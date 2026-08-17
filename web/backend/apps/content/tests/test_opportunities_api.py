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


def _conference(cid, title, *, deadline="2026-12-01", prune_after=None):
    """A minimal open-collector-shaped conference row (plan Phase 9 fields).

    ``prune_after`` defaults to the deadline because ``map_conference`` always
    writes the key — a conference with none at all is the dateless case
    :mod:`apps.content.liveness` deliberately hides, so a fixture omitting it
    would silently test the wrong thing.
    """
    return ContentItem.objects.create(
        type=ContentItem.Type.CONFERENCE,
        source="conf:ccf_deadlines",
        external_id=cid,
        source_url="https://sigmod.org/2026",
        metadata={
            "name": title,
            "acronym": "SIGMOD",
            "year_label": "2026",
            "website": "https://sigmod.org/2026",
            "deadline_date": deadline,
            "prune_after": deadline if prune_after is None else prune_after,
            "next_kind": "abstract",
            "rankings": {
                "ccf": {"rank": "A", "edition": ""},
                "core": {"rank": "A*", "edition": ""},
            },
            "rank_badges": [
                {"system": "ccf", "rank": "A", "edition": ""},
                {"system": "core", "rank": "A*", "edition": ""},
            ],
            "red_flags": [],
            "quality_warnings": ["only a notification date is on record"],
            "deadlines_structured": [
                {
                    "kind": "abstract",
                    "raw": "2026-01-10 23:59:00 AoE",
                    "instant": "2026-01-10T23:59:00+00:00",
                    "basis": "AoE",
                    "round_label": "round 1",
                    "source": "conf:ccf_deadlines",
                    "is_estimated": False,
                    "extension_count": 0,
                }
            ],
            "license": "MIT",
            "source_links": [
                {"source": "ccf_deadlines", "url": "https://sigmod.org/2026"}
            ],
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
def test_notifications_serve_the_notification_model(client: APIClient):
    # Reminders rework (D-2/D-3): the bell reads Notification rows, and *saving*
    # no longer produces an alert — a reminder created from a save does.
    from apps.content.models import Notification

    user = User.objects.create_user("u", password="x")
    client.force_authenticate(user)

    item = _grant("g", "g", deadline="2026-12-01")
    client.post(
        "/api/opportunities/save/", {"content_id": str(item.id)}, format="json"
    )

    # A save alone: no notification.
    resp = client.get("/api/notifications/")
    assert resp.status_code == 200
    assert resp.data["count"] == 0

    note = Notification.objects.create(
        user=user,
        kind=Notification.Kind.REMINDER,
        content=item,
        title="Grant reminder",
        body="Application due Dec 1 — 7 days left",
        dedupe_key="reminder:test:1",
    )
    resp = client.get("/api/notifications/")
    assert resp.data["count"] == 1
    assert resp.data["items"][0]["kind"] == "reminder"
    assert resp.data["items"][0]["title"] == "Grant reminder"

    # Dismiss clears it from the count.
    dismiss = client.post(
        f"/api/notifications/{note.id}/action/", {"action": "dismiss"}, format="json"
    )
    assert dismiss.status_code == 200
    assert client.get("/api/notifications/").data["count"] == 0


@pytest.mark.django_db
def test_save_rejects_unknown_item(client: APIClient):
    user = User.objects.create_user("u", password="x")
    client.force_authenticate(user)
    import uuid

    resp = client.post(
        "/api/opportunities/save/", {"content_id": str(uuid.uuid4())}, format="json"
    )
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# Open-collector provenance + quality fields (plan Phase 9)
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_grants_feed_exposes_open_collector_provenance(client: APIClient):
    """Every field the open collector adds that Pivot never carried round-trips
    through the feed, and ``posted`` prefers the funder's own
    ``metadata["published_on"]`` over Mylo's ingest date."""
    user = User.objects.create_user("prov", password="x")
    client.force_authenticate(user)
    item = ContentItem.objects.create(
        type=ContentItem.Type.GRANT,
        source="grants:nsf",
        external_id="g-prov",
        source_url="https://www.nsf.gov/funding/x",
        metadata={
            "title": "Coastal Ecosystems",
            "sponsor": "NSF",
            "amount": "$50,000",
            "website": "https://www.nsf.gov/funding/x",
            "deadline_date": "2026-12-01",
            "next_kind": "application",
            "opportunity_number": "PAR-25-144",
            "due_dates": ["2026-02-01", "2026-06-01", "2026-12-01"],
            "deadline_text": "Standard NSF cycle",
            "dates_inferred": False,
            "original_deadline": "2026-02-01",
            "loi_date": "2026-01-01",
            "published_on": "2015-03-02",
            "license": (
                "US Government Work — no copyright (17 U.S.C. § 105); "
                "public domain"
            ),
            "contributing_sources": ["nsf"],
        },
    )
    _score(user, item, rank=1, run_at="2026-07-05T00:00:00+00:00", match=88)

    data = client.get("/api/opportunities/grants/").data["items"][0]
    assert data["source"] == "grants:nsf"
    assert data["license"].startswith("US Government Work")
    assert data["license_url"] == ""
    assert data["source_links"] == [
        {"source": "nsf", "url": "https://www.nsf.gov/funding/x"}
    ]
    assert data["opportunity_number"] == "PAR-25-144"
    assert data["due_dates"] == ["2026-02-01", "2026-06-01", "2026-12-01"]
    assert data["deadline_text"] == "Standard NSF cycle"
    assert data["dates_inferred"] is False
    assert data["original_deadline"] == "2026-02-01"
    assert data["loi_date"] == "2026-01-01"
    assert data["published_on"] == "2015-03-02"
    assert data["posted"] == "2015-03-02"


@pytest.mark.django_db
def test_grants_feed_posted_falls_back_without_published_on(client: APIClient):
    """A pre-migration row that carries no ``metadata["published_on"]`` keeps
    reading Mylo's own ingest date from ``signals["first_seen"]`` — the exact
    behaviour ``get_posted`` had before the Phase 9 repoint, preserved as the
    fallback rather than dropped."""
    user = User.objects.create_user("legacy", password="x")
    client.force_authenticate(user)
    item = _grant("legacy", "Legacy Pivot Grant")  # no metadata["published_on"]
    RelevanceScore.objects.create(
        content=item,
        target_user=user,
        score=1.0,
        signals={
            "run_at": "2026-07-05T00:00:00+00:00",
            "rank": 1,
            "suggested": True,
            "match_percent": 70,
            "first_seen": "2026-01-02T00:00:00+00:00",
        },
    )

    data = client.get("/api/opportunities/grants/").data["items"][0]
    assert data["published_on"] == ""
    assert data["posted"] == "2026-01-02T00:00:00+00:00"


@pytest.mark.django_db
def test_conferences_feed_exposes_ranking_fields(client: APIClient):
    user = User.objects.create_user("conf_prov", password="x")
    client.force_authenticate(user)
    item = _conference("c-prov", "ACM Conference on Management of Data")
    _score(user, item, rank=1, run_at="2026-07-05T00:00:00+00:00", match=90)

    data = client.get("/api/opportunities/conferences/").data["items"][0]
    assert data["acronym"] == "SIGMOD"
    assert data["year_label"] == "2026"
    assert "trust_tier" not in data
    assert data["rank_badges"] == [
        {"system": "ccf", "rank": "A", "edition": ""},
        {"system": "core", "rank": "A*", "edition": ""},
    ]
    assert data["rankings"]["ccf"]["rank"] == "A"
    assert data["quality_warnings"] == ["only a notification date is on record"]
    assert data["deadlines_structured"][0]["kind"] == "abstract"
    assert data["source"] == "conf:ccf_deadlines"
    assert data["license"] == "MIT"
    assert data["source_links"] == [
        {"source": "ccf_deadlines", "url": "https://sigmod.org/2026"}
    ]


@pytest.mark.django_db
def test_conferences_feed_degrades_safely_when_series_unresolved(client: APIClient):
    """A series the resolve stage never matched carries no rank badges — the
    card must simply show none, and attribution degrades to an empty list
    rather than guessing."""
    user = User.objects.create_user("conf_unres", password="x")
    client.force_authenticate(user)
    item = ContentItem.objects.create(
        type=ContentItem.Type.CONFERENCE,
        source="conf:society_pages",
        external_id="c-unres",
        source_url="https://example.org",
        metadata={"name": "An Unresolved Venue", "prune_after": "2026-12-01"},
    )
    _score(user, item, rank=1, run_at="2026-07-05T00:00:00+00:00", match=60)

    data = client.get("/api/opportunities/conferences/").data["items"][0]
    assert data["rank_badges"] == []
    assert data["source_links"] == []


@pytest.mark.django_db
def test_ranking_reference_endpoint_covers_every_system(client: APIClient):
    """The static hover-copy table (plan Phase 9): every rank the live corpus
    can carry has an explanation."""
    user = User.objects.create_user("ref", password="x")
    client.force_authenticate(user)

    resp = client.get("/api/opportunities/ranking-reference/")
    assert resp.status_code == 200
    assert set(resp.data["rank_systems"]) == {"ccf", "core", "thcpl"}
    assert set(resp.data["rank_explanations"]["ccf"]) == {"A", "B", "C"}
    assert set(resp.data["rank_explanations"]["core"]) == {"A*", "A", "B", "C"}
    assert set(resp.data["rank_explanations"]["thcpl"]) == {"A", "B"}
    assert "trust_tiers" not in resp.data


@pytest.mark.django_db
def test_ranking_reference_requires_auth(client: APIClient):
    assert client.get("/api/opportunities/ranking-reference/").status_code in (401, 403)
