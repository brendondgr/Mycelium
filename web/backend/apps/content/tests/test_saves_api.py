"""The Saves (bookmarks) endpoint: paper saves + feed-parity card payloads.

Like the opportunities API tests these read ``RelevanceScore`` /
``SavedOpportunity`` rows directly (no pgvector), so they run on SQLite.
"""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.content.models import ContentItem, RelevanceScore, SavedOpportunity


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def _paper(pid, title):
    return ContentItem.objects.create(
        type=ContentItem.Type.PAPER,
        source="openalex",
        external_id=pid,
        source_url=f"https://openalex.org/{pid}",
        metadata={
            "title": title,
            "abstract": f"Abstract for {title}.",
            "venue": "NeurIPS",
            "year": 2026,
            "authors": ["A. Researcher"],
            "pdf_url": f"https://arxiv.org/pdf/{pid}",
        },
    )


def _grant(gid, title):
    return ContentItem.objects.create(
        type=ContentItem.Type.GRANT,
        source="pivot",
        external_id=gid,
        source_url=f"https://pivot.proquest.com/funding_opps/{gid}",
        metadata={
            "title": title,
            "sponsor": "NSF",
            "amount": "$100,000",
            "website": "https://nsf.gov/x",
            "deadline_date": "2026-12-01",
            "next_kind": "application",
            "matched_topics": title,
        },
    )


def _fellowship(fid, title):
    return ContentItem.objects.create(
        type=ContentItem.Type.FELLOWSHIP,
        source="illinois",
        external_id=fid,
        source_url=f"https://example.edu/fellowships/{fid}",
        metadata={
            "title": title,
            "award_class": "fellowship",
            "description": "Supports early-stage graph researchers.",
            "eligibility": ["PhD students"],
            "facets": {"field": ["Computer Science"], "stage": ["phd"]},
        },
    )


def _score(user, item, *, rank=1, match=85):
    return RelevanceScore.objects.create(
        content=item,
        target_user=user,
        score=1.0 / rank,
        signals={
            "area": item.type,
            "run_at": "2026-07-05T00:00:00+00:00",
            "rank": rank,
            "suggested": True,
            "headline": f"Headline {rank}",
            "reason": f"Reason {rank}",
            "match_percent": match,
            "source": "llm",
        },
    )


@pytest.mark.django_db
def test_saves_requires_auth(client: APIClient):
    assert client.get("/api/saves/").status_code in (401, 403)


@pytest.mark.django_db
def test_paper_can_be_saved_and_flagged(client: APIClient):
    user = User.objects.create_user("u", password="x")
    client.force_authenticate(user)
    paper = _paper("p1", "Graph Learning Advances")
    _score(user, paper)

    # daily report starts unsaved
    report = client.get("/api/daily-report/").data
    assert report["suggestions"][0]["saved"] is False

    resp = client.post(
        "/api/opportunities/save/", {"content_id": str(paper.id)}, format="json"
    )
    assert resp.status_code == 201
    saved = SavedOpportunity.objects.get(user=user, content=paper)
    assert saved.area == SavedOpportunity.Area.PAPER
    assert saved.title == "Graph Learning Advances"
    assert saved.deadline_date is None

    # the paper feed now flags it saved
    report = client.get("/api/daily-report/").data
    assert report["suggestions"][0]["saved"] is True


@pytest.mark.django_db
def test_saves_returns_feed_parity_cards(client: APIClient):
    user = User.objects.create_user("u", password="x")
    client.force_authenticate(user)
    paper = _paper("p1", "Saved Paper")
    grant = _grant("g1", "Saved Grant")
    fellowship = _fellowship("f1", "Saved Fellowship")
    for item in (paper, grant, fellowship):
        _score(user, item)
        client.post(
            "/api/opportunities/save/", {"content_id": str(item.id)}, format="json"
        )

    items = client.get("/api/saves/").data["items"]
    by_area = {i["area"]: i for i in items}
    assert set(by_area) == {"paper", "grant", "fellowship"}

    # paper card matches the daily-report suggestion shape
    paper_card = by_area["paper"]["card"]
    assert paper_card["title"] == "Saved Paper"
    assert paper_card["venue"] == "NeurIPS"
    assert paper_card["saved"] is True

    # grant card matches the grants-feed shape
    grant_card = by_area["grant"]["card"]
    assert grant_card["sponsor"] == "NSF"
    assert grant_card["amount"] == "$100,000"
    assert grant_card["saved"] is True

    # fellowship card carries the (new) description field
    fellowship_card = by_area["fellowship"]["card"]
    assert fellowship_card["description"] == (
        "Supports early-stage graph researchers."
    )
    assert fellowship_card["saved"] is True

    # the envelope keeps the save metadata
    assert by_area["grant"]["deadline_date"] == "2026-12-01"
    assert by_area["paper"]["saved_at"]


@pytest.mark.django_db
def test_saves_falls_back_to_snapshot_after_prune(client: APIClient):
    user = User.objects.create_user("u", password="x")
    client.force_authenticate(user)
    grant = _grant("g1", "Pruned Grant")
    _score(user, grant)
    client.post(
        "/api/opportunities/save/", {"content_id": str(grant.id)}, format="json"
    )

    grant.delete()  # the daily prune removes the global item

    items = client.get("/api/saves/").data["items"]
    assert len(items) == 1
    assert items[0]["card"] is None
    assert items[0]["content_id"] is None
    assert items[0]["title"] == "Pruned Grant"


@pytest.mark.django_db
def test_fellowships_feed_includes_description(client: APIClient):
    user = User.objects.create_user("u", password="x")
    client.force_authenticate(user)
    fellowship = _fellowship("f1", "Descriptive Fellowship")
    _score(user, fellowship)

    items = client.get("/api/opportunities/fellowships/").data["items"]
    assert items[0]["description"] == "Supports early-stage graph researchers."
