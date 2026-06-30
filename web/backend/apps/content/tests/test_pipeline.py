"""The per-user pipeline: query building, graceful degradation, and the RAG run."""

import math

import pytest
from django.contrib.auth.models import User
from django.db import connection

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


# -- pure ---------------------------------------------------------------------


def test_build_queries_uses_areas_then_keywords() -> None:
    interests = {"areas": ["AI", "Graphs"], "keywords": ["rag", "AI"]}

    assert build_queries(interests, limit=10) == ["AI", "Graphs", "rag"]


def test_build_queries_respects_limit() -> None:
    interests = {"areas": ["a", "b", "c"], "keywords": ["d"]}

    assert build_queries(interests, limit=2) == ["a", "b"]


# -- graceful degradation (no pgvector needed) --------------------------------


@pytest.mark.django_db
def test_no_interests_short_circuits() -> None:
    user = User.objects.create_user("nobody", password="x")
    # Fresh profile has empty interests.

    result = run_for_user(user, search_fn=_no_search)

    assert result.status == "no_interests"


@pytest.mark.django_db
def test_no_embedder_reports_cleanly() -> None:
    user = User.objects.create_user("someone", password="x")
    user.profile.interests = {"areas": ["Knowledge Graphs"]}
    user.profile.save()
    embeddings.set_embedder(None)

    result = run_for_user(user, search_fn=_no_search)

    assert result.status == "no_embedder"
    assert result.queries == ["Knowledge Graphs"]


# -- full RAG run (pgvector) --------------------------------------------------


@pytest.fixture
def pgvector(db: None):
    if connection.vendor != "postgresql":
        pytest.skip("the RAG path needs PostgreSQL + pgvector")


def _profile_user(username: str) -> User:
    user = User.objects.create_user(username, password="x")
    user.profile.interests = {
        "areas": ["Knowledge Graphs"],
        "keywords": ["biomedical knowledge discovery"],
    }
    user.profile.save()
    return user


def _paper(source: str, title: str) -> ContentItem:
    return ContentItem.objects.create(
        type=ContentItem.Type.PAPER,
        source=source,
        external_id=source,
        embedding=_fake_embed([title])[0],
        metadata={"title": title, "abstract": title},
    )


@pytest.mark.django_db
def test_full_pipeline_persists_scores_and_suggestions(pgvector) -> None:
    embeddings.set_embedder(_fake_embed)
    near = _paper("near", "knowledge graph for biomedical discovery")
    far = _paper("far", "an unrelated other topic")
    user = _profile_user("ragger")

    result = run_for_user(user, search_fn=_no_search, complete=lambda _p: None)

    assert result.status == "ok"
    assert result.retrieved == 2
    assert result.suggestions >= 1
    scores = {s.content_id: s for s in RelevanceScore.objects.filter(target_user=user)}
    assert near.id in scores and far.id in scores
    # The on-topic paper outscores the unrelated one and is flagged suggested.
    assert scores[near.id].score > scores[far.id].score
    assert scores[near.id].signals["suggested"] is True
    assert scores[near.id].signals["source"] == "fallback"
    # Profile embedding was persisted for the future scoring phase.
    user.profile.refresh_from_db()
    assert user.profile.embedding is not None


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
