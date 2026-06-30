"""The daily-report endpoint: own suggestions, latest run only, auth-gated."""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.content.models import ContentItem, RelevanceScore


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def _paper(title: str) -> ContentItem:
    return ContentItem.objects.create(
        type=ContentItem.Type.PAPER,
        source="OpenAlex",
        external_id=title,
        source_url="https://example.org/p",
        metadata={"title": title, "venue": "Nature", "year": 2026},
    )


def _suggest(user, paper, *, rank, run_at, score=0.8, suggested=True) -> RelevanceScore:
    return RelevanceScore.objects.create(
        content=paper,
        target_user=user,
        score=score,
        signals={
            "suggested": suggested,
            "run_at": run_at,
            "rank": rank,
            "headline": f"Headline {rank}",
            "reason": f"Reason {rank}",
            "source": "llm",
        },
    )


@pytest.mark.django_db
def test_requires_authentication(client: APIClient) -> None:
    assert client.get("/api/daily-report/").status_code in (401, 403)


@pytest.mark.django_db
def test_empty_when_no_run(client: APIClient) -> None:
    user = User.objects.create_user("fresh", password="x")
    client.force_authenticate(user)

    resp = client.get("/api/daily-report/")

    assert resp.status_code == 200
    assert resp.data == {"generated_at": None, "suggestions": []}


@pytest.mark.django_db
def test_returns_latest_run_ordered_by_rank(client: APIClient) -> None:
    user = User.objects.create_user("brendon", password="x")
    old = _suggest(user, _paper("Old"), rank=1, run_at="2026-06-28T00:00:00")
    _suggest(user, _paper("Second"), rank=2, run_at="2026-06-29T00:00:00")
    first = _suggest(user, _paper("First"), rank=1, run_at="2026-06-29T00:00:00")

    client.force_authenticate(user)
    resp = client.get("/api/daily-report/")

    assert resp.status_code == 200
    assert resp.data["generated_at"] == "2026-06-29T00:00:00"
    titles = [s["title"] for s in resp.data["suggestions"]]
    assert titles == ["First", "Second"]  # latest run only, rank order
    assert old.content.metadata["title"] == "Old"  # excluded
    assert {"headline", "reason", "source", "url", "venue", "year"} <= set(
        resp.data["suggestions"][0]
    )
    assert resp.data["suggestions"][0]["origin"] == "llm"
    assert first.signals["rank"] == 1


@pytest.mark.django_db
def test_excludes_unsuggested_and_other_users(client: APIClient) -> None:
    user = User.objects.create_user("me", password="x")
    other = User.objects.create_user("them", password="x")
    _suggest(user, _paper("Mine"), rank=1, run_at="2026-06-29T00:00:00")
    # A retrieved-but-not-suggested row for the same user must not surface.
    RelevanceScore.objects.create(
        content=_paper("Retrieved only"),
        target_user=user,
        score=0.3,
        signals={"suggested": False, "run_at": "2026-06-29T00:00:00"},
    )
    _suggest(other, _paper("Theirs"), rank=1, run_at="2026-06-29T00:00:00")

    client.force_authenticate(user)
    resp = client.get("/api/daily-report/")

    titles = [s["title"] for s in resp.data["suggestions"]]
    assert titles == ["Mine"]
