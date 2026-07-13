"""Opportunities, save, deadlines, and notifications endpoints (auth-gated).

These need no pgvector — they read the ``RelevanceScore`` / ``SavedOpportunity``
rows the matcher persists, so they run on SQLite.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from apps.content.models import ContentItem, RelevanceScore, SavedOpportunity


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def _grant(gid, title, *, deadline="2026-12-01", first_seen=None):
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
            "deadline_date": deadline,
            "next_kind": "application",
            "matched_topics": title,
            "search_text": title,
            "first_seen": first_seen or "2026-07-05T00:00:00+00:00",
            "status_summary": f"Application due {deadline}",
        },
    )


def _score(
    user, item, *, rank, run_at, match, pinned_until=None, is_new=False, suggested=True
):
    return RelevanceScore.objects.create(
        content=item,
        target_user=user,
        score=1.0 / rank,
        signals={
            "area": item.type,
            "run_at": run_at,
            "rank": rank,
            "suggested": suggested,
            "headline": f"Headline {rank}",
            "reason": f"Reason {rank}",
            "match_percent": match,
            "source": "llm",
            "is_new": is_new,
            "pinned_until": pinned_until,
            "deadline_date": (item.metadata or {}).get("deadline_date", ""),
            "next_kind": (item.metadata or {}).get("next_kind", ""),
            "status_summary": (item.metadata or {}).get("status_summary", ""),
        },
    )


@pytest.mark.django_db
def test_grants_requires_auth(client: APIClient):
    assert client.get("/api/opportunities/grants/").status_code in (401, 403)


@pytest.mark.django_db
def test_grants_feed_pins_new_high_fit_first(client: APIClient):
    user = User.objects.create_user("brendon", password="x")
    client.force_authenticate(user)
    run_at = "2026-07-05T01:00:00+00:00"
    future = (timezone.now().date() + timedelta(days=5)).isoformat()

    top = _grant("g_top", "Knowledge Graphs Award")
    pinned = _grant("g_pinned", "Brand New Agentic AI Award")
    _score(user, top, rank=1, run_at=run_at, match=88)
    _score(
        user, pinned, rank=3, run_at=run_at, match=80, pinned_until=future, is_new=True
    )

    resp = client.get("/api/opportunities/grants/")
    assert resp.status_code == 200
    items = resp.data["items"]
    # The pinned "New" item floats above the higher-ranked unpinned one.
    assert items[0]["content_id"] == str(pinned.id)
    assert items[0]["is_new"] is True
    assert items[0]["pinned"] is True
    assert items[0]["amount"] == "$100,000"
    assert items[1]["content_id"] == str(top.id)
    assert items[1]["is_new"] is False


@pytest.mark.django_db
def test_grants_feed_accumulates_across_runs(client: APIClient):
    """Opportunities accumulate: an earlier run's match stays in the feed alongside
    a later run's, since the daily job scores only new items and appends them."""
    user = User.objects.create_user("u", password="x")
    client.force_authenticate(user)
    _score(user, _grant("old", "Old"), rank=1, run_at="2026-07-01T00:00:00", match=90)
    _score(user, _grant("new", "New"), rank=1, run_at="2026-07-05T00:00:00", match=70)

    items = client.get("/api/opportunities/grants/").data["items"]
    # Both runs' matches are present; unpinned rows order by match strength, so the
    # older-but-stronger grant leads. generated_at reflects the most recent run.
    assert [i["title"] for i in items] == ["Old", "New"]


@pytest.mark.django_db
def test_grants_feed_excludes_suggested_false(client: APIClient):
    """A latest-run row persisted below the match floor (``suggested=False``) is
    never returned by the feed, even though it is the latest run."""
    user = User.objects.create_user("u_hidden", password="x")
    client.force_authenticate(user)
    run_at = "2026-07-05T00:00:00+00:00"
    _score(
        user, _grant("visible", "Visible Grant"), rank=1, run_at=run_at, match=80
    )
    _score(
        user,
        _grant("hidden", "Hidden Grant"),
        rank=2,
        run_at=run_at,
        match=10,
        suggested=False,
    )

    items = client.get("/api/opportunities/grants/").data["items"]
    assert [i["title"] for i in items] == ["Visible Grant"]


@pytest.mark.django_db
def test_save_and_unsave_roundtrip_and_deadlines(client: APIClient):
    user = User.objects.create_user("u", password="x")
    client.force_authenticate(user)
    soon = (timezone.now().date() + timedelta(days=3)).isoformat()
    item = _grant("g1", "Amazon Award", deadline=soon)

    # saved flag starts false
    _score(user, item, rank=1, run_at="2026-07-05T00:00:00", match=90)
    assert client.get("/api/opportunities/grants/").data["items"][0]["saved"] is False

    resp = client.post(
        "/api/opportunities/save/", {"content_id": str(item.id)}, format="json"
    )
    assert resp.status_code == 201
    assert SavedOpportunity.objects.filter(user=user, content=item).exists()

    # now flagged saved, and it shows on the deadlines feed with days_remaining
    assert client.get("/api/opportunities/grants/").data["items"][0]["saved"] is True
    deadlines = client.get("/api/deadlines/").data["items"]
    assert len(deadlines) == 1
    assert deadlines[0]["title"] == "Amazon Award"
    assert deadlines[0]["days_remaining"] == 3
    assert deadlines[0]["within_week"] is True

    # unsave
    resp = client.delete(f"/api/opportunities/save/{item.id}/")
    assert resp.status_code == 204
    assert not SavedOpportunity.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_saved_deadline_survives_content_prune(client: APIClient):
    user = User.objects.create_user("u", password="x")
    client.force_authenticate(user)
    item = _grant("g1", "Expiring Award", deadline="2026-07-08")
    client.post("/api/opportunities/save/", {"content_id": str(item.id)}, format="json")

    item.delete()  # the daily prune removes the global item

    deadlines = client.get("/api/deadlines/").data["items"]
    assert len(deadlines) == 1  # snapshot survives
    assert deadlines[0]["title"] == "Expiring Award"
    assert deadlines[0]["content_id"] is None


@pytest.mark.django_db
def test_notifications_lists_only_within_week(client: APIClient):
    user = User.objects.create_user("u", password="x")
    client.force_authenticate(user)
    today = timezone.now().date()

    def _save(gid, days):
        item = _grant(gid, gid, deadline=(today + timedelta(days=days)).isoformat())
        client.post(
            "/api/opportunities/save/", {"content_id": str(item.id)}, format="json"
        )

    _save("soon", 4)  # within a week -> alert
    _save("far", 30)  # too far -> no alert

    resp = client.get("/api/notifications/")
    assert resp.status_code == 200
    assert resp.data["count"] == 1
    assert resp.data["items"][0]["title"] == "soon"
    assert resp.data["items"][0]["days_remaining"] == 4
    assert "less than a week" in resp.data["items"][0]["message"]


@pytest.mark.django_db
def test_save_rejects_unknown_item(client: APIClient):
    user = User.objects.create_user("u", password="x")
    client.force_authenticate(user)
    import uuid

    resp = client.post(
        "/api/opportunities/save/", {"content_id": str(uuid.uuid4())}, format="json"
    )
    assert resp.status_code == 404
