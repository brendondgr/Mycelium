"""The per-user pipeline: query building, graceful degradation, and the RAG run."""

import math
from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.utils import timezone

from apps.accounts.models import WatchPreference
from apps.content import embeddings
from apps.content.digest_selection import renumber, split_by_floor
from apps.content.models import ContentItem, RelevanceScore
from apps.content.pipeline import (
    build_queries,
    gather_scan_queries,
    run_daily_batch,
    run_for_user,
)
from apps.content.tests.entitle import entitle_user

# A tiny deterministic embedder shared by the profile and the papers so cosine
# distance is meaningful without loading fastembed.
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
def _open_match_threshold(settings):
    """Surface every fused candidate by default, isolating these tests from the
    production ``PAPER_MATCH_THRESHOLD``. Tests that exercise the threshold set their
    own value explicitly via ``match_threshold=``."""
    settings.PAPER_MATCH_THRESHOLD = 0.0
    settings.PAPER_MIN_MATCH_PERCENT = 0


def _no_search(*_args, **_kwargs):
    return []


def _set_watch(user: User, topics: list[str]) -> None:
    """Give a user the watch topics that now drive the literature scan."""
    WatchPreference.objects.update_or_create(user=user, defaults={"topics": topics})


# -- pure ---------------------------------------------------------------------


def test_build_queries_dedupes_and_preserves_order() -> None:
    # The watch topics are the sole search source; order is the user's priority,
    # duplicates collapse case-insensitively.
    topics = ["Knowledge Graphs", "RAG", "knowledge graphs", "biomedical"]

    assert build_queries(topics, limit=10) == ["Knowledge Graphs", "RAG", "biomedical"]


def test_build_queries_respects_limit() -> None:
    assert build_queries(["a", "b", "c", "d"], limit=2) == ["a", "b"]


# -- global scan-term gathering (batch phase 1) -------------------------------


@pytest.mark.django_db
def test_gather_scan_queries_unions_and_dedupes() -> None:
    u1 = User.objects.create_user("g1", password="x")
    u2 = User.objects.create_user("g2", password="x")
    u3 = User.objects.create_user("g3", password="x")
    _set_watch(u1, ["Knowledge Graphs", "RAG"])
    _set_watch(u2, ["knowledge graphs", "Biomedical NLP"])  # dup of u1's first
    _set_watch(u3, [])  # contributes nothing

    terms = gather_scan_queries([u1, u2, u3])

    # Deduped case-insensitively across users, order-preserving (first seen wins).
    assert terms == ["Knowledge Graphs", "RAG", "Biomedical NLP"]


@pytest.mark.django_db
def test_gather_scan_queries_respects_per_user_and_global_limits() -> None:
    u1 = User.objects.create_user("g4", password="x")
    u2 = User.objects.create_user("g5", password="x")
    _set_watch(u1, ["a", "b", "c"])
    _set_watch(u2, ["d", "e", "f"])

    # Each user contributes at most per_user_limit; the global cap trims the union.
    assert gather_scan_queries([u1, u2], per_user_limit=2) == ["a", "b", "d", "e"]
    assert gather_scan_queries([u1, u2], per_user_limit=2, global_limit=3) == [
        "a",
        "b",
        "d",
    ]


def test_gather_scan_queries_empty_users() -> None:
    assert gather_scan_queries([]) == []


# -- graceful degradation (no pgvector needed) --------------------------------


@pytest.mark.django_db
def test_no_watch_topics_short_circuits() -> None:
    user = User.objects.create_user("nobody", password="x")
    user.profile.interests = {"areas": ["AI"]}
    user.profile.save()
    # No watch topics set -> nothing to search for, even with interests present.

    result = run_for_user(user, search_fn=_no_search)

    assert result.status == "no_watch_topics"


@pytest.mark.django_db
def test_no_embedder_reports_cleanly() -> None:
    user = User.objects.create_user("someone", password="x")
    user.profile.interests = {"areas": ["Knowledge Graphs"]}
    user.profile.save()
    _set_watch(user, ["Knowledge Graphs"])
    embeddings.set_embedder(None)

    result = run_for_user(user, search_fn=_no_search)

    assert result.status == "no_embedder"
    assert result.queries == ["Knowledge Graphs"]


# -- full RAG run (pgvector) --------------------------------------------------


@pytest.fixture
def pgvector(db: None):
    if connection.vendor != "postgresql":
        pytest.skip("the RAG path needs PostgreSQL + pgvector")


def _profile_user(username: str, *, areas=None, keywords=None) -> User:
    user = User.objects.create_user(username, password="x")
    user.profile.interests = {
        "areas": areas if areas is not None else ["Knowledge Graphs"],
        "keywords": keywords if keywords is not None else ["biomedical discovery"],
    }
    user.profile.save()
    # Watch topics drive the scan; without them the run short-circuits.
    _set_watch(user, ["knowledge graphs", "biomedical discovery"])
    return user


def _paper(source: str, title: str) -> ContentItem:
    return ContentItem.objects.create(
        type=ContentItem.Type.PAPER,
        source=source,
        external_id=source,
        embedding=_fake_embed([title])[0],
        metadata={"title": title, "abstract": title},
    )


def _vpaper(source: str, title: str, vector: list[float]) -> ContentItem:
    """A paper with an explicit embedding, so per-interest cosine is controllable."""
    return ContentItem.objects.create(
        type=ContentItem.Type.PAPER,
        source=source,
        external_id=source,
        embedding=vector,
        metadata={"title": title, "abstract": title},
    )


@pytest.mark.django_db
def test_fusion_prefers_multi_interest_paper(pgvector) -> None:
    """The primary integration test: a paper matching 2 interests beats 1-interest.

    Explicit embeddings over the ``_fake_embed`` token axes (graph, health, …) so
    each interest's per-paper cosine — and thus the fusion outcome — is
    deterministic. ``p_both`` is the strongest paper in *both* interest channels.
    """
    embeddings.set_embedder(_fake_embed)
    # Interests "graph" and "health" embed to [1,0,0,0] and [0,1,0,0].
    p_both = _vpaper("both", "graph health", [1.0, 1.0, 0.0, 0.0])
    p_one = _vpaper("one", "graph biomedical", [0.5, 0.0, 0.8, 0.0])  # graph only
    p_two = _vpaper("two", "health public", [0.0, 0.5, 0.0, 0.8])  # health only
    user = _profile_user("fuser", areas=["graph", "health"], keywords=[])

    result = run_for_user(user, search_fn=_no_search, complete=lambda _p: None)

    assert result.status == "ok"
    assert result.interests == 2
    scores = {s.content_id: s for s in RelevanceScore.objects.filter(target_user=user)}
    # The two-interest paper is surfaced, matched both interests, and outranks the
    # single-interest papers.
    both = scores[p_both.id]
    assert both.signals["n_matched"] == 2
    assert set(both.signals["per_interest"]) == {"graph", "health"}
    assert both.score > scores[p_one.id].score
    assert both.score > scores[p_two.id].score
    # The single-interest papers each matched exactly one.
    assert scores[p_one.id].signals["n_matched"] == 1
    assert scores[p_two.id].signals["n_matched"] == 1
    # Profile embedding is still persisted for downstream scoring.
    user.profile.refresh_from_db()
    assert user.profile.embedding is not None


def _clustered_user(username: str) -> User:
    """A user whose two areas (graph, health) live in two named clusters."""
    user = User.objects.create_user(username, password="x")
    user.profile.interests = {
        "version": 2,
        "areas": ["graph", "health"],
        "keywords": [],
        "clusters": [
            {"id": "c-graph", "label": "Graph", "areas": ["graph"]},
            {"id": "c-health", "label": "Health", "areas": ["health"]},
        ],
    }
    user.profile.save()
    _set_watch(user, ["graph", "health"])
    return user


@pytest.mark.django_db
def test_cluster_scoping_attributes_and_bridges(pgvector) -> None:
    """>= 2 clusters: single-cluster papers attribute to their cluster with no
    bridge; a paper strong in both clusters clears the floor in both and bridges."""
    embeddings.set_embedder(_fake_embed)
    # Symmetric pool: a graph-only, a health-only, and a both paper. The single
    # papers dominate their own channel (the other floors out); the both paper is
    # second in each, so it clears the floor in both clusters -> a bridge.
    p_graph = _vpaper("g", "graph", [1.0, 0.0, 0.0, 0.0])
    p_health = _vpaper("h", "health", [0.0, 1.0, 0.0, 0.0])
    p_bridge = _vpaper("b", "graph health", [1.0, 1.0, 0.0, 0.0])
    user = _clustered_user("cluster-user")

    result = run_for_user(user, search_fn=_no_search, complete=lambda _p: None)
    assert result.status == "ok"

    scores = {s.content_id: s for s in RelevanceScore.objects.filter(target_user=user)}

    graph_only = scores[p_graph.id]
    assert graph_only.signals["cluster_id"] == "c-graph"
    assert graph_only.signals["cluster_label"] == "Graph"
    assert graph_only.signals["bridge_cluster_ids"] == []
    assert set(graph_only.signals["per_cluster"]) == {"c-graph"}

    health_only = scores[p_health.id]
    assert health_only.signals["cluster_id"] == "c-health"
    assert health_only.signals["bridge_cluster_ids"] == []

    bridge = scores[p_bridge.id]
    # Cleared the floor in both clusters -> both scores present and a bridge badge;
    # the symmetric scores tie so attribution breaks to the earliest cluster.
    assert set(bridge.signals["per_cluster"]) == {"c-graph", "c-health"}
    assert bridge.signals["cluster_id"] == "c-graph"
    assert bridge.signals["bridge_cluster_ids"] == ["c-health"]


@pytest.mark.django_db
def test_cluster_edit_reattributes_on_rerun(pgvector) -> None:
    """Renaming clusters and re-running (the refit path, reuse_prior=False) updates
    the persisted attribution — a paper picks up the new cluster label/ids."""
    embeddings.set_embedder(_fake_embed)
    _vpaper("g", "graph", [1.0, 0.0, 0.0, 0.0])  # competition so health floors out
    p_health = _vpaper("h", "health", [0.0, 1.0, 0.0, 0.0])
    user = _clustered_user("edit-user")
    run_for_user(user, search_fn=_no_search, complete=lambda _p: None)
    first = RelevanceScore.objects.get(target_user=user, content=p_health)
    assert first.signals["cluster_id"] == "c-health"

    # Edit the profile: rename the health cluster (new id + label), keep areas.
    user.profile.interests = {
        "version": 2,
        "areas": ["graph", "health"],
        "clusters": [
            {"id": "c-graph", "label": "Graph", "areas": ["graph"]},
            {"id": "c-wellness", "label": "Wellness", "areas": ["health"]},
        ],
    }
    user.profile.save()

    from apps.content.pipeline import recommend_for_user

    recommend_for_user(
        user, complete=lambda _p: None, reuse_prior=False
    )
    again = RelevanceScore.objects.get(target_user=user, content=p_health)
    assert again.signals["cluster_id"] == "c-wellness"
    assert again.signals["cluster_label"] == "Wellness"


@pytest.mark.django_db
def test_single_cluster_has_no_attribution(pgvector) -> None:
    """One (implicit) cluster scores byte-identically to today — no cluster fields."""
    embeddings.set_embedder(_fake_embed)
    _vpaper("g", "graph health", [1.0, 1.0, 0.0, 0.0])
    user = _profile_user("solo", areas=["graph", "health"], keywords=[])

    run_for_user(user, search_fn=_no_search, complete=lambda _p: None)
    score = RelevanceScore.objects.filter(target_user=user).first()
    assert "cluster_id" not in score.signals  # flat path writes no attribution
    assert score.signals["n_matched"] == 2  # still the flat multi-interest breadth


@pytest.mark.django_db
def test_match_threshold_filters_fusion_by_embedding_cosine(pgvector) -> None:
    """The paper feed surfaces only candidates whose transformer cosine clears the
    threshold — a variable-length list — and records that cosine as embedding_match.

    ``p_both`` matches both interests at cosine ~0.71; the single-interest papers
    match one at ~0.53. A 0.60 threshold keeps only ``p_both``, so the surfaced count
    is 1 rather than a fixed 25.
    """
    embeddings.set_embedder(_fake_embed)
    p_both = _vpaper("both", "graph health", [1.0, 1.0, 0.0, 0.0])
    p_one = _vpaper("one", "graph biomedical", [0.5, 0.0, 0.8, 0.0])  # graph only
    p_two = _vpaper("two", "health public", [0.0, 0.5, 0.0, 0.8])  # health only
    user = _profile_user("thresholder", areas=["graph", "health"], keywords=[])

    result = run_for_user(
        user, search_fn=_no_search, complete=lambda _p: None, match_threshold=0.6
    )

    assert result.status == "ok"
    scores = {s.content_id: s for s in RelevanceScore.objects.filter(target_user=user)}
    # Only the two-interest paper cleared the 60% embedding-match threshold.
    assert set(scores) == {p_both.id}
    assert p_one.id not in scores
    assert p_two.id not in scores
    # Its embedding cosine (~0.71) is recorded for the UI's cross-embedding badge.
    assert scores[p_both.id].signals["embedding_match"] >= 0.7
    assert result.suggestions == 1


@pytest.mark.django_db
def test_match_threshold_filters_single_vector_path(pgvector) -> None:
    """The same threshold gates the no-areas single-vector path, on raw similarity."""
    embeddings.set_embedder(_fake_embed)
    strong = _vpaper("strong", "graph", [1.0, 0.0, 0.0, 0.0])  # cosine ~1.0
    weak = _vpaper("weak", "graph other", [0.5, 0.0, 0.0, 0.87])  # cosine ~0.5
    user = User.objects.create_user("sv-threshold", password="x")
    user.profile.interests = {"statement": "graph"}  # no areas -> single-vector
    user.profile.save()
    _set_watch(user, ["graph"])

    result = run_for_user(
        user, search_fn=_no_search, complete=lambda _p: None, match_threshold=0.7
    )

    assert result.status == "ok"
    assert result.interests == 0  # single-vector fallback path
    scored = {
        s.content_id: s for s in RelevanceScore.objects.filter(target_user=user)
    }
    assert strong.id in scored
    assert weak.id not in scored  # cosine ~0.5 fell below the 0.7 threshold
    assert scored[strong.id].signals["embedding_match"] >= 0.9


@pytest.mark.django_db
def test_single_interest_fusion_drops_unrelated(pgvector) -> None:
    embeddings.set_embedder(_fake_embed)
    near = _paper("near", "knowledge graph for biomedical discovery")
    far = _paper("far", "an unrelated other topic")
    user = _profile_user("ragger")  # one area: "Knowledge Graphs"

    result = run_for_user(user, search_fn=_no_search, complete=lambda _p: None)

    assert result.status == "ok"
    assert result.retrieved == 2  # both pulled into the candidate pool
    scores = {s.content_id: s for s in RelevanceScore.objects.filter(target_user=user)}
    # The on-topic paper is surfaced with its per-interest breakdown; the unrelated
    # one fell below the per-interest floor and is not surfaced/persisted.
    assert near.id in scores
    assert far.id not in scores
    assert scores[near.id].signals["suggested"] is True
    assert scores[near.id].signals["source"] == "fallback"
    assert "per_interest" in scores[near.id].signals
    assert "n_matched" in scores[near.id].signals


@pytest.mark.django_db
def test_no_areas_falls_back_to_single_vector(pgvector) -> None:
    """Profiles without declared areas keep the original single-vector behaviour."""
    embeddings.set_embedder(_fake_embed)
    near = _paper("near", "knowledge graph for biomedical discovery")
    user = User.objects.create_user("plain", password="x")
    user.profile.interests = {"statement": "knowledge graph biomedical"}  # no areas
    user.profile.save()
    _set_watch(user, ["knowledge graphs"])

    result = run_for_user(user, search_fn=_no_search, complete=lambda _p: None)

    assert result.status == "ok"
    assert result.interests == 0  # single-vector fallback path
    top = RelevanceScore.objects.get(target_user=user, content=near)
    # The single-vector path persists similarity/focus signals, not per-interest.
    assert "similarity" in top.signals
    assert "focus_overlap" in top.signals
    assert "per_interest" not in top.signals


@pytest.mark.django_db
def test_recommend_papers_are_fresh_only_and_pinned(pgvector) -> None:
    """The paper feed shows only the freshest gather batch, never a previous day.

    A stronger match gathered weeks ago must NOT surface — papers are the daily
    exception that never mixes old with new. Only papers from the latest gather day
    are scored, and (being fresh) they are flagged New and pinned to the top.
    """
    embeddings.set_embedder(_fake_embed)
    # Profile statement "graph" embeds to [1,0,0,0]; both papers match it, but the
    # old one was gathered a month ago so it is not part of today's freshest batch.
    old = _vpaper("old-strong", "graph", [1.0, 0.0, 0.0, 0.0])
    ContentItem.objects.filter(pk=old.pk).update(
        created_at=timezone.now() - timedelta(days=30)
    )
    fresh = _vpaper("fresh-weak", "graph health", [0.8, 0.6, 0.0, 0.0])  # today
    user = User.objects.create_user("retain", password="x")
    user.profile.interests = {"statement": "graph"}  # no areas → single-vector path
    user.profile.save()
    _set_watch(user, ["knowledge graphs"])

    result = run_for_user(user, search_fn=_no_search, complete=lambda _p: None)

    assert result.status == "ok"
    assert result.interests == 0  # single-vector fallback path
    rows = {
        r.content_id: r for r in RelevanceScore.objects.filter(target_user=user)
    }
    # Only the freshest gather day is scored — the month-old paper is not in the feed.
    assert old.id not in rows
    assert fresh.id in rows
    # The freshly-gathered paper is flagged New and pinned to the top.
    assert rows[fresh.id].signals["is_new"] is True
    assert rows[fresh.id].signals["pinned_until"]


def _mylo_answer(prompt: str) -> str:
    """A model answering both stages — the précis, then the per-theme verdict."""
    import json

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
            "matters": "It matches your knowledge-graph work.",
            "use": "Use it as a baseline.",
            "take": "Take their evaluation protocol.",
            "caveat": "The cohort is small.",
        }
        for line in prompt.splitlines()
        if line.startswith("[")
    ]
    return json.dumps({"items": rows})


@pytest.mark.django_db
def test_llm_suggestions_counted(pgvector) -> None:
    """An entitled reader gets a model verdict, three beats, and a caveat.

    And no percent: the number implied a measurement nobody made, so the row
    carries a ``verdict`` instead and ``match_percent`` is explicitly ``None``.
    """
    embeddings.set_embedder(_fake_embed)
    near = _paper("near", "knowledge graph for biomedical discovery")
    _paper("far", "an unrelated other topic")
    user = _profile_user("llm-user")
    entitle_user(user)

    result = run_for_user(user, search_fn=_no_search, complete=_mylo_answer)

    assert result.llm == 1 and result.fallback == 0
    top = RelevanceScore.objects.get(target_user=user, content=near)
    assert top.signals["source"] == "llm"
    # Persisted headline is the paper's real title, not the model's rename.
    assert top.signals["headline"] == "knowledge graph for biomedical discovery"
    assert top.signals["match_percent"] is None
    assert top.signals["verdict"] == "read"
    assert top.signals["caveat"] == "The cohort is small."
    writeup = top.signals["writeups"]["c-all"]
    assert len(writeup["beats"]) == 3
    assert writeup["caveat"]


@pytest.mark.django_db
def test_an_unentitled_reader_gets_a_complete_deterministic_report(pgvector) -> None:
    """The deterministic path is the baseline product, not a degraded one.

    No model call happens at all, and the row still carries a position-derived
    verdict, a lead sentence, and a caveat — the same shape a paid row has.
    """
    embeddings.set_embedder(_fake_embed)
    near = _paper("near", "knowledge graph for biomedical discovery")
    user = _profile_user("free-user")  # no subscription

    calls: list[str] = []

    def complete(prompt: str) -> str:
        calls.append(prompt)
        return _mylo_answer(prompt)

    run_for_user(user, search_fn=_no_search, complete=complete)

    assert calls == []  # gated before the prompt, not after
    row = RelevanceScore.objects.get(target_user=user, content=near)
    assert row.signals["source"] == "fallback"
    assert row.signals["verdict"] in {"read", "skim", "file"}
    assert row.signals["caveat"]
    assert row.signals["match_percent"] is None


@pytest.mark.django_db
def test_a_second_run_over_an_unchanged_profile_costs_nothing(pgvector) -> None:
    """Reuse is the default: a model call happens once per artefact, ever."""
    embeddings.set_embedder(_fake_embed)
    _paper("near", "knowledge graph for biomedical discovery")
    user = _profile_user("reuser")
    entitle_user(user)

    calls = {"n": 0}

    def complete(prompt: str) -> str:
        calls["n"] += 1
        return _mylo_answer(prompt)

    run_for_user(user, search_fn=_no_search, complete=complete)
    first = calls["n"]
    assert first > 0

    run_for_user(user, search_fn=_no_search, complete=complete)
    assert calls["n"] == first  # nothing re-sent


@pytest.mark.django_db
def test_paper_floor_hides_low_score_but_persists_verdict(settings) -> None:
    """A paper the model scores below PAPER_MIN_MATCH_PERCENT is persisted
    (carry-forward remembers it) but hidden from the feed; a 60+ paper stays.

    Drives ``generate_suggestions`` + ``_persist`` directly over hand-built rows
    — the floor logic under test lives in ``recommend_for_user``'s finalize/
    persist step, so this skips retrieval/fusion (gated on pgvector, and liable
    to drop one of two near-identical fixtures via the *unrelated* per-interest
    RRF floor — see the opportunity twin of this test for the same pitfall).
    """
    import json

    from apps.content.pipeline import _persist
    from apps.content.suggest import generate_suggestions

    settings.PAPER_MIN_MATCH_PERCENT = 60
    user = User.objects.create_user("floortest", password="x")
    strong = _paper("strong", "Strong Match Paper")
    weak = _paper("weak", "Weak Match Paper")

    def complete(prompt: str) -> str:
        rows = []
        for line in prompt.splitlines():
            if not line.startswith("["):
                continue
            idx = int(line[1 : line.index("]")])
            if "Weak Match Paper" in line:
                rows.append(
                    {"paper": idx, "match": 10, "headline": "Weak", "reason": "Barely."}
                )
            elif "Strong Match Paper" in line:
                rows.append(
                    {
                        "paper": idx,
                        "match": 90,
                        "headline": "Strong",
                        "reason": "Great.",
                    }
                )
        return json.dumps({"suggestions": rows})

    suggestions = generate_suggestions(
        {}, [(strong, 0.9), (weak, 0.5)], complete=complete
    )
    visible, hidden = split_by_floor(suggestions, 60)
    assert len(visible) == 1 and len(hidden) == 1

    visible_ids = {s["content_id"] for s in visible}
    _persist(
        {"target_user": user},
        ContentItem.Type.PAPER,
        [(strong, 0.9, {}), (weak, 0.5, {})],
        suggestions,
        visible_ids,
    )

    scores = {s.content_id: s for s in RelevanceScore.objects.filter(target_user=user)}
    assert strong.id in scores and weak.id in scores
    assert scores[strong.id].signals["suggested"] is True
    assert scores[strong.id].signals["match_percent"] == 90
    assert scores[weak.id].signals["suggested"] is False
    assert scores[weak.id].signals["match_percent"] == 10


def test_renumber_closes_the_gaps_the_floor_leaves() -> None:
    """Pure: ranks describe the list you are looking at, not the one before it."""
    visible = [{"rank": 1}, {"rank": 2}, {"rank": 11}, {"rank": 12}]

    assert [s["rank"] for s in renumber(visible)] == [1, 2, 3, 4]


@pytest.mark.django_db
def test_surfaced_papers_are_numbered_contiguously(settings) -> None:
    """A lab reported papers arriving "1 → 2 → 11 → 12" — eight apparently missing.

    Nothing was missing. Ranks are handed out over the whole surfaced set before
    the match-percent floor removes the papers the model judged poorly, so the
    survivors kept the numbering of a list they were no longer part of. The
    numbering now describes what is actually shown.
    """
    import json

    from apps.content.pipeline import _persist
    from apps.content.suggest import generate_suggestions

    settings.PAPER_MIN_MATCH_PERCENT = 60
    user = User.objects.create_user("gaptest", password="x")
    # Three go to the model (two pass, one is rejected); two never reach it and
    # form the unscored tail that used to resume at a stranded number.
    papers = [_paper(f"p{n}", f"Paper {n}") for n in range(5)]
    verdicts = {"Paper 0": 90, "Paper 1": 80, "Paper 2": 20}

    def complete(prompt: str) -> str:
        rows = []
        for line in prompt.splitlines():
            if not line.startswith("["):
                continue
            idx = int(line[1 : line.index("]")])
            for title, match in verdicts.items():
                if title in line:
                    rows.append({"paper": idx, "match": match, "reason": "Because."})
        return json.dumps({"suggestions": rows})

    pairs = [(paper, 1.0 - n / 10) for n, paper in enumerate(papers)]
    suggestions = generate_suggestions({}, pairs, llm_limit=3, complete=complete)
    # The bug, reproduced: pre-floor the survivors are 1, 2, 4, 5.
    pre_floor = [
        s["rank"] for s in suggestions if (s["match_percent"] or 100) >= 60
    ]
    assert pre_floor == [1, 2, 4, 5]

    visible, hidden = split_by_floor(suggestions, 60)
    renumber(visible)
    assert len(visible) == 4 and len(hidden) == 1

    _persist(
        {"target_user": user},
        ContentItem.Type.PAPER,
        [(paper, score, {}) for paper, score in pairs],
        suggestions,
        {s["content_id"] for s in visible},
    )

    shown = [
        s.signals["rank"]
        for s in RelevanceScore.objects.filter(target_user=user)
        if s.signals["suggested"]
    ]
    assert sorted(shown) == [1, 2, 3, 4]


@pytest.mark.django_db
def test_refit_bypasses_carry_forward_for_papers(pgvector) -> None:
    """``refit_user`` re-sends every surfaced paper to the model, even ones a prior
    run already scored (``reuse_prior=False`` skips the carry-forward store)."""

    from apps.content.refitting import refit_user

    embeddings.set_embedder(_fake_embed)
    _paper("near", "knowledge graph for biomedical discovery")
    user = _profile_user("refitbypass")

    entitle_user(user)
    calls = {"n": 0}

    def complete(prompt: str) -> str:
        calls["n"] += 1
        return _mylo_answer(prompt)

    run_for_user(user, search_fn=_no_search, complete=complete)
    first = calls["n"]
    assert first > 0  # first run reads and judges it

    refit_user(user, areas=("papers",), complete=complete, persist=True, log=None)
    # The refit re-sent the already-written paper to the model instead of
    # carrying its stored write-up forward.
    assert calls["n"] > first


@pytest.mark.django_db
def test_rerun_is_idempotent(pgvector) -> None:
    embeddings.set_embedder(_fake_embed)
    _paper("near", "knowledge graph for biomedical discovery")
    user = _profile_user("repeat")

    run_for_user(user, search_fn=_no_search, complete=lambda _p: None)
    first = RelevanceScore.objects.filter(target_user=user).count()
    run_for_user(user, search_fn=_no_search, complete=lambda _p: None)
    second = RelevanceScore.objects.filter(target_user=user).count()

    assert first == second == 1


@pytest.mark.django_db
def test_dry_run_persists_nothing(pgvector) -> None:
    embeddings.set_embedder(_fake_embed)
    _paper("near", "knowledge graph for biomedical discovery")
    user = _profile_user("dry")

    result = run_for_user(
        user, search_fn=_no_search, complete=lambda _p: None, persist=False
    )

    assert result.status == "ok"
    assert RelevanceScore.objects.filter(target_user=user).count() == 0


# -- batch run: ingest once, recommend per user -------------------------------


@pytest.mark.django_db
def test_batch_scans_shared_terms_once_and_recommends_all(pgvector) -> None:
    """The core efficiency win: a shared topic is searched once, not per user."""
    embeddings.set_embedder(_fake_embed)
    # One paper already in the shared store for everyone to be recommended from.
    _vpaper("p", "graph health", [1.0, 1.0, 0.0, 0.0])

    calls: list[list[str]] = []

    def counting_search(queries, _window, _sources):
        calls.append(list(queries))
        return []  # no NEW papers; the pre-loaded one stays

    _set_watch(_profile_user("b1", areas=["graph"], keywords=[]), ["graph", "health"])
    _set_watch(_profile_user("b2", areas=["graph"], keywords=[]), ["graph"])  # shares
    _set_watch(_profile_user("b3", areas=["health"], keywords=[]), ["health"])  # shares
    # Fresh instances, exactly as select_users returns them in production (no
    # stale cached watch relations from the setup above).
    users = list(User.objects.filter(username__in=["b1", "b2", "b3"]).order_by("id"))

    result = run_daily_batch(
        users,
        search_fn=counting_search,
        embed=False,
        complete=lambda _p: None,
    )

    # Phase 1: the sources were hit exactly once, over the deduped union — NOT
    # once per user (that would be three calls / re-searching "graph" & "health").
    assert len(calls) == 1
    assert calls[0] == ["graph", "health"]
    assert result.ingest["unique_queries"] == 2
    # Phase 2: every user got a recommendation from the shared store.
    assert [r.status for r in result.results] == ["ok", "ok", "ok"]
    for username in ("b1", "b2", "b3"):
        assert RelevanceScore.objects.filter(target_user__username=username).exists()


@pytest.mark.django_db
def test_batch_skips_users_without_topics(pgvector) -> None:
    embeddings.set_embedder(_fake_embed)
    _vpaper("p", "graph health", [1.0, 1.0, 0.0, 0.0])

    _set_watch(_profile_user("has-topics", areas=["graph"], keywords=[]), ["graph"])
    # A user who opted out of monitoring (no watch topics).
    _set_watch(_profile_user("no-topics", areas=["graph"], keywords=[]), [])
    users = list(
        User.objects.filter(username__in=["has-topics", "no-topics"]).order_by("id")
    )

    result = run_daily_batch(
        users, search_fn=_no_search, embed=False, complete=lambda _p: None
    )

    by_name = {r.username: r.status for r in result.results}
    assert by_name["has-topics"] == "ok"
    assert by_name["no-topics"] == "no_watch_topics"
