"""Per-user grants/conferences matching: interests, LLM scoring, pins, persist.

The pure/LLM/pin pieces run offline (SQLite); the full retrieval path is gated on
PostgreSQL + pgvector, mirroring ``test_pipeline``.
"""

import json
import math

import pytest
from apps.accounts.models import WatchPreference
from apps.billing.models import Subscription, Tier
from apps.billing.testing import entitle_user
from django.contrib.auth.models import User
from django.db import connection

from tools.recommendation.models import RelevanceScore
from tools.recommendation.opportunities import (
    match_opportunities_for_user,
    opportunity_search_interests,
    run_daily_opportunities_batch,
)
from tools.recommendation.opportunity_llm import generate_opportunity_suggestions
from tools.recommendation.pinning import compute_pins
from tools.retrieval import embeddings
from tools.retrieval.models import ContentItem

_TOKENS = ["graph", "health", "biomedical", "other"]


def _fake_embed(texts):
    out = []
    for text in texts:
        low = text.casefold()
        vec = [1.0 if tok in low else 0.0 for tok in _TOKENS]
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        out.append([x / norm for x in vec])
    return out


@pytest.fixture(autouse=True)
def _reset_embedder():
    embeddings.reset_embedder()
    yield
    embeddings.reset_embedder()


@pytest.fixture(autouse=True)
def _open_opportunity_thresholds(settings):
    """Surface every fused opportunity by default, isolating these tests from the
    production match thresholds. The dedicated threshold test overrides its own."""
    settings.GRANT_MATCH_THRESHOLD = 0.0
    settings.CONFERENCE_MATCH_THRESHOLD = 0.0
    settings.OPPORTUNITY_MIN_MATCH_PERCENT = 0


# -- pure: search interests ---------------------------------------------------


def test_watch_topics_no_longer_leak_into_every_interest():
    """They used to, and that is what made every query the same query.

    Fifteen watch topics plus nine keywords appended to each of twenty-two areas
    left one reader's searches ~95% identical, so a single knowledge-graph
    workshop led all five of their themes at once.
    """
    interests = {"areas": ["Knowledge Graphs"], "keywords": ["biomedical"]}
    ints = opportunity_search_interests(interests, ["Agentic AI"])
    assert [i.label for i in ints] == ["Knowledge Graphs"]
    assert ints[0].query_text == "Knowledge Graphs"
    assert "agentic ai" not in ints[0].query_text.casefold()
    assert "biomedical" not in ints[0].query_text.casefold()


def test_context_comes_from_the_interests_own_theme():
    """Two themes must never end up asking the same question."""
    from tools.recommendation.clustering import Cluster

    interests = {"areas": ["knowledge graphs", "entity resolution", "nanotechnology"]}
    clusters = [
        Cluster(id="c-kg", label="KG",
                areas=["knowledge graphs", "entity resolution"]),
        Cluster(id="c-nano", label="Emerging", areas=["nanotechnology"]),
    ]

    ints = {
        i.label: i.query_text
        for i in opportunity_search_interests(interests, ["Agentic AI"],
                                              clusters=clusters)
    }

    assert ints["knowledge graphs"] == "knowledge graphs entity resolution"
    # The nanotechnology query carries no knowledge-graph vocabulary at all.
    assert ints["nanotechnology"] == "nanotechnology"


def test_opportunity_search_interests_falls_back_to_watch_topics():
    ints = opportunity_search_interests({}, ["Agentic AI", "Robotics"])
    assert [i.label for i in ints] == ["Agentic AI", "Robotics"]


# -- LLM scoring (offline via injected complete) ------------------------------



def _stored_writeup(lead: str, verdict: str = "read") -> dict:
    """A stored per-theme write-up in the shape the reuse check accepts."""
    from tools.recommendation.cluster_fit import RUBRIC_VERSION, areas_fingerprint

    return {
        "verdict": verdict,
        "beats": [lead],
        "caveat": "Worth checking the eligibility text.",
        "bridge_note": "",
        "source": "llm",
        "rubric_version": RUBRIC_VERSION,
        "areas_fingerprint": areas_fingerprint(["Knowledge Graphs"]),
        "written_on": "2026-07-01",
    }


def _mylo_answer(prompt: str) -> str:
    """A model answering both stages — the précis, then the per-theme verdict."""
    if prompt.startswith("Title:"):
        return json.dumps(
            {
                "problem": "A problem.",
                "method": "A method.",
                "setting": "A cohort.",
                "claim": "A claim.",
                "limitations": "Small sample.",
                "reusable": "A baseline.",
                "thin": False,
            }
        )
    rows = [
        {
            "n": int(line[1 : line.index("]")]),
            "verdict": "read",
            "matters": "It funds this strand.",
            "use": "Apply in the spring round.",
            "take": "Take the eligibility list.",
            "caveat": "The deadline is tight.",
        }
        for line in prompt.splitlines()
        if line.startswith("[")
    ]
    return json.dumps({"items": rows})


@pytest.mark.django_db
def test_generate_suggestions_fallback_when_no_model():
    items = [
        (_persisted_grant("g1", "Knowledge Graphs Award"), 0.9),
        (_persisted_grant("g2", "Robotics Grant"), 0.5),
    ]
    out = generate_opportunity_suggestions(
        ContentItem.Type.GRANT,
        {"areas": ["Knowledge Graphs"]},
        {"academic_title": "student"},
        items,
        complete=lambda _p: None,  # model unavailable -> all fallback
    )
    assert [s["source"] for s in out] == ["fallback", "fallback"]
    assert all(s["match_percent"] is None for s in out)
    assert out[0]["rank"] == 1


@pytest.mark.django_db
def test_generate_suggestions_uses_model_scores():
    items = [(_persisted_grant("g1", "Knowledge Graphs Award"), 0.9)]

    def _complete(_prompt):
        return json.dumps(
            {
                "suggestions": [
                    {
                        "item": 1,
                        "match": 92,
                        "headline": "Strong Fit",
                        "reason": "Aligns with your graph work.",
                    }
                ]
            }
        )

    out = generate_opportunity_suggestions(
        ContentItem.Type.GRANT, {}, {}, items, complete=_complete
    )
    assert out[0]["source"] == "llm"
    assert out[0]["match_percent"] == 92
    assert out[0]["headline"] == "Strong Fit"


# -- carry-forward: prior verdicts skip the model, new items get freed slots --


@pytest.mark.django_db
def test_carry_forward_skips_already_scored_item_and_reuses_its_verdict():
    """An item ``prior`` already scored is never re-sent to the model; its verdict
    survives, and the freed ``llm_limit`` slot goes to the unscored item."""
    scored = _persisted_grant("g_scored", "Knowledge Graphs Award")
    unscored = _persisted_grant("g_unscored", "Robotics Grant")
    items = [(scored, 0.9), (unscored, 0.5)]
    prior = {
        str(scored.id): {
            "match_percent": 82,
            "headline": "Carried Headline",
            "reason": "Carried reason from a prior run.",
            "llm_scored_at": "2026-07-01T00:00:00+00:00",
        }
    }
    seen_prompts: list[str] = []

    def _complete(prompt):
        seen_prompts.append(prompt)
        return json.dumps(
            {
                "suggestions": [
                    {"item": 1, "match": 95, "headline": "Fresh", "reason": "New."}
                ]
            }
        )

    out = generate_opportunity_suggestions(
        ContentItem.Type.GRANT,
        {},
        {},
        items,
        llm_limit=1,
        prior=prior,
        complete=_complete,
    )

    # Only the unscored grant reached the prompt.
    assert seen_prompts
    assert "Robotics Grant" in seen_prompts[0]
    assert "Knowledge Graphs Award" not in seen_prompts[0]

    carried = next(s for s in out if s["content_id"] == str(scored.id))
    assert carried["source"] == "llm"
    assert carried["match_percent"] == 82
    assert carried["headline"] == "Carried Headline"
    assert carried["llm_scored_at"] == "2026-07-01T00:00:00+00:00"
    fresh = next(s for s in out if s["content_id"] == str(unscored.id))
    assert fresh["source"] == "llm"
    assert fresh["match_percent"] == 95


@pytest.mark.django_db
def test_slate_entrant_gets_llm_slot_priority_over_older_unscored():
    """An item that just entered the Top-25 wins the one free LLM slot over a
    higher-ranked one that has been sitting in the slate unwritten."""
    standing = _persisted_grant("g_old", "Old High Rank Grant")
    entrant = _persisted_grant("g_new", "Newly Promoted Grant")
    items = [(standing, 0.9), (entrant, 0.4)]  # fused order: standing first

    seen_prompts: list[str] = []

    def _complete(prompt):
        seen_prompts.append(prompt)
        return json.dumps({"suggestions": []})

    generate_opportunity_suggestions(
        ContentItem.Type.GRANT,
        {},
        {},
        items,
        llm_limit=1,
        priority_ids={str(entrant.id)},
        complete=_complete,
    )

    assert seen_prompts
    assert "Newly Promoted Grant" in seen_prompts[0]
    assert "Old High Rank Grant" not in seen_prompts[0]


@pytest.mark.django_db
def test_model_verdict_does_not_reorder_the_feed():
    """A grant the model scored 95 does not overtake a better-fused one it skipped.

    This is the whole failure the Top-25 change is about: when the verdict decided
    the order and the budget went to whatever had just been ingested, an unrelated
    bulk import led every reader's feed.
    """
    best = _persisted_grant("g_best", "Best Fused Grant")
    weaker = _persisted_grant("g_weak", "Weaker Fused Grant")
    items = [(best, 0.9), (weaker, 0.4)]

    def _complete(_prompt):
        return json.dumps(
            {
                "suggestions": [
                    {"item": 1, "match": 95, "headline": "h", "reason": "r"}
                ]
            }
        )

    out = generate_opportunity_suggestions(
        ContentItem.Type.GRANT,
        {},
        {},
        items,
        llm_limit=1,
        priority_ids={str(weaker.id)},  # the weaker one gets the write-up…
        complete=_complete,
    )

    # …and stays exactly where retrieval put it.
    assert [s["content_id"] for s in out] == [str(best.id), str(weaker.id)]
    assert [s["rank"] for s in out] == [1, 2]
    assert out[1]["match_percent"] == 95
    assert out[0]["match_percent"] is None


def _persisted_grant(gid, title):
    return ContentItem.objects.create(
        type=ContentItem.Type.GRANT,
        source="legacy",
        external_id=gid,
        metadata={"title": title, "search_text": title},
    )


# -- pinning ------------------------------------------------------------------


@pytest.mark.django_db
def test_compute_pins_flags_every_recently_seen_item():
    """Every item first seen within the window is New — no fit gate.

    The feed is already interest-thresholded, so being *in* it means "worth
    recommending"; pinning only distinguishes fresh from old, regardless of the
    match strength. Items first seen more than a week ago are not new.
    """
    today = "2026-07-05"

    def _item(gid, first_seen):
        return ContentItem.objects.create(
            type=ContentItem.Type.GRANT,
            source="legacy",
            external_id=gid,
            metadata={"first_seen": first_seen, "title": gid},
        )

    a = _item("a", "2026-07-05T00:00:00+00:00")  # new, top match
    b = _item("b", "2026-07-05T00:00:00+00:00")  # new, low match
    c = _item("c", "2026-06-20T00:00:00+00:00")  # old, high match
    d = _item("d", "2026-07-05T00:00:00+00:00")  # new, low match
    items_by_id = {str(x.id): x for x in (a, b, c, d)}
    suggestions = [
        {"content_id": str(a.id), "match_percent": 95},
        {"content_id": str(b.id), "match_percent": 50},
        {"content_id": str(c.id), "match_percent": 70},
        {"content_id": str(d.id), "match_percent": 30},
    ]

    pins = compute_pins(suggestions, items_by_id, today=today)

    # All three recently-seen items are new — even the low-match ones.
    assert pins[str(a.id)]["is_new"] is True
    assert pins[str(a.id)]["pinned_until"] == "2026-07-12"  # first_seen + 7 days
    assert pins[str(b.id)]["is_new"] is True
    assert pins[str(d.id)]["is_new"] is True
    # First seen > 7 days ago: no longer new, no pin.
    assert pins[str(c.id)]["is_new"] is False
    assert pins[str(c.id)]["pinned_until"] is None


@pytest.mark.django_db
def test_compute_pins_papers_fall_back_to_created_at():
    """Papers carry no metadata.first_seen, so pinning uses the ingest date."""
    from datetime import timedelta

    from django.utils import timezone as tz

    fresh = ContentItem.objects.create(
        type=ContentItem.Type.PAPER, source="openalex", external_id="p_fresh",
        metadata={"title": "fresh"},
    )
    old = ContentItem.objects.create(
        type=ContentItem.Type.PAPER, source="openalex", external_id="p_old",
        metadata={"title": "old"},
    )
    # created_at is auto_now_add; backdate the "old" paper past the window.
    ContentItem.objects.filter(pk=old.pk).update(
        created_at=tz.now() - timedelta(days=30)
    )
    old.refresh_from_db()
    items_by_id = {str(fresh.id): fresh, str(old.id): old}
    suggestions = [{"content_id": str(fresh.id)}, {"content_id": str(old.id)}]

    pins = compute_pins(suggestions, items_by_id)

    assert pins[str(fresh.id)]["is_new"] is True
    expected_first_seen = tz.localdate(fresh.created_at).isoformat()
    assert pins[str(fresh.id)]["first_seen"] == expected_first_seen
    assert pins[str(old.id)]["is_new"] is False


# -- full retrieval E2E (pgvector) --------------------------------------------


@pytest.fixture
def pgvector(db: None):
    if connection.vendor != "postgresql":
        pytest.skip("the opportunity retrieval path needs PostgreSQL + pgvector")


def _grant(gid, title, deadline_date="2026-12-01"):
    return {
        "id": gid,
        "title": title,
        "sponsor": "NSF",
        "amount": "$100,000",
        "deadline_date": deadline_date,
        "url": f"https://example.org/funding_opps/{gid}",
        "matched_topics": title,
    }


def _seed_grants(pairs, *, embedder, today, prune=False):
    """Stand-in for a retired grant-ingest test fixture (plan Phase 6). These
    tests only ever seeded grants — never
    conferences/fellowships — to exercise the *matching* pipeline, not ingest,
    so this builds ``ContentItem`` grant rows directly and embeds them with the
    injected embedder, mirroring ``_persisted_grant`` / ``_embedded_conf`` above
    rather than routing through any production ingest module.
    """
    assert not prune, "this test fixture never prunes"
    created: list[ContentItem] = []
    texts: list[str] = []
    for area, rec in pairs:
        assert area == "grants", f"only grants are seeded here, got {area!r}"
        parts = (rec.get("title"), rec.get("sponsor"), rec.get("matched_topics"))
        text = " ".join(str(part) for part in parts if part)
        obj = ContentItem.objects.create(
            type=ContentItem.Type.GRANT,
            source="grants:test",
            external_id=rec["id"],
            source_url=rec.get("url", ""),
            metadata={
                "title": rec.get("title", ""),
                "sponsor": rec.get("sponsor", ""),
                "amount": rec.get("amount", ""),
                "deadline_date": rec.get("deadline_date", ""),
                "matched_topics": rec.get("matched_topics", ""),
                "search_text": text,
                "first_seen": f"{today}T00:00:00+00:00",
            },
        )
        created.append(obj)
        texts.append(text)
    vectors = embedder(texts)
    for obj, vector in zip(created, vectors, strict=False):
        obj.embedding = vector
        obj.save(update_fields=["embedding"])
    return created


def _profile_user(username):
    user = User.objects.create_user(username, password="x")
    user.profile.interests = {
        "areas": ["Knowledge Graphs"],
        "keywords": ["biomedical"],
    }
    user.profile.save()
    WatchPreference.objects.update_or_create(
        user=user, defaults={"topics": ["knowledge graphs"]}
    )
    # Entitle the researcher (Spore+) so the daily pipeline runs the full path —
    # these tests exercise pipeline mechanics, not the tier gate.
    Subscription.objects.create(tier=Tier.SPORE, scope_user=user)
    return user


@pytest.mark.django_db
def test_match_grants_end_to_end(pgvector):
    embeddings.set_embedder(_fake_embed)
    user = _profile_user("brendon")
    _seed_grants(
        [
            ("grants", _grant("g_match", "Knowledge Graphs for biomedical health")),
            ("grants", _grant("g_other", "Marine biology other funding")),
        ],
        embedder=_fake_embed,
        prune=False,
        today="2026-07-05",
    )

    result = match_opportunities_for_user(
        user, "grants", complete=lambda _p: None, today="2026-07-05"
    )
    assert result.status == "ok"
    assert result.retrieved >= 1

    scores = RelevanceScore.objects.filter(target_user=user, content__type="grant")
    assert scores.exists()
    top = scores.order_by("-score").first()
    assert top.signals["area"] == "grant"
    assert top.signals["deadline_date"] == "2026-12-01"
    assert "is_new" in top.signals
    assert "pinned_until" in top.signals

    # Re-running overwrites rather than duplicating (one row per content+user).
    before = scores.count()
    match_opportunities_for_user(
        user, "grants", complete=lambda _p: None, today="2026-07-05"
    )
    assert scores.count() == before


@pytest.mark.django_db
def test_match_grants_floor_hides_low_score_but_persists_verdict(settings):
    """A grant the model scores below OPPORTUNITY_MIN_MATCH_PERCENT is persisted
    (carry-forward remembers it) but hidden from the feed; a 60+ grant stays.

    Drives ``_score_job``/``_finalize_match`` directly over a hand-built job —
    the floor logic under test lives entirely there, so this skips the
    retrieval/fusion machinery (gated on pgvector, and liable to drop one of two
    near-identical fixtures via the *unrelated* per-interest RRF floor).
    """
    from tools.recommendation.opportunities import (
        _finalize_match,
        _MatchJob,
        _score_job,
    )
    from tools.recommendation.targets import target_for_user

    settings.OPPORTUNITY_MIN_MATCH_PERCENT = 60
    user = _profile_user("floortest")
    strong = _persisted_grant("g_strong", "Strong Match Grant")
    weak = _persisted_grant("g_weak", "Weak Match Grant")
    job = _MatchJob(
        target=target_for_user(user),
        username="floortest",
        area="grants",
        content_type=ContentItem.Type.GRANT,
        pairs=[(strong, 0.9), (weak, 0.5)],
        rows=[(strong, 0.9, {}), (weak, 0.5, {})],
        pool=2,
        llm_limit=10,
        surface_limit=None,
    )

    def _complete(prompt):
        rows = []
        for line in prompt.splitlines():
            if not line.startswith("["):
                continue
            idx = int(line[1 : line.index("]")])
            if "Weak Match Grant" in line:
                rows.append(
                    {"item": idx, "match": 10, "headline": "Weak", "reason": "Barely."}
                )
            elif "Strong Match Grant" in line:
                rows.append(
                    {"item": idx, "match": 90, "headline": "Strong", "reason": "Great."}
                )
        return json.dumps({"suggestions": rows})

    suggestions = _score_job(job, complete=_complete)
    result = _finalize_match(
        job, suggestions, persist=True, today="2026-07-05", log=None
    )
    assert result.suggestions == 1
    assert result.hidden == 1

    scores = {
        s.content.external_id: s
        for s in RelevanceScore.objects.filter(target_user=user, content__type="grant")
    }
    # Both persisted (carry-forward remembers both verdicts)...
    assert "g_strong" in scores and "g_weak" in scores
    # ...but only the strong one is flagged suggested.
    assert scores["g_strong"].signals["suggested"] is True
    assert scores["g_strong"].signals["match_percent"] == 90
    assert scores["g_weak"].signals["suggested"] is False
    assert scores["g_weak"].signals["match_percent"] == 10


@pytest.mark.django_db
def test_refit_bypasses_carry_forward_for_grants(pgvector):
    """``refit_user`` re-sends every surfaced grant to the model, even ones a prior
    run already scored (``reuse_prior=False`` skips the carry-forward store)."""
    from tools.recommendation.refitting import refit_user

    embeddings.set_embedder(_fake_embed)
    user = _profile_user("refitbypass")
    _seed_grants(
        [("grants", _grant("g1", "Knowledge Graphs for biomedical health"))],
        embedder=_fake_embed,
        prune=False,
        today="2026-07-05",
    )

    entitle_user(user)
    calls = {"n": 0}

    def _complete(prompt):
        calls["n"] += 1
        return _mylo_answer(prompt)

    match_opportunities_for_user(
        user, "grants", complete=_complete, today="2026-07-05"
    )
    first = calls["n"]
    assert first > 0  # first run reads and judges it

    refit_user(
        user, areas=("grants",), complete=_complete, persist=True, log=None
    )
    # The refit re-sent the already-written grant to the model instead of
    # carrying its stored write-up forward.
    assert calls["n"] > first


@pytest.mark.django_db
def test_grant_match_threshold_surfaces_only_related(pgvector, settings):
    """Grants are gated by the embedding-match threshold, not a fixed top-25 slice.

    A strongly-matching grant clears a 60% threshold; a weakly-related one does not,
    so it is not surfaced/persisted — and the survivor records its embedding match.
    """
    # 0.5, not 0.6: an interest's query is now just its declared area, so a
    # three-token document scores 1/sqrt(3) against a one-token query rather than
    # riding the profile-wide keyword suffix that used to be bolted onto it. The
    # separation this test is about — a related grant clears, an unrelated one
    # does not — is unchanged (0.577 vs 0.0); only the absolute geometry moved.
    settings.GRANT_MATCH_THRESHOLD = 0.5
    embeddings.set_embedder(_fake_embed)
    user = _profile_user("gthresh")
    _seed_grants(
        [
            ("grants", _grant("g_strong", "Knowledge Graphs for biomedical health")),
            ("grants", _grant("g_weak", "Marine biology other funding")),
        ],
        embedder=_fake_embed,
        prune=False,
        today="2026-07-05",
    )

    result = match_opportunities_for_user(
        user, "grants", complete=lambda _p: None, today="2026-07-05"
    )
    assert result.status == "ok"

    scores = {
        s.content.external_id: s
        for s in RelevanceScore.objects.filter(target_user=user, content__type="grant")
    }
    assert "g_strong" in scores
    assert "g_weak" not in scores  # below the 60% embedding-match threshold
    assert scores["g_strong"].signals["embedding_match"] >= 0.5
    assert result.suggestions == 1


def _embedded_conf(cid, name, scope):
    return ContentItem.objects.create(
        type=ContentItem.Type.CONFERENCE,
        source="legacy",
        external_id=cid,
        embedding=_fake_embed([f"{name} {scope}"])[0],
        metadata={
            "name": name,
            "scope": scope,
            "keywords": name,
            "search_text": f"{name} {scope}",
        },
    )


@pytest.mark.django_db
def test_conference_match_threshold_surfaces_only_related(pgvector, settings):
    """Conferences are gated by the embedding-match threshold, like grants."""
    # 0.5, not 0.6: an interest's query is now just its declared area, so a
    # three-token document scores 1/sqrt(3) against a one-token query rather than
    # riding the profile-wide keyword suffix that used to be bolted onto it. The
    # separation this test is about — a related grant clears, an unrelated one
    # does not — is unchanged (0.577 vs 0.0); only the absolute geometry moved.
    settings.CONFERENCE_MATCH_THRESHOLD = 0.5
    embeddings.set_embedder(_fake_embed)
    user = _profile_user("cthresh")
    strong = _embedded_conf(
        "c_strong", "Knowledge Graphs in biomedical health", "graph methods"
    )
    weak = _embedded_conf("c_weak", "Marine biology symposium", "other topics")

    result = match_opportunities_for_user(
        user, "conferences", complete=lambda _p: None, today="2026-07-05"
    )
    assert result.status == "ok"

    scores = {
        s.content_id: s
        for s in RelevanceScore.objects.filter(
            target_user=user, content__type="conference"
        )
    }
    assert strong.id in scores
    assert weak.id not in scores  # below the 60% embedding-match threshold
    assert scores[strong.id].signals["embedding_match"] >= 0.5
    assert result.suggestions == 1


@pytest.mark.django_db
def test_batch_scores_units_concurrently(pgvector):
    """The batch scores (user, area) units in parallel, not one at a time."""
    import threading
    import time

    embeddings.set_embedder(_fake_embed)
    for name in ("u1", "u2", "u3"):
        _profile_user(name)
    _seed_grants(
        [("grants", _grant("g1", "Knowledge Graphs for biomedical health"))],
        embedder=_fake_embed,
        prune=False,
        today="2026-07-05",
    )
    # The daily run scores only items ingested on the run day; stamp created_at to
    # the simulated run date so this new grant is in that day's new-items pool.
    from datetime import UTC, datetime

    ContentItem.objects.filter(type=ContentItem.Type.GRANT).update(
        created_at=datetime(2026, 7, 5, 12, tzinfo=UTC)
    )

    # A slow model call that records how many run at the same time.
    lock = threading.Lock()
    state = {"live": 0, "peak": 0}

    def slow_complete(_prompt):
        with lock:
            state["live"] += 1
            state["peak"] = max(state["peak"], state["live"])
        time.sleep(0.2)
        with lock:
            state["live"] -= 1
        return None  # deterministic fallback; we only care about concurrency

    batch = run_daily_opportunities_batch(
        [u for u in User.objects.filter(username__in=("u1", "u2", "u3"))],
        areas=("grants",),
        prune=False,
        concurrency=12,
        complete=slow_complete,
        today="2026-07-05",
    )

    ok = [r for r in batch.results if r.status == "ok"]
    assert len(ok) == 3  # every user scored + persisted
    assert state["peak"] >= 2  # units ran concurrently, not serially


# -- the nightly whole-corpus re-rank -----------------------------------------


@pytest.mark.django_db
def test_daily_batch_reranks_what_is_already_in_the_feed(pgvector):
    """The nightly run ranks a grant it has already scored, instead of skipping it.

    This is what makes the feed answer to the *reader*: a run that only ever looked
    at items it had never scored could not re-order anything, so editing a research
    focus left the old list in place. What it must not do is pay the model twice —
    the verdict already written is carried forward untouched.
    """
    from datetime import UTC, datetime

    embeddings.set_embedder(_fake_embed)
    user = _profile_user("rerank")
    _seed_grants(
        [("grants", _grant("g_known", "Knowledge Graphs for biomedical health"))],
        embedder=_fake_embed,
        prune=False,
        today="2026-07-05",
    )
    known = ContentItem.objects.get(external_id="g_known")
    # Ingested days ago and already scored, so the old append-only gate would have
    # excluded it from retrieval entirely.
    ContentItem.objects.filter(pk=known.pk).update(
        created_at=datetime(2026, 7, 1, tzinfo=UTC)
    )
    RelevanceScore.objects.create(
        content=known,
        target_user=user,
        score=0.9,
        signals={
            "area": "grant",
            "run_at": "2026-07-01T00:00:00",
            "suggested": True,
            "rank": 1,
            "headline": "Known Grant",
            "reason": "A write-up from an earlier run.",
            "source": "llm",
            "cluster_slates": {
                "c-all": {
                    "label": "",
                    "rank": 1,
                    "entered_on": "2026-07-01",
                    "is_new": True,
                }
            },
            "writeups": {
                "c-all": _stored_writeup("A write-up from an earlier run."),
            },
            "top_rank": 1,
            "entered_top_on": "2026-07-01",
            "is_new_top": True,
        },
    )

    run_daily_opportunities_batch(
        [user],
        areas=("grants",),
        prune=False,
        complete=lambda _p: None,
        today="2026-07-05",
    )

    signals = RelevanceScore.objects.get(target_user=user, content=known).signals
    assert signals["run_at"] != "2026-07-01T00:00:00"  # re-ranked tonight
    assert signals["reason"] == "A write-up from an earlier run."  # reused verbatim
    assert signals["source"] == "llm"
    assert signals["match_percent"] is None  # the percent is retired everywhere
    # It was already in the reader's slate, so it is not announced a second time,
    # and the date still says when it first appeared in a report.
    assert signals["cluster_slates"]["c-all"]["rank"] == 1
    assert signals["cluster_slates"]["c-all"]["is_new"] is False
    assert signals["top_rank"] == 1
    assert signals["is_new_top"] is False
    assert signals["entered_top_on"] == "2026-07-01"


@pytest.mark.django_db
def test_daily_batch_picks_up_an_unscored_backlog_from_an_earlier_day(pgvector):
    """A matchable grant ingested days ago that no run ever scored is picked up.

    The regression this guards: the daily run used to gate on ``created_at`` == today,
    so a corpus imported on a day the pipeline did not complete could never be scored
    by any later run — it was no longer "new today" — and the feed stayed empty next
    to a store full of matchable items.
    """
    from datetime import UTC, datetime

    embeddings.set_embedder(_fake_embed)
    user = _profile_user("backlog")
    _seed_grants(
        [("grants", _grant("g_backlog", "Knowledge Graphs for biomedical health"))],
        embedder=_fake_embed,
        prune=False,
        today="2026-07-05",
    )
    item = ContentItem.objects.get(external_id="g_backlog")
    # Ingested four days ago, and never scored for this user.
    ContentItem.objects.filter(pk=item.pk).update(
        created_at=datetime(2026, 7, 1, tzinfo=UTC)
    )

    run_daily_opportunities_batch(
        [user],
        areas=("grants",),
        prune=False,
        complete=lambda _p: None,
        today="2026-07-05",
    )

    assert RelevanceScore.objects.filter(
        target_user=user, content=item
    ).exists()


@pytest.mark.django_db
def test_whole_corpus_match_replaces_stale_feed_rows(pgvector, settings):
    """A whole-corpus run re-establishes the feed: a previously-suggested grant that
    no longer matches stops being surfaced rather than lingering in the list."""
    # 0.5, not 0.6: an interest's query is now just its declared area, so a
    # three-token document scores 1/sqrt(3) against a one-token query rather than
    # riding the profile-wide keyword suffix that used to be bolted onto it. The
    # separation this test is about — a related grant clears, an unrelated one
    # does not — is unchanged (0.577 vs 0.0); only the absolute geometry moved.
    settings.GRANT_MATCH_THRESHOLD = 0.5
    embeddings.set_embedder(_fake_embed)
    user = _profile_user("replace")
    _seed_grants(
        [
            ("grants", _grant("g_strong", "Knowledge Graphs for biomedical health")),
            ("grants", _grant("g_stale", "Marine biology other funding")),
        ],
        embedder=_fake_embed,
        prune=False,
        today="2026-07-05",
    )
    strong = ContentItem.objects.get(external_id="g_strong")
    stale = ContentItem.objects.get(external_id="g_stale")
    # g_stale used to be in the user's feed (before an interest change).
    RelevanceScore.objects.create(
        content=stale,
        target_user=user,
        score=0.5,
        signals={
            "area": "grant",
            "run_at": "2026-07-01T00:00:00",
            "suggested": True,
            "rank": 1,
            "match_percent": 70,
            "source": "llm",
        },
    )

    # Serial path: unscored_only defaults to False -> whole corpus -> re-establish.
    match_opportunities_for_user(
        user, "grants", complete=lambda _p: None, today="2026-07-05"
    )

    rows = {
        s.content_id: s
        for s in RelevanceScore.objects.filter(
            target_user=user, content__type="grant"
        )
    }
    assert rows[strong.id].signals["suggested"] is True  # the current match is kept
    # The stale row leaves the feed but is not deleted: it still holds the verdict
    # the model was paid for, so if the interest swings back it costs nothing.
    assert rows[stale.id].signals["suggested"] is False
    assert "top_rank" not in rows[stale.id].signals
    assert rows[stale.id].signals["match_percent"] == 70
