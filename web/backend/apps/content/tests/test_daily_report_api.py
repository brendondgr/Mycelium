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
        metadata={
            "title": title,
            "abstract": f"Abstract of {title}",
            "venue": "Nature",
            "year": 2026,
        },
    )


def _suggest(
    user,
    paper,
    *,
    rank,
    run_at,
    score=0.8,
    suggested=True,
    match=80,
    focus_areas=None,
    per_interest=None,
    embedding_match=0.72,
) -> RelevanceScore:
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
            "verdict": "read" if match >= 75 else "skim",
            "embedding_match": embedding_match,
            "focus_areas": focus_areas or [],
            "per_interest": per_interest or {},
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
    assert resp.data == {
        "generated_at": None,
        "summary": None,
        "suggestions": [],
        "scanning": False,
    }


@pytest.mark.django_db
def test_returns_latest_run_ordered_by_rank(client: APIClient) -> None:
    user = User.objects.create_user("brendon", password="x")
    old = _suggest(user, _paper("Old"), rank=1, run_at="2026-06-28T00:00:00")
    _suggest(
        user,
        _paper("Second"),
        rank=2,
        run_at="2026-06-29T00:00:00",
        match=60,
        focus_areas=["Knowledge Graphs"],
    )
    first = _suggest(
        user,
        _paper("First"),
        rank=1,
        run_at="2026-06-29T00:00:00",
        match=90,
        focus_areas=["Knowledge Graphs"],
        per_interest={"Knowledge Graphs": 0.82},
    )

    client.force_authenticate(user)
    resp = client.get("/api/daily-report/")

    assert resp.status_code == 200
    assert resp.data["generated_at"] == "2026-06-29T00:00:00"
    titles = [s["title"] for s in resp.data["suggestions"]]
    assert titles == ["First", "Second"]  # latest run only, rank order
    assert old.content.metadata["title"] == "Old"  # excluded
    top = resp.data["suggestions"][0]
    assert {
        "headline",
        "reason",
        "source",
        "url",
        "venue",
        "year",
        "verdict",
        "position",
        "embedding_match",
        "abstract",
        "per_interest",
        "matched_interests",
    } <= set(top)
    assert top["origin"] == "llm"
    # Old rows may carry a model-invented "headline" rename in signals; the API
    # always serves the paper's real title instead.
    assert top["headline"] == "First"
    assert top["verdict"] == "read"
    # The transformer cosine match is exposed as a whole percent for the tail badge.
    assert top["embedding_match"] == 72
    # The page reads the abstract, the per-interest fusion scores, and the
    # matched interest labels (chips) straight off the suggestion.
    assert top["abstract"] == "Abstract of First"
    assert top["per_interest"] == {"Knowledge Graphs": 0.82}
    assert top["matched_interests"] == ["Knowledge Graphs"]
    assert first.signals["rank"] == 1

    # The daily summary rolls up today's suggested papers (latest run only).
    summary = resp.data["summary"]
    assert summary["paper_count"] == 2
    assert summary["strong_matches"] == 1  # only the 90% match clears the bar
    assert summary["verdict_counts"]["read"] >= 1
    assert summary["verdict_counts"]["skim"] >= 1
    assert summary["themes"] == ["Knowledge Graphs"]
    # The summary frames the count against the configurable match threshold.
    assert isinstance(summary["match_threshold"], int)
    # These fixtures set no pin window, so nothing is "new this week".
    assert summary["new_count"] == 0
    assert "2 papers match your interests" in summary["headline"]


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


@pytest.mark.django_db
def test_excludes_grants_and_conferences(client: APIClient) -> None:
    """Grants/conferences persist suggested rows too — they must NOT leak here."""
    user = User.objects.create_user("me", password="x")
    _suggest(user, _paper("A paper"), rank=1, run_at="2026-07-05T00:00:00")

    # A grant suggestion for the same user, from a *newer* run — it has its own
    # page (Opportunities) and must never appear in the Research Papers feed.
    grant = ContentItem.objects.create(
        type=ContentItem.Type.GRANT,
        source="pivot",
        external_id="g1",
        metadata={"title": "A grant"},
    )
    RelevanceScore.objects.create(
        content=grant,
        target_user=user,
        score=0.9,
        signals={
            "suggested": True,
            "run_at": "2026-07-06T00:00:00",  # newer than the paper run
            "rank": 1,
            "area": "grant",
        },
    )

    client.force_authenticate(user)
    resp = client.get("/api/daily-report/")

    titles = [s["title"] for s in resp.data["suggestions"]]
    assert titles == ["A paper"]
    assert resp.data["generated_at"] == "2026-07-05T00:00:00"
