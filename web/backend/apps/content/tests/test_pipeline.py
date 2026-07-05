"""The per-user pipeline: query building, graceful degradation, and the RAG run."""

import math

import pytest
from django.contrib.auth.models import User
from django.db import connection

from apps.accounts.models import WatchPreference
from apps.content import embeddings
from apps.content.models import ContentItem, RelevanceScore
from apps.content.pipeline import build_queries, run_for_user

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
def test_llm_suggestions_counted(pgvector) -> None:
    import json

    embeddings.set_embedder(_fake_embed)
    near = _paper("near", "knowledge graph for biomedical discovery")
    _paper("far", "an unrelated other topic")
    user = _profile_user("llm-user")

    def complete(_prompt: str) -> str:
        return json.dumps(
            {"suggestions": [{"paper": 1, "headline": "Top", "reason": "Fits you."}]}
        )

    result = run_for_user(user, search_fn=_no_search, complete=complete)

    assert result.llm == 1 and result.fallback == 0
    top = RelevanceScore.objects.get(target_user=user, content=near)
    assert top.signals["source"] == "llm"
    assert top.signals["headline"] == "Top"
    # A percent match is persisted for every suggested paper.
    assert isinstance(top.signals["match_percent"], int)
    assert 0 <= top.signals["match_percent"] <= 100


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
