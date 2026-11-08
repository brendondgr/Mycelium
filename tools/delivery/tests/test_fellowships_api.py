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

import json
import math
from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.utils import timezone
from rest_framework.test import APIClient

from tools.delivery.models import SavedOpportunity
from tools.recommendation.models import RelevanceScore
from tools.recommendation.opportunities import match_fellowships_for_user
from tools.retrieval import embeddings
from tools.retrieval.models import ContentItem

# ---- fixtures ------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _open_match_floor(settings):
    """Surface every eligible fellowship by default, isolating these tests from the
    production ``OPPORTUNITY_MIN_MATCH_PERCENT`` floor. The dedicated floor test
    overrides its own value."""
    settings.OPPORTUNITY_MIN_MATCH_PERCENT = 0


@pytest.fixture(autouse=True)
def _reset_embedder():
    """No embedder by default (the rule-only / no-embedding-signal path); the
    dedicated embedding-match tests install a fake one via ``embeddings.set_embedder``.
    """
    embeddings.reset_embedder()
    yield
    embeddings.reset_embedder()


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
    user,
    item,
    *,
    rank,
    run_at,
    match,
    pinned_until=None,
    is_new=False,
    suggested=True,
    embedding_match=None,
    rule_fit=None,
):
    signals = {
        "area": ContentItem.Type.FELLOWSHIP,
        "run_at": run_at,
        "rank": rank,
        "suggested": suggested,
        "headline": "Strong eligibility match" if match >= 70 else "Possible fit",
        "reason": "US citizen / permanent resident eligible; Stage matches",
        "match_percent": match,
        "source": "rules",
        "tier": "qualified" if match >= 70 else "conditional",
        "gates_failed": [],
        "reasons": ["US citizen / permanent resident eligible"],
        "fit": match / 100,
        "rule_fit": rule_fit if rule_fit is not None else match / 100,
        "is_new": is_new,
        "pinned_until": pinned_until,
        "deadline_date": (item.metadata or {}).get("deadline_date", ""),
        "next_kind": (item.metadata or {}).get("next_kind", ""),
        "status": "open",
        "status_summary": (item.metadata or {}).get("status_summary", ""),
        "first_seen": "2026-07-01T00:00:00+00:00",
    }
    if embedding_match is not None:
        signals["embedding_match"] = embedding_match
    return RelevanceScore.objects.create(
        content=item,
        target_user=user,
        score=round(match / 100, 4),
        signals=signals,
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
        "content_id", "url", "score", "verdict", "position", "position_of",
        "rank",
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
def test_fellowships_feed_accumulates_across_runs(client: APIClient):
    """Fellowships accumulate like the other opportunity feeds: an earlier run's
    eligible match stays alongside a later run's, ordered by match strength."""
    user = User.objects.create_user("u_latest", password="x")
    client.force_authenticate(user)
    old_item = _fellowship("f_old", "Old Fellowship")
    new_item = _fellowship("f_new", "New Fellowship")
    _score_fellowship(user, old_item, rank=1, run_at="2026-07-01T00:00:00", match=80)
    _score_fellowship(user, new_item, rank=1, run_at="2026-07-06T00:00:00", match=75)

    items = client.get("/api/opportunities/fellowships/").data["items"]
    # Both runs' eligible matches show; unpinned rows order by match strength.
    assert [i["title"] for i in items] == ["Old Fellowship", "New Fellowship"]


@pytest.mark.django_db
def test_fellowships_feed_excludes_suggested_false(client: APIClient):
    """A latest-run row persisted below the match floor (``suggested=False``) is
    never returned by the feed, even though it is the latest run."""
    user = User.objects.create_user("u_hidden", password="x")
    client.force_authenticate(user)
    run_at = "2026-07-06T01:00:00+00:00"

    visible = _fellowship("f_visible", "Visible Fellowship")
    hidden = _fellowship("f_hidden", "Hidden Fellowship")
    _score_fellowship(user, visible, rank=1, run_at=run_at, match=80)
    _score_fellowship(
        user, hidden, rank=2, run_at=run_at, match=10, suggested=False
    )

    items = client.get("/api/opportunities/fellowships/").data["items"]
    assert [i["title"] for i in items] == ["Visible Fellowship"]


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


@pytest.mark.django_db
def test_fellowships_feed_includes_description_and_embedding_match(client: APIClient):
    """The payload exposes ``description`` (Phase B, like GrantSerializer) and
    ``embedding_match`` (0-100, via the shared ``_OpportunitySerializer``)."""
    user = User.objects.create_user("u_desc", password="x")
    client.force_authenticate(user)
    run_at = "2026-07-06T01:00:00+00:00"

    item = _fellowship("f_desc", "Description Fellowship")
    _score_fellowship(
        user, item, rank=1, run_at=run_at, match=82, embedding_match=0.82
    )

    f = client.get("/api/opportunities/fellowships/").data["items"][0]
    assert f["description"] == "Description for Description Fellowship"
    assert f["embedding_match"] == 82


@pytest.mark.django_db
def test_fellowships_feed_description_falls_back_to_blurb(client: APIClient):
    """No ``description`` in metadata -> the shorter ``blurb`` is used instead."""
    user = User.objects.create_user("u_blurb", password="x")
    client.force_authenticate(user)
    run_at = "2026-07-06T01:00:00+00:00"

    item = _fellowship("f_blurb", "Blurb Only Fellowship")
    item.metadata["description"] = ""
    item.metadata["blurb"] = "  Extra   whitespace   blurb  "
    item.save(update_fields=["metadata"])
    _score_fellowship(user, item, rank=1, run_at=run_at, match=80)

    f = client.get("/api/opportunities/fellowships/").data["items"][0]
    assert f["description"] == "Extra whitespace blurb"


@pytest.mark.django_db
def test_fellowships_feed_embedding_match_absent_without_signal(client: APIClient):
    """A rule-only row (no embedding signal at match time) reports ``embedding_match``
    as ``None`` — the same "not applicable" contract grants/conferences use."""
    user = User.objects.create_user("u_noembed", password="x")
    client.force_authenticate(user)
    run_at = "2026-07-06T01:00:00+00:00"

    item = _fellowship("f_noembed", "No Signal Fellowship")
    _score_fellowship(user, item, rank=1, run_at=run_at, match=80)

    f = client.get("/api/opportunities/fellowships/").data["items"][0]
    assert f["embedding_match"] is None


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

    # complete=lambda _p: None -> model unavailable, so the rule-engine summary is
    # the fallback reason (source="rules"); keeps this test offline + deterministic.
    result = match_fellowships_for_user(
        user, today="2026-07-06", persist=True, complete=lambda _p: None
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
        "rank", "headline", "reason", "verdict", "source",
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
    match_fellowships_for_user(
        user, today="2026-07-06", persist=True, complete=lambda _p: None
    )
    after = RelevanceScore.objects.filter(
        target_user=user, content__type=ContentItem.Type.FELLOWSHIP
    ).count()
    assert after == before


def _seed_fellowship_corpus() -> None:
    """Create the five _SEED_RECORDS fellowship ContentItems (shared by e2e tests)."""
    for rec in _SEED_RECORDS:
        ContentItem.objects.create(
            type=ContentItem.Type.FELLOWSHIP,
            source="illinois-fellowship-finder",
            external_id=rec["eid"],
            metadata={
                "title": rec["title"],
                "award_class": rec["award_class"],
                "description": f"Supports research aligned with {rec['title']}.",
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


@pytest.mark.django_db
def test_fellowships_e2e_llm_report():
    """With the model available, the top eligible fellowships get an LLM report.

    The rule engine still gates eligibility (Illinois-only stays excluded, tier
    is preserved), but the surfaced reason is Mylo's tailored text (source="llm")
    rather than the concatenated eligibility summary.
    """
    user = _profile_user_with_eligibility("e2e_llm_user")
    _seed_fellowship_corpus()

    def fake_complete(prompt: str) -> str:
        # A tailored, multi-sentence report for each candidate the prompt lists.
        rows = ", ".join(
            f'{{"item": {i}, "match": 90, "headline": "Great Fit {i}", '
            f'"reason": "This aligns with your neuroscience research. It supports '
            f'your imaging methods. You could fund your dissertation work."}}'
            for i in range(1, 6)
        )
        return '{"suggestions": [' + rows + "]}"

    result = match_fellowships_for_user(
        user, today="2026-07-06", persist=True, complete=fake_complete
    )
    assert result.status == "ok"
    assert result.llm >= 1  # at least one report authored by the model

    scores = list(
        RelevanceScore.objects.filter(
            target_user=user, content__type=ContentItem.Type.FELLOWSHIP
        ).select_related("content")
    )
    llm_scores = [s for s in scores if s.signals["source"] == "llm"]
    assert llm_scores, "expected at least one LLM-authored fellowship report"

    top = llm_scores[0]
    # No percent survives persistence — the reader gets a verdict instead.
    assert top.signals["match_percent"] is None
    # A genuine multi-sentence report, not a one-line eligibility summary.
    assert top.signals["reason"].count(".") >= 2
    # The eligibility verdict is carried alongside the LLM reason.
    assert top.signals["tier"] in ("qualified", "conditional")
    assert top.signals["gates_failed"] == []

    # Illinois-only (hard gate) is still excluded even with the model on.
    illinois_ids = {
        str(ci.id)
        for ci in ContentItem.objects.filter(
            external_id="9999", type=ContentItem.Type.FELLOWSHIP
        )
    }
    assert illinois_ids.isdisjoint({str(s.content_id) for s in scores})


# ============================================================================ #
# 4. Carry-forward floor + refit bypass (match_fellowships_for_user)            #
# ============================================================================ #


@pytest.mark.django_db
def test_match_fellowships_floor_hides_low_score_but_persists_verdict(settings):
    """A fellowship the model scores below OPPORTUNITY_MIN_MATCH_PERCENT is
    persisted (carry-forward remembers it) but hidden from the feed; a 60+
    fellowship stays suggested."""
    settings.OPPORTUNITY_MIN_MATCH_PERCENT = 60
    user = _profile_user_with_eligibility("floortest")
    _fellowship("f_strong", "Strong Match Fellowship")
    _fellowship("f_weak", "Weak Match Fellowship")

    def fake_complete(prompt: str) -> str:
        rows = []
        for line in prompt.splitlines():
            if not line.startswith("["):
                continue
            idx = int(line[1 : line.index("]")])
            if "Weak Match Fellowship" in line:
                rows.append(
                    {"item": idx, "match": 10, "headline": "Weak", "reason": "Barely."}
                )
            elif "Strong Match Fellowship" in line:
                rows.append(
                    {"item": idx, "match": 90, "headline": "Strong", "reason": "Great."}
                )
        return json.dumps({"suggestions": rows})

    result = match_fellowships_for_user(
        user, today="2026-07-06", persist=True, complete=fake_complete
    )
    assert result.status == "ok"
    assert result.suggestions == 1
    assert result.hidden == 1

    scores = {
        s.content.external_id: s
        for s in RelevanceScore.objects.filter(
            target_user=user, content__type=ContentItem.Type.FELLOWSHIP
        )
    }
    # Both persisted (carry-forward remembers both verdicts)...
    assert "f_strong" in scores and "f_weak" in scores
    # ...but only the strong one is flagged suggested.
    assert scores["f_strong"].signals["suggested"] is True
    assert scores["f_weak"].signals["suggested"] is False
    # Neither carries a percent any more; the strong one carries a slate verdict.
    assert scores["f_strong"].signals["match_percent"] is None
    assert scores["f_strong"].signals["verdict"] in {"read", "skim", "file"}
    assert scores["f_weak"].signals["match_percent"] is None


@pytest.mark.django_db
def test_refit_bypasses_carry_forward_for_fellowships():
    """``refit_user`` re-sends every eligible fellowship to the model, even ones a
    prior run already scored (``reuse_prior=False`` skips the carry-forward store)."""
    from tools.recommendation.refitting import refit_user

    user = _profile_user_with_eligibility("refitbypass")
    _fellowship("f1", "Dissertation Award")

    calls = {"n": 0}

    def fake_complete(_prompt: str) -> str:
        calls["n"] += 1
        return json.dumps(
            {"suggestions": [{"item": 1, "match": 80, "headline": "H", "reason": "R"}]}
        )

    match_fellowships_for_user(
        user, today="2026-07-06", persist=True, complete=fake_complete
    )
    assert calls["n"] == 1  # first run scores it

    refit_user(
        user, areas=("fellowships",), complete=fake_complete, persist=True, log=None
    )
    # The refit re-sent the already-scored fellowship to the model instead of
    # carrying its prior verdict forward.
    assert calls["n"] == 2


# ============================================================================ #
# 5. Embedding relevance gate end-to-end (pgvector, mirrors test_opportunities) #
# ============================================================================ #

_TOKENS = ["graph", "health", "biomedical", "other"]


def _fake_embed(texts):
    out = []
    for text in texts:
        low = text.casefold()
        vec = [1.0 if tok in low else 0.0 for tok in _TOKENS]
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        out.append([x / norm for x in vec])
    return out


@pytest.fixture
def pgvector(db: None):
    if connection.vendor != "postgresql":
        pytest.skip("the fellowship embedding-match path needs PostgreSQL + pgvector")


def _embedded_fellowship(eid, title, text, *, field=(SCI,), stage=(EARLY,)):
    """A fellowship ContentItem with a real embedding (pgvector retrieval)."""
    return ContentItem.objects.create(
        type=ContentItem.Type.FELLOWSHIP,
        source="illinois-fellowship-finder",
        external_id=eid,
        embedding=_fake_embed([text])[0],
        metadata={
            "title": title,
            "award_class": "fellowship",
            "description": text,
            "facets": {
                "citizenship": [US, INTL],
                "stage": list(stage),
                "field": list(field),
                "limits": [],
                "award_type": ["Fellowship/Grant"],
                "other": [],
            },
            "flags": {
                "requires_us_citizenship": False, "open_to_international": True
            },
            "deadline": {"type": "continuous", "date": "", "raw": "Continuous"},
            "first_seen": "2026-07-01T00:00:00+00:00",
            "search_text": text,
        },
    )


def _profile_user_with_sharp_interests(username):
    """Like ``_profile_user_with_eligibility``, but with ``areas``/``keywords``
    chosen to overlap ``_TOKENS`` deterministically for the fake embedder."""
    user = _profile_user_with_eligibility(username)
    user.profile.interests = {
        **user.profile.interests,
        "areas": ["Knowledge Graphs"],
        "keywords": ["biomedical"],
    }
    user.profile.save()
    return user


@pytest.mark.django_db
def test_fellowship_embed_threshold_drops_irrelevant_eligible(pgvector, settings):
    """A topically irrelevant-but-eligible fellowship (e.g. the cattlemen's-award
    scenario from the plan) is not surfaced; a relevant one is — and its persisted
    ``embedding_match`` is the topical (not eligibility) signal.
    """
    # 0.5, not 0.6: an interest's query is its declared area now, not the area
    # plus the whole profile's keyword list, so a multi-token document scores
    # lower against it. The separation under test — relevant clears, irrelevant
    # does not — is unchanged (0.577 vs 0.0).
    settings.FELLOWSHIP_MATCH_THRESHOLD = 0.5
    embeddings.set_embedder(_fake_embed)
    user = _profile_user_with_sharp_interests("fthresh")

    _embedded_fellowship(
        "f_relevant",
        "Knowledge Graphs Fellowship",
        "Knowledge Graphs for biomedical health",
    )
    _embedded_fellowship(
        "f_irrelevant", "Marine Biology Fellowship", "Marine biology other funding"
    )

    result = match_fellowships_for_user(
        user, today="2026-07-06", persist=True, complete=lambda _p: None
    )
    assert result.status == "ok"

    scores = {
        s.content.external_id: s
        for s in RelevanceScore.objects.filter(
            target_user=user, content__type=ContentItem.Type.FELLOWSHIP
        )
    }
    assert "f_relevant" in scores
    assert "f_irrelevant" not in scores  # below the embedding-match threshold

    relevant_signals = scores["f_relevant"].signals
    assert relevant_signals["embedding_match"] >= 0.5
    # The measured cosine survives as a diagnostic; it is no longer shown as a
    # percent, because a reader cannot be expected to track which of two numbers
    # on a card is the trustworthy one.
    assert relevant_signals["match_percent"] is None
    assert relevant_signals["source"] == "rules"
    assert "rule_fit" in relevant_signals


@pytest.mark.django_db
def test_fellowship_no_interest_signal_keeps_rule_only_ranking(pgvector, settings):
    """A user with no declared areas/watch topics gets the pre-Phase-B behaviour:
    every eligible fellowship surfaces, embedding_match stays unset."""
    settings.FELLOWSHIP_MATCH_THRESHOLD = 0.6
    embeddings.set_embedder(_fake_embed)
    user = User.objects.create_user("fnointerest", password="x")
    user.profile.interests = {
        "eligibility": {
            "citizenship": "us",
            "stage": "doctoral_early",
            "fields": ["Sciences/Engineering/Math"],
            "eligible_restrictions": [],
        }
    }
    user.profile.institution = "Florida State University"
    user.profile.save()

    _embedded_fellowship(
        "f_a", "Knowledge Graphs Fellowship", "Knowledge Graphs for biomedical health"
    )
    _embedded_fellowship(
        "f_b", "Marine Biology Fellowship", "Marine biology other funding"
    )

    result = match_fellowships_for_user(
        user, today="2026-07-06", persist=True, complete=lambda _p: None
    )
    assert result.status == "ok"

    scores = {
        s.content.external_id: s
        for s in RelevanceScore.objects.filter(
            target_user=user, content__type=ContentItem.Type.FELLOWSHIP
        )
    }
    # Both eligible fellowships surface — no relevance gate without interests.
    assert "f_a" in scores and "f_b" in scores
    assert scores["f_a"].signals.get("embedding_match") is None
    assert scores["f_b"].signals.get("embedding_match") is None


# ============================================================================ #
# 4. The feed reports whether it could filter on career stage at all
# ============================================================================ #


@pytest.mark.django_db
def test_feed_reports_an_unknown_career_stage(client: APIClient):
    """The stage gate is silent for anyone it cannot place on the ladder, so a
    feed built without a stage is genuinely less filtered — the page says so
    rather than promising eligibility filtering that did not happen."""
    user = User.objects.create_user("u_stage_unset", password="x")
    user.profile.interests = {}
    user.profile.academic_title = ""
    user.profile.save()
    client.force_authenticate(user)
    assert client.get("/api/opportunities/fellowships/").data["stage_set"] is False


@pytest.mark.django_db
def test_feed_reports_a_stage_derived_from_the_academic_title(client: APIClient):
    """Nothing was ever written to eligibility.stage — the title carries it."""
    user = User.objects.create_user("u_stage_derived", password="x")
    user.profile.interests = {}
    user.profile.academic_title = "postdoc"
    user.profile.save()
    client.force_authenticate(user)
    assert client.get("/api/opportunities/fellowships/").data["stage_set"] is True
