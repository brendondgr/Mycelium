"""The post-onboarding single-area live match (`onboarding_match_area`)."""

import math

import pytest
from django.contrib.auth.models import User
from django.db import connection

from apps.accounts.models import WatchPreference
from apps.billing.models import Subscription, Tier
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
    # Entitle the researcher (Spore+) so the match uses the LLM path; the tests that
    # want the deterministic path pass an explicit fallback ``complete``.
    Subscription.objects.create(tier=Tier.SPORE, scope_user=user)
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

    # Deterministic fallback (no LLM) so the test runs offline; inject the scan seam
    # so the sparse-batch hybrid never touches Celery.
    scans: list[str] = []
    result = onboarding_match_area(
        user, "papers", complete=lambda _p: None, enqueue_scan=scans.append
    )

    assert result["area"] == "papers"
    assert result["status"] == "ok"
    assert result["matched"] >= 1
    # The strong match is surfaced and persisted as a per-user score.
    assert RelevanceScore.objects.filter(
        target_user=user, content=match
    ).exists()
    titles = [row["title"] for row in result["sample"]]
    assert any("graph health" in title.casefold() for title in titles)
    # Fallback matches carry no LLM percent, so the batch has 0 high-quality (>=80%)
    # matches — far below the default minimum — so the background scan is triggered.
    assert result["scanning"] is True
    assert scans == ["matcher"]


@pytest.mark.django_db
def test_papers_onboarding_skips_scan_when_batch_is_rich(pgvector, settings) -> None:
    """A latest batch with enough high-quality matches shows immediately — no scan."""

    settings.PAPER_ONBOARDING_MIN_HIGH_QUALITY = 1
    embeddings.set_embedder(_fake_embed)
    _paper("m", "graph health", [1.0, 1.0, 0.0, 0.0])
    user = _profile_user("rich", areas=["graph", "health"])

    def complete(_prompt: str) -> str:
        return None  # the rank-band verdict is what richness is measured by

    scans: list[str] = []
    result = onboarding_match_area(
        user, "papers", complete=complete, enqueue_scan=scans.append
    )

    assert result["scanning"] is False
    assert scans == []  # the batch was rich enough; no background scan


@pytest.mark.django_db
def test_non_paper_area_never_scans(pgvector) -> None:
    """Grants/conferences/fellowships are corpus-only — they never trigger a scan."""
    embeddings.set_embedder(_fake_embed)
    user = _profile_user("gonly", areas=["graph"])

    scans: list[str] = []
    result = onboarding_match_area(
        user, "grants", complete=lambda _p: None, enqueue_scan=scans.append
    )

    assert result["scanning"] is False
    assert scans == []
