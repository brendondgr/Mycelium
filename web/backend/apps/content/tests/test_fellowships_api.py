"""Fellowship feed, save, and end-to-end match tests.

Tests are SQLite-compatible (no pgvector / embeddings needed): fellowships
are scored by the deterministic rule engine, not retrieval + LLM.

Sections:
  1. API: GET /api/opportunities/fellowships/ (auth, feed shape, saved flag)
  2. Save: POST /api/opportunities/save/ accepts fellowships; DELETE unsaves.
  3. E2E match: seed real-ish records, run match_fellowships_for_user, verify
     RelevanceScore rows + signal fields.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from apps.content.models import ContentItem, RelevanceScore, SavedOpportunity
from apps.content.opportunities import match_fellowships_for_user

# ---- constants ---------------------------------------------------------------

US = "US Citizens, Nationals, or Permanent Residents"
INTL = "International Students"
SCI = "Sciences/Engineering/Math"
EARLY = "Early Years of Doctoral Program"


# ---- helpers -----------------------------------------------------------------


def _fellowship(
    eid,
    title,
    *,
    citizenship=(US, INTL),
    stage=(EARLY,),
    field=(SCI,),
    limits=(),
    deadline_type="continuous",
    deadline_date="",
    first_seen=None,
    award_class="fellowship",
    external_url=None,
):
    return ContentItem.objects.create(
        type=ContentItem.Type.FELLOWSHIP,
        source="illinois-fellowship-finder",
        external_id=eid,
        source_url=f"https://fellowship-finder.grad.illinois.edu/SearchResult/Fellowship/{eid}",
        metadata={
            "title": title,
            "award_class": award_class,
            "blurb": f"Blurb for {title}",
            "description": f"Description for {title}",
            "external_url": external_url or f"https://example.org/{eid}",
            "contact_email": "test@example.org",
            "eligibility": ["Must be enrolled in a graduate program."],
            "facets": {
                "citizenship": list(citizenship),
                "stage": list(stage),
                "field": list(field),
                "limits": list(limits),
                "award_type": ["Fellowship/Grant"],
                "other": [],
            },
            "flags": {"requires_us_citizenship": False, "open_to_international": True},
            "deadline": {
                "type": deadline_type,
                "date": deadline_date,
                "previous_date": "",
                "raw": deadline_date or deadline_type.capitalize(),
            },
            "deadline_date": deadline_date,
            "deadline_type": deadline_type,
            "next_kind": "application" if deadline_date else "",
            "status": "open",
            "status_summary": (
                f"Deadline {deadline_date}" if deadline_date else "Continuous"
            ),
            "amount_raw": "$20,000",
            "amount_kind": "exact",
            "amount_currency": "USD",
            "amount_min": 20000,
            "amount_max": 20000,
            "amount_note": "For one year.",
            "first_seen": first_seen or "2026-07-01T00:00:00+00:00",
            "last_seen": "2026-07-06T00:00:00+00:00",
            "search_text": title,
        },
    )


def _score_fellowship(
    user, item, *, rank, run_at, match, pinned_until=None, is_new=False
):
    return RelevanceScore.objects.create(
        content=item,
        target_user=user,
        score=round(match / 100, 4),
        signals={
            "area": ContentItem.Type.FELLOWSHIP,
            "run_at": run_at,
            "rank": rank,
            "suggested": True,
            "headline": "Strong eligibility match" if match >= 70 else "Possible fit",
            "reason": "US citizen / permanent resident eligible; Stage matches",
            "match_percent": match,
            "source": "rules",
            "tier": "qualified" if match >= 70 else "conditional",
            "gates_failed": [],
            "reasons": ["US citizen / permanent resident eligible"],
            "fit": match / 100,
            "is_new": is_new,
            "pinned_until": pinned_until,
            "deadline_date": (item.metadata or {}).get("deadline_date", ""),
            "next_kind": (item.metadata or {}).get("next_kind", ""),
            "status": "open",
            "status_summary": (item.metadata or {}).get("status_summary", ""),
            "first_seen": "2026-07-01T00:00:00+00:00",
        },
    )


def _profile_user_with_eligibility(username):
    user = User.objects.create_user(username, password="x")
    user.profile.interests = {
        "areas": ["Artificial Intelligence in Healthcare"],
        "eligibility": {
            "citizenship": "us",
            "stage": "doctoral_early",
            "fields": ["Sciences/Engineering/Math"],
            "eligible_restrictions": [],
        },
    }
    user.profile.institution = "Florida State University"
    user.profile.save()
    return user


# ============================================================================ #
# 1. API feed tests                                                              #
# ============================================================================ #


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.mark.django_db
def test_fellowships_requires_auth(client: APIClient):
    assert client.get("/api/opportunities/fellowships/").status_code in (401, 403)


@pytest.mark.django_db
def test_fellowships_feed_shape(client: APIClient):
    """GET /api/opportunities/fellowships/ returns required fields."""
    user = User.objects.create_user("u_feed", password="x")
    client.force_authenticate(user)
    run_at = "2026-07-06T01:00:00+00:00"

    item = _fellowship("f_api_1", "Dissertation Award", stage=(EARLY,))
    _score_fellowship(user, item, rank=1, run_at=run_at, match=82)

    resp = client.get("/api/opportunities/fellowships/")
    assert resp.status_code == 200

    items = resp.data["items"]
    assert len(items) == 1
    f = items[0]

    # Required fields from the plan's contract
    required = [
        "content_id", "url", "score", "match_percent", "rank",
        "headline", "reason", "origin", "is_new", "pinned",
        "deadline_date", "deadline_kind", "status_summary", "saved",
        "title", "award_class", "amount", "amount_note", "deadline_type",
        "fields", "stages", "citizenship", "award_types", "limits",
        "eligibility", "contact_email", "posted", "tier", "gates_failed",
        "reasons", "fit",
    ]
    for field_name in required:
        assert field_name in f, f"Missing field: {field_name}"

    assert f["title"] == "Dissertation Award"
    assert f["award_class"] == "fellowship"
    assert f["amount"] == "$20,000"
    assert f["tier"] == "qualified"
    assert f["origin"] == "rules"
    assert f["url"] == "https://example.org/f_api_1"
    assert f["contact_email"] == "test@example.org"
    assert f["saved"] is False


@pytest.mark.django_db
def test_fellowships_feed_latest_run_only(client: APIClient):
    user = User.objects.create_user("u_latest", password="x")
    client.force_authenticate(user)
    old_item = _fellowship("f_old", "Old Fellowship")
    new_item = _fellowship("f_new", "New Fellowship")
    _score_fellowship(user, old_item, rank=1, run_at="2026-07-01T00:00:00", match=80)
    _score_fellowship(user, new_item, rank=1, run_at="2026-07-06T00:00:00", match=75)

    items = client.get("/api/opportunities/fellowships/").data["items"]
    assert [i["title"] for i in items] == ["New Fellowship"]


@pytest.mark.django_db
def test_fellowships_feed_pinned_floats_first(client: APIClient):
    user = User.objects.create_user("u_pin", password="x")
    client.force_authenticate(user)
    run_at = "2026-07-06T01:00:00+00:00"
    future = (timezone.now().date() + timedelta(days=5)).isoformat()

    top = _fellowship("f_top", "Top Ranked Fellowship")
    pinned = _fellowship("f_pinned", "Brand New Fellowship")
    _score_fellowship(user, top, rank=1, run_at=run_at, match=90)
    _score_fellowship(
        user, pinned, rank=3, run_at=run_at, match=80, pinned_until=future, is_new=True
    )

    items = client.get("/api/opportunities/fellowships/").data["items"]
    assert items[0]["content_id"] == str(pinned.id)
    assert items[0]["is_new"] is True
    assert items[1]["content_id"] == str(top.id)


# ============================================================================ #
# 2. Save tests                                                                  #
# ============================================================================ #


@pytest.mark.django_db
def test_save_fellowship_creates_deadline_entry(client: APIClient):
    user = User.objects.create_user("u_save", password="x")
    client.force_authenticate(user)
    soon = (timezone.now().date() + timedelta(days=5)).isoformat()
    item = _fellowship(
        "f_save", "Save Test Fellowship", deadline_type="true", deadline_date=soon
    )

    resp = client.post(
        "/api/opportunities/save/", {"content_id": str(item.id)}, format="json"
    )
    assert resp.status_code == 201
    assert SavedOpportunity.objects.filter(user=user, content=item).exists()

    saved = SavedOpportunity.objects.get(user=user, content=item)
    assert saved.area == SavedOpportunity.Area.FELLOWSHIP
    assert saved.title == "Save Test Fellowship"
    assert saved.subtitle == "Fellowship"   # award_class title-cased

    # Appears on deadlines page
    deadlines = client.get("/api/deadlines/").data["items"]
    assert any(d["title"] == "Save Test Fellowship" for d in deadlines)


@pytest.mark.django_db
def test_unsave_fellowship(client: APIClient):
    user = User.objects.create_user("u_unsave", password="x")
    client.force_authenticate(user)
    item = _fellowship("f_unsave", "Unsave Test Fellowship")
    client.post("/api/opportunities/save/", {"content_id": str(item.id)}, format="json")
    assert SavedOpportunity.objects.filter(user=user, content=item).exists()

    resp = client.delete(f"/api/opportunities/save/{item.id}/")
    assert resp.status_code == 204
    assert not SavedOpportunity.objects.filter(user=user, content=item).exists()


@pytest.mark.django_db
def test_save_fellowship_saved_flag_in_feed(client: APIClient):
    user = User.objects.create_user("u_savedflag", password="x")
    client.force_authenticate(user)
    run_at = "2026-07-06T01:00:00+00:00"
    item = _fellowship("f_flag", "Flag Test Fellowship")
    _score_fellowship(user, item, rank=1, run_at=run_at, match=80)

    feed_url = "/api/opportunities/fellowships/"
    assert client.get(feed_url).data["items"][0]["saved"] is False
    client.post("/api/opportunities/save/", {"content_id": str(item.id)}, format="json")
    assert client.get(feed_url).data["items"][0]["saved"] is True


@pytest.mark.django_db
def test_save_rejects_unknown_fellowship(client: APIClient):
    import uuid

    user = User.objects.create_user("u_reject", password="x")
    client.force_authenticate(user)
    resp = client.post(
        "/api/opportunities/save/", {"content_id": str(uuid.uuid4())}, format="json"
    )
    assert resp.status_code == 404


# ============================================================================ #
# 3. E2E match: seed real-ish records, run rule engine, check signals           #
# ============================================================================ #

# Five fellowship records seeded from real fellowships.json data (by hand).
_SEED_RECORDS = [
    {
        "eid": "3231",
        "title": "American Heart Association (AHA) - Predoctoral Fellowship",
        "award_class": "fellowship",
        "citizenship": (US, INTL),
        "stage": (EARLY, "Dissertation Research", "Dissertation Write-Up"),
        "field": (SCI,),
        "limits": (),
        "deadline_type": "true",
        "deadline_date": "2026-08-04",
    },
    {
        "eid": "4137",
        "title": "American Heraldry Society - William Barton Graduate Scholarship",
        "award_class": "scholarship",
        "citizenship": (US, INTL),
        "stage": ("Master's", "Dissertation Research", "Dissertation Write-Up"),
        # field mismatch -> conditional:
        "field": ("Social Sciences", "Fine Arts", "Humanities"),
        "limits": (),
        "deadline_type": "true",
        "deadline_date": "2026-07-31",
    },
    {
        "eid": "3998",
        "title": "American Heart Association (AHA) - Postdoctoral Fellowship",
        "award_class": "fellowship",
        "citizenship": (US, INTL),
        "stage": ("Postdoctoral/Post-graduate",),   # stage mismatch -> conditional
        "field": (SCI,),
        "limits": (),
        "deadline_type": "true",
        "deadline_date": "2026-08-04",
    },
    {
        "eid": "9999",
        "title": "Illinois-Only Award",
        "award_class": "fellowship",
        "citizenship": (US, INTL),
        "stage": (EARLY,),
        "field": (SCI,),
        "limits": ("University of Illinois Students",),  # hard gate -> not_eligible
        "deadline_type": "continuous",
        "deadline_date": "",
    },
    {
        "eid": "8888",
        "title": "Continuous Open Fellowship",
        "award_class": "fellowship",
        "citizenship": (US, INTL),
        "stage": (),  # no stage restriction -> qualified
        "field": (SCI,),
        "limits": (),
        "deadline_type": "continuous",
        "deadline_date": "",
    },
]


@pytest.mark.django_db
def test_fellowships_e2e_match_and_signals():
    """Seed 5 records, run match_fellowships_for_user, verify RelevanceScore rows."""
    user = _profile_user_with_eligibility("e2e_user")

    # Seed content items
    for rec in _SEED_RECORDS:
        ContentItem.objects.create(
            type=ContentItem.Type.FELLOWSHIP,
            source="illinois-fellowship-finder",
            external_id=rec["eid"],
            metadata={
                "title": rec["title"],
                "award_class": rec["award_class"],
                "facets": {
                    "citizenship": list(rec["citizenship"]),
                    "stage": list(rec["stage"]),
                    "field": list(rec["field"]),
                    "limits": list(rec["limits"]),
                    "award_type": ["Fellowship/Grant"],
                    "other": [],
                },
                "flags": {
                    "requires_us_citizenship": False, "open_to_international": True
                },
                "deadline": {
                    "type": rec["deadline_type"],
                    "date": rec["deadline_date"],
                    "previous_date": "",
                    "raw": rec["deadline_date"] or rec["deadline_type"].capitalize(),
                },
                "deadline_date": rec["deadline_date"],
                "next_kind": "application" if rec["deadline_date"] else "",
                "status": "open",
                "status_summary": (
                    f"Deadline {rec['deadline_date']}"
                    if rec["deadline_date"]
                    else "Continuous"
                ),
                "first_seen": "2026-07-01T00:00:00+00:00",
                "last_seen": "2026-07-06T00:00:00+00:00",
            },
        )

    result = match_fellowships_for_user(
        user, today="2026-07-06", persist=True
    )

    assert result.status == "ok"
    assert result.retrieved == 5     # 5 items loaded from corpus
    # Illinois-only (not_eligible) should be excluded from suggestions
    assert result.suggestions <= 4

    scores = list(
        RelevanceScore.objects.filter(
            target_user=user, content__type=ContentItem.Type.FELLOWSHIP
        ).select_related("content")
    )
    assert len(scores) == result.suggestions
    assert len(scores) >= 3   # at least AHA pre-doctoral, AHA post-doctoral, continuous

    # Every persisted score has the expected signal keys.
    required_signal_keys = {
        "area", "run_at", "suggested", "is_new", "pinned_until",
        "first_seen", "deadline_date", "next_kind", "status", "status_summary",
        "rank", "headline", "reason", "match_percent", "source",
        "tier", "gates_failed", "reasons", "fit",
    }
    for score in scores:
        missing = required_signal_keys - set(score.signals.keys())
        title = score.content.metadata["title"]
        assert not missing, f"Score {title!r} missing signals: {missing}"
        assert score.signals["area"] == ContentItem.Type.FELLOWSHIP
        assert score.signals["source"] == "rules"
        assert score.signals["tier"] in ("qualified", "conditional")
        assert isinstance(score.signals["rank"], int)
        assert score.signals["rank"] >= 1

    # Qualified items rank above conditional items.
    def _tier(score):
        return score.signals["tier"]

    qualified_ranks = [s.signals["rank"] for s in scores if _tier(s) == "qualified"]
    conditional_ranks = [s.signals["rank"] for s in scores if _tier(s) == "conditional"]
    if qualified_ranks and conditional_ranks:
        assert max(qualified_ranks) < min(conditional_ranks)

    # Illinois-only not persisted.
    illinois_ids = {
        str(ci.id)
        for ci in ContentItem.objects.filter(
            external_id="9999", type=ContentItem.Type.FELLOWSHIP
        )
    }
    score_ids = {str(s.content_id) for s in scores}
    assert illinois_ids.isdisjoint(score_ids)

    # Re-running overwrites, not duplicates.
    before = len(scores)
    match_fellowships_for_user(user, today="2026-07-06", persist=True)
    after = RelevanceScore.objects.filter(
        target_user=user, content__type=ContentItem.Type.FELLOWSHIP
    ).count()
    assert after == before
