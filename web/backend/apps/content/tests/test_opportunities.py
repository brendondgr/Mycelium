"""Per-user grants/conferences matching: interests, LLM scoring, pins, persist.

The pure/LLM/pin pieces run offline (SQLite); the full retrieval path is gated on
PostgreSQL + pgvector, mirroring ``test_pipeline``.
"""

import json
import math

import pytest
from django.contrib.auth.models import User
from django.db import connection

from apps.accounts.models import WatchPreference
from apps.content import embeddings
from apps.content.models import ContentItem, RelevanceScore
from apps.content.opportunities import (
    match_opportunities_for_user,
    opportunity_search_interests,
    run_daily_opportunities_batch,
)
from apps.content.opportunity_llm import generate_opportunity_suggestions
from apps.content.pinning import compute_pins
from apps.scraper.pivot.ingest import ingest_pivot

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


# -- pure: search interests ---------------------------------------------------


def test_opportunity_search_interests_from_areas_and_topics():
    interests = {"areas": ["Knowledge Graphs"], "keywords": ["biomedical"]}
    ints = opportunity_search_interests(interests, ["Agentic AI"])
    labels = [i.label for i in ints]
    assert labels == ["Knowledge Graphs"]
    # watch topics broaden every interest's lexical query
    assert "agentic ai" in ints[0].query_text.casefold()


def test_opportunity_search_interests_falls_back_to_watch_topics():
    ints = opportunity_search_interests({}, ["Agentic AI", "Robotics"])
    assert [i.label for i in ints] == ["Agentic AI", "Robotics"]


# -- LLM scoring (offline via injected complete) ------------------------------


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


def _persisted_grant(gid, title):
    return ContentItem.objects.create(
        type=ContentItem.Type.GRANT,
        source="pivot",
        external_id=gid,
        metadata={"title": title, "search_text": title},
    )


# -- pinning ------------------------------------------------------------------


@pytest.mark.django_db
def test_compute_pins_flags_new_high_fit_only():
    today = "2026-07-05"

    def _item(gid, first_seen):
        return ContentItem.objects.create(
            type=ContentItem.Type.GRANT,
            source="pivot",
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

    pins = compute_pins(suggestions, items_by_id, today=today, percentile=80)

    assert pins[str(a.id)]["is_new"] is True
    assert pins[str(a.id)]["pinned_until"] == "2026-07-12"  # first_seen + 7 days
    assert pins[str(b.id)]["is_new"] is False  # new but below the 80th percentile
    assert pins[str(c.id)]["is_new"] is False  # high match but first seen > 7 days ago
    assert pins[str(d.id)]["is_new"] is False


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
        "url": f"https://pivot.proquest.com/funding_opps/{gid}",
        "matched_topics": title,
    }


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
    return user


@pytest.mark.django_db
def test_match_grants_end_to_end(pgvector):
    embeddings.set_embedder(_fake_embed)
    user = _profile_user("brendon")
    ingest_pivot(
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
def test_grant_match_threshold_surfaces_only_related(pgvector, settings):
    """Grants are gated by the embedding-match threshold, not a fixed top-25 slice.

    A strongly-matching grant clears a 60% threshold; a weakly-related one does not,
    so it is not surfaced/persisted — and the survivor records its embedding match.
    """
    settings.GRANT_MATCH_THRESHOLD = 0.6
    embeddings.set_embedder(_fake_embed)
    user = _profile_user("gthresh")
    ingest_pivot(
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
    assert scores["g_strong"].signals["embedding_match"] >= 0.6
    assert result.suggestions == 1


def _embedded_conf(cid, name, scope):
    return ContentItem.objects.create(
        type=ContentItem.Type.CONFERENCE,
        source="pivot",
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
    settings.CONFERENCE_MATCH_THRESHOLD = 0.6
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
    assert scores[strong.id].signals["embedding_match"] >= 0.6
    assert result.suggestions == 1


@pytest.mark.django_db
def test_batch_scores_units_concurrently(pgvector):
    """The batch scores (user, area) units in parallel, not one at a time."""
    import threading
    import time

    embeddings.set_embedder(_fake_embed)
    for name in ("u1", "u2", "u3"):
        _profile_user(name)
    ingest_pivot(
        [("grants", _grant("g1", "Knowledge Graphs for biomedical health"))],
        embedder=_fake_embed,
        prune=False,
        today="2026-07-05",
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
        ingest=False,
        prune=False,
        concurrency=12,
        complete=slow_complete,
        today="2026-07-05",
    )

    ok = [r for r in batch.results if r.status == "ok"]
    assert len(ok) == 3  # every user scored + persisted
    assert state["peak"] >= 2  # units ran concurrently, not serially
