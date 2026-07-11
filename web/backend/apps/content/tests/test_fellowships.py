"""Unit tests for the fellowship eligibility rule engine.

Adapted from /home/bdgr/Tools/ProQuest/tests/test_fellowships_recommend.py.
No ORM, no pgvector, no LLM — all tests are pure-Python except the E2E
match test which seeds ContentItem rows and needs django_db.
"""

from __future__ import annotations

import pytest

from apps.content.fellowships import (
    FELLOWSHIP_SURFACE_LIMIT,
    Elig,
    evaluate_eligibility,
    fellowship_status,
    fit,
    match_fellowships,
    recency,
)

# ---- Test constants ----------------------------------------------------------

TODAY = "2026-07-06"

US = "US Citizens, Nationals, or Permanent Residents"
INTL = "International Students"
SCI = "Sciences/Engineering/Math"
EARLY = "Early Years of Doctoral Program"
ILLINOIS = "University of Illinois Students"
WOMEN = "Women"
EQUITY = "Equity"
STIPEND = "Annual stipend of at least $10,000"

# A US-citizen, early-doctoral, Sci/Eng/Math profile (matches the fixture user).
ELIG = Elig(
    citizenship="us",
    stage_tokens={"Early Years of Doctoral Program"},
    fields=["Sciences/Engineering/Math"],
    university="Florida State University",
    is_illinois_student=False,
    eligible_restrictions=[],
)


# ---- Helpers -----------------------------------------------------------------


def _facets(citizenship=(US, INTL), stage=(EARLY,), field=(SCI,), limits=()):
    return {
        "citizenship": list(citizenship),
        "stage": list(stage),
        "field": list(field),
        "award_type": ["Fellowship/Grant"],
        "limits": list(limits),
        "other": [],
    }


def _meta(
    citizenship=(US, INTL),
    stage=(EARLY,),
    field=(SCI,),
    limits=(),
    deadline=None,
    award_class="fellowship",
    flags=None,
):
    return {
        "award_class": award_class,
        "facets": _facets(citizenship, stage, field, limits),
        "flags": flags or {
            "requires_us_citizenship": False, "open_to_international": True
        },
        "deadline": deadline or {
            "type": "continuous", "date": "", "raw": "Continuous"
        },
    }


# ---- evaluate_eligibility ---------------------------------------------------


def test_general_award_qualified():
    ev = evaluate_eligibility(_meta(), ELIG)
    assert ev["tier"] == "qualified"
    assert not ev["gates_failed"]


def test_international_only_not_eligible_for_us_user():
    ev = evaluate_eligibility(_meta(citizenship=(INTL,)), ELIG)
    assert ev["tier"] == "not_eligible"
    assert "International students only" in ev["gates_failed"]


def test_us_only_not_eligible_for_international_user():
    intl = Elig(citizenship="international", stage_tokens=set(), fields=[])
    ev = evaluate_eligibility(
        _meta(citizenship=(US,), flags={"requires_us_citizenship": True}),
        intl,
    )
    assert ev["tier"] == "not_eligible"
    assert any("Requires US" in g for g in ev["gates_failed"])


def test_illinois_restriction_gates_out_non_illinois_user():
    ev = evaluate_eligibility(_meta(limits=(ILLINOIS,)), ELIG)
    assert ev["tier"] == "not_eligible"
    assert any("Illinois" in g for g in ev["gates_failed"])


def test_illinois_restriction_passes_for_illinois_user():
    illinois_elig = Elig(
        citizenship="us",
        stage_tokens={"Early Years of Doctoral Program"},
        fields=["Sciences/Engineering/Math"],
        is_illinois_student=True,
    )
    ev = evaluate_eligibility(_meta(limits=(ILLINOIS,)), illinois_elig)
    assert ev["tier"] == "qualified"


def test_women_restriction_gates_out_user_without_claim():
    ev = evaluate_eligibility(_meta(limits=(WOMEN,)), ELIG)
    assert ev["tier"] == "not_eligible"
    assert any("women" in g for g in ev["gates_failed"])


def test_equity_restriction_gates_out_user_without_claim():
    ev = evaluate_eligibility(_meta(limits=(EQUITY,)), ELIG)
    assert ev["tier"] == "not_eligible"


def test_women_restriction_passes_when_user_claims_it():
    elig_w = Elig(
        citizenship="us",
        stage_tokens={"Early Years of Doctoral Program"},
        fields=["Sciences/Engineering/Math"],
        eligible_restrictions=["Women"],
    )
    ev = evaluate_eligibility(_meta(limits=(WOMEN,)), elig_w)
    assert ev["tier"] == "qualified"


def test_stipend_limit_is_attribute_not_gate():
    ev = evaluate_eligibility(_meta(limits=(STIPEND,)), ELIG)
    assert ev["tier"] == "qualified"
    assert ev["has_stipend"] is True


def test_field_mismatch_is_conditional_not_hidden():
    ev = evaluate_eligibility(_meta(field=("Humanities",)), ELIG)
    assert ev["tier"] == "conditional"
    assert ev["field_match"] is False


def test_stage_mismatch_is_conditional():
    ev = evaluate_eligibility(_meta(stage=("Postdoctoral/Post-graduate",)), ELIG)
    assert ev["tier"] == "conditional"
    assert ev["stage_match"] is False


def test_empty_facets_qualify():
    ev = evaluate_eligibility(_meta(citizenship=(), stage=(), field=()), ELIG)
    assert ev["tier"] == "qualified"


def test_reasons_include_citizenship_note():
    ev = evaluate_eligibility(_meta(), ELIG)
    assert any("US citizen" in r for r in ev["reasons"])


# ---- fellowship_status ------------------------------------------------------


def test_status_continuous_open():
    st = fellowship_status(_meta(), TODAY)
    assert st["status"] == "open"
    assert st["actionable_date"] == ""


def test_status_anticipated_open_with_actionable_date():
    m = _meta(deadline={"type": "anticipated", "date": "2027-04", "raw": ""})
    st = fellowship_status(m, TODAY)
    assert st["status"] == "open"
    assert st["actionable_date"] == "2027-04"


def test_status_true_future_open():
    m = _meta(deadline={"type": "true", "date": "2026-12-01", "raw": ""})
    assert fellowship_status(m, TODAY)["status"] == "open"


def test_status_true_past_closed():
    m = _meta(deadline={"type": "true", "date": "2025-01-01", "raw": ""})
    assert fellowship_status(m, TODAY)["status"] == "closed"


def test_status_suspended():
    m = _meta(deadline={"type": "suspended", "date": "", "raw": ""})
    assert fellowship_status(m, TODAY)["status"] == "suspended"


def test_status_rolling_open():
    m = _meta(deadline={"type": "rolling", "date": "", "raw": ""})
    assert fellowship_status(m, TODAY)["status"] == "open"


# ---- recency / fit ----------------------------------------------------------


def test_recency_imminent_is_near_one():
    r = recency("2026-07-10", TODAY)
    assert 0.99 <= r <= 1.0


def test_recency_far_future_decays():
    # 540 days into the future would hit exactly 0; 270 days should give ~0.5
    r = recency("2027-03-31", TODAY)
    assert 0 < r < 1.0


def test_recency_past_is_zero():
    assert recency("2026-01-01", TODAY) == 0.0


def test_recency_empty_is_zero():
    assert recency("", TODAY) == 0.0


def test_fit_qualified_beats_conditional():
    q_ev = evaluate_eligibility(_meta(), ELIG)
    c_ev = evaluate_eligibility(_meta(field=("Humanities",)), ELIG)
    st = fellowship_status(_meta(), TODAY)
    assert fit(q_ev, st, TODAY) > fit(c_ev, st, TODAY)


def test_fit_returns_float_between_zero_and_one():
    ev = evaluate_eligibility(_meta(), ELIG)
    st = fellowship_status(_meta(), TODAY)
    f = fit(ev, st, TODAY)
    assert 0.0 <= f <= 1.0


# ---- match_fellowships (E2E — needs django_db) ------------------------------


@pytest.mark.django_db
def test_match_fellowships_filters_and_orders():
    """Qualified items rank above conditional; closed and not_eligible are excluded."""
    from apps.content.models import ContentItem

    def _item(eid, citizenship, stage, field, deadline_type, award_class="fellowship"):
        return ContentItem.objects.create(
            type=ContentItem.Type.FELLOWSHIP,
            source="illinois-fellowship-finder",
            external_id=eid,
            metadata={
                "title": f"Fellowship {eid}",
                "award_class": award_class,
                "facets": {
                    "citizenship": list(citizenship),
                    "stage": list(stage),
                    "field": list(field),
                    "limits": [],
                    "award_type": ["Fellowship/Grant"],
                    "other": [],
                },
                "flags": {
                    "requires_us_citizenship": False, "open_to_international": True
                },
                "deadline": {
                    "type": deadline_type,
                    "date": "2026-12-01" if deadline_type == "true" else "",
                    "raw": "",
                },
                "deadline_date": "2026-12-01" if deadline_type == "true" else "",
                "first_seen": "2026-07-01T00:00:00+00:00",
            },
        )

    qualified = _item("q", (US, INTL), (EARLY,), (SCI,), "continuous")
    conditional = _item("c", (US, INTL), (EARLY,), ("Humanities",), "continuous")
    # US user cannot get INTL-only award → not_eligible
    _not_eligible = _item("x", (INTL,), (EARLY,), (SCI,), "continuous")
    # Past deadline → excluded by fellowship_status
    _closed = _item("p", (US, INTL), (EARLY,), (SCI,), "true")
    # Override closed item's deadline to be past
    closed = ContentItem.objects.get(external_id="p")
    closed.metadata["deadline"]["date"] = "2025-01-01"
    closed.metadata["deadline_date"] = "2025-01-01"
    closed.save()

    items = ContentItem.objects.filter(type=ContentItem.Type.FELLOWSHIP)
    suggestions = match_fellowships(items, ELIG, TODAY)
    ids = [s["content_id"] for s in suggestions]

    assert str(qualified.id) in ids
    assert str(conditional.id) in ids
    assert str(_not_eligible.id) not in ids
    assert str(closed.id) not in ids

    # Qualified must rank above conditional
    q_id, c_id = str(qualified.id), str(conditional.id)
    q_rank = next(s["rank"] for s in suggestions if s["content_id"] == q_id)
    c_rank = next(s["rank"] for s in suggestions if s["content_id"] == c_id)
    assert q_rank < c_rank


@pytest.mark.django_db
def test_match_fellowships_skips_grants():
    """Items with award_class=='grant' are skipped even if in the fellowship corpus."""
    from apps.content.models import ContentItem

    ContentItem.objects.create(
        type=ContentItem.Type.FELLOWSHIP,
        source="illinois-fellowship-finder",
        external_id="grant_in_fellowship_corpus",
        metadata={
            "title": "Sneaky Grant",
            "award_class": "grant",
            "facets": {
                "citizenship": [US], "stage": [], "field": [],
                "limits": [], "award_type": [], "other": [],
            },
            "flags": {},
            "deadline": {"type": "continuous", "date": "", "raw": ""},
        },
    )
    items = ContentItem.objects.filter(type=ContentItem.Type.FELLOWSHIP)
    suggestions = match_fellowships(items, ELIG, TODAY)
    assert all(s["content_id"] != "grant_in_fellowship_corpus" for s in suggestions)


@pytest.mark.django_db
def test_match_fellowships_surface_limit():
    """At most FELLOWSHIP_SURFACE_LIMIT suggestions are returned."""
    from apps.content.models import ContentItem

    for i in range(FELLOWSHIP_SURFACE_LIMIT + 5):
        ContentItem.objects.create(
            type=ContentItem.Type.FELLOWSHIP,
            source="illinois-fellowship-finder",
            external_id=f"bulk_{i}",
            metadata={
                "title": f"Fellowship {i}",
                "award_class": "fellowship",
                "facets": {
                    "citizenship": [US, INTL], "stage": [], "field": [],
                    "limits": [], "award_type": [], "other": [],
                },
                "flags": {},
                "deadline": {"type": "continuous", "date": "", "raw": ""},
                "first_seen": "2026-07-01T00:00:00+00:00",
            },
        )
    items = ContentItem.objects.filter(type=ContentItem.Type.FELLOWSHIP)
    suggestions = match_fellowships(items, ELIG, TODAY)
    assert len(suggestions) <= FELLOWSHIP_SURFACE_LIMIT


@pytest.mark.django_db
def test_match_fellowships_uncaps_beyond_default_limit():
    """A larger ``max_surface`` surfaces *every* eligible fellowship, not just 40."""
    from apps.content.models import ContentItem

    n = FELLOWSHIP_SURFACE_LIMIT + 12
    for i in range(n):
        ContentItem.objects.create(
            type=ContentItem.Type.FELLOWSHIP,
            source="illinois-fellowship-finder",
            external_id=f"more_{i}",
            metadata=_meta(),  # eligible (US+INTL, matching stage/field), continuous
        )
    items = ContentItem.objects.filter(type=ContentItem.Type.FELLOWSHIP)

    # Default keeps the old backstop; a higher cap shows them all.
    assert len(match_fellowships(items, ELIG, TODAY)) == FELLOWSHIP_SURFACE_LIMIT
    assert len(match_fellowships(items, ELIG, TODAY, max_surface=250)) == n


@pytest.mark.django_db
def test_match_fellowships_fit_threshold_trims_weak():
    """The fit threshold (after eligibility) drops weakly-related fellowships."""
    from apps.content.models import ContentItem

    ContentItem.objects.create(
        type=ContentItem.Type.FELLOWSHIP,
        source="illinois-fellowship-finder",
        external_id="strong",
        metadata=_meta(),  # qualified: field + stage match -> fit ~0.72
    )
    ContentItem.objects.create(
        type=ContentItem.Type.FELLOWSHIP,
        source="illinois-fellowship-finder",
        external_id="weak",
        # Eligible (passes hard gates) but neither field nor stage match -> conditional
        # with a low fit (~0.25).
        metadata=_meta(
            field=("Humanities/Arts/Social Sciences",),
            stage=("Postdoctoral/Post-graduate",),
        ),
    )
    items = ContentItem.objects.filter(type=ContentItem.Type.FELLOWSHIP)

    # No threshold: both eligible fellowships surface.
    ids = {s["content_id"] for s in match_fellowships(items, ELIG, TODAY)}
    assert len(ids) == 2

    # A 0.5 fit threshold keeps only the strongly-fitting one.
    kept = match_fellowships(items, ELIG, TODAY, match_threshold=0.5)
    assert [s["tier"] for s in kept] == ["qualified"]
    assert all(s["fit"] >= 0.5 for s in kept)


@pytest.mark.django_db
def test_match_fellowships_rank_is_1_based():
    from apps.content.models import ContentItem

    ContentItem.objects.create(
        type=ContentItem.Type.FELLOWSHIP,
        source="illinois-fellowship-finder",
        external_id="r1",
        metadata={
            "title": "Fellowship R1",
            "award_class": "fellowship",
            "facets": {
                "citizenship": [US, INTL], "stage": [], "field": [],
                "limits": [], "award_type": [], "other": [],
            },
            "flags": {},
            "deadline": {"type": "continuous", "date": "", "raw": ""},
            "first_seen": "2026-07-01T00:00:00+00:00",
        },
    )
    items = ContentItem.objects.filter(type=ContentItem.Type.FELLOWSHIP)
    suggestions = match_fellowships(items, ELIG, TODAY)
    assert suggestions[0]["rank"] == 1
    assert suggestions[0]["source"] == "rules"
    assert 0 <= suggestions[0]["match_percent"] <= 100


# ---- LLM report overlay (generate_fellowship_suggestions, pure) ---------------


class _FakeItem:
    """Minimal fellowship ContentItem stand-in (only ``.id`` + ``.metadata``)."""

    def __init__(self, cid: str, metadata: dict):
        self.id = cid
        self.metadata = metadata


def _ranked_stub(cid: str, *, tier: str = "qualified", fit: float = 0.8) -> dict:
    """A rule-engine suggestion dict as match_fellowships would emit it."""
    return {
        "content_id": cid,
        "tier": tier,
        "fit": fit,
        "similarity": fit,
        "match_percent": round(fit * 100),
        "gates_failed": [],
        "reasons": ["US citizen / permanent resident eligible", "Stage matches"],
        "headline": (
            "Strong eligibility match" if tier == "qualified" else "Possible fit"
        ),
        "reason": "US citizen / permanent resident eligible; Stage matches",
        "source": "rules",
        "status": "open",
        "actionable_date": "",
        "status_summary": "Continuous",
        "rank": 1,
    }


def test_generate_fellowship_suggestions_overlays_llm_report():
    """The model's tailored report replaces the reason; eligibility is preserved."""
    from apps.content.opportunity_llm import generate_fellowship_suggestions

    ranked = [_ranked_stub("aaa")]
    items = {
        "aaa": _FakeItem(
            "aaa",
            {
                "title": "Neuro Fellowship",
                "award_class": "fellowship",
                "description": "Supports doctoral neuroscience research.",
                "facets": {"field": [SCI], "stage": [EARLY]},
                "eligibility": ["US citizens"],
            },
        )
    }

    def fake_complete(prompt: str) -> str:
        assert "Neuro Fellowship" in prompt  # the candidate brief reached the model
        return (
            '{"suggestions": [{"item": 1, "match": 88, '
            '"headline": "A Natural Fit For Your Neuro Work", '
            '"reason": "One. Two. Three."}]}'
        )

    out = generate_fellowship_suggestions(
        {}, {}, ranked, items, complete=fake_complete
    )
    assert len(out) == 1
    s = out[0]
    assert s["source"] == "llm"
    assert s["match_percent"] == 88
    assert s["reason"] == "One. Two. Three."
    # eligibility verdict + facts survive the overlay
    assert s["tier"] == "qualified"
    assert s["gates_failed"] == []
    assert s["reasons"]


def test_generate_fellowship_suggestions_falls_back_to_rules():
    """A missing/empty model keeps the rule-engine reason (no regression)."""
    from apps.content.opportunity_llm import generate_fellowship_suggestions

    ranked = [_ranked_stub("bbb")]
    items = {"bbb": _FakeItem("bbb", {"title": "X", "award_class": "fellowship"})}

    out = generate_fellowship_suggestions(
        {}, {}, ranked, items, complete=lambda _p: None
    )
    assert out[0]["source"] == "rules"
    assert out[0]["reason"] == ranked[0]["reason"]
    assert out[0]["match_percent"] == ranked[0]["match_percent"]
