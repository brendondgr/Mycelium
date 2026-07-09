"""The post-onboarding single-area live match (`onboarding_match_area`)."""

import math

import pytest
from django.contrib.auth.models import User
from django.db import connection

from apps.accounts.models import WatchPreference
from apps.content import embeddings
from apps.content.models import ContentItem, RelevanceScore
from apps.content.onboarding_match import UnknownArea, onboarding_match_area

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


@pytest.fixture
def pgvector(db: None):
    if connection.vendor != "postgresql":
        pytest.skip("the RAG path needs PostgreSQL + pgvector")


def _profile_user(username: str, *, areas) -> User:
    user = User.objects.create_user(username, password="x")
    user.profile.interests = {"areas": areas, "keywords": []}
    user.profile.save()
    WatchPreference.objects.update_or_create(
        user=user, defaults={"topics": areas}
    )
    return user


def _paper(source: str, title: str, vector: list[float]) -> ContentItem:
    return ContentItem.objects.create(
        type=ContentItem.Type.PAPER,
        source=source,
        external_id=source,
        embedding=vector,
        metadata={"title": title, "abstract": title},
    )


def test_unknown_area_raises() -> None:
    # Guard runs before any DB access, so no database is needed.
    user = User(username="nobody")
    with pytest.raises(UnknownArea):
        onboarding_match_area(user, "widgets")


@pytest.mark.django_db
def test_papers_area_matches_and_persists(pgvector) -> None:
    embeddings.set_embedder(_fake_embed)
    match = _paper("m", "graph health", [1.0, 1.0, 0.0, 0.0])
    _paper("far", "an unrelated other topic", [0.0, 0.0, 0.0, 1.0])
    user = _profile_user("matcher", areas=["graph", "health"])

    # Deterministic fallback (no LLM) so the test runs offline.
    result = onboarding_match_area(user, "papers", complete=lambda _p: None)

    assert result["area"] == "papers"
    assert result["status"] == "ok"
    assert result["matched"] >= 1
    # The strong match is surfaced and persisted as a per-user score.
    assert RelevanceScore.objects.filter(
        target_user=user, content=match
    ).exists()
    titles = [row["title"] for row in result["sample"]]
    assert any("graph health" in title.casefold() for title in titles)
