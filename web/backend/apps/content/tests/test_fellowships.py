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
    derive_stage,
    eligibility_from_profile,
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


def test_award_above_the_applicants_stage_is_gated():
    """The reported defect: a postdoctoral award reaching an early-doctoral user."""
    ev = evaluate_eligibility(_meta(stage=("Postdoctoral/Post-graduate",)), ELIG)
    assert ev["tier"] == "not_eligible"
    assert any("postdoctoral" in g.lower() for g in ev["gates_failed"])


def test_award_below_the_applicants_stage_stays_soft():
    """The other direction is odd, not disqualifying — a postdoc may still hold a
    doctoral award, so it downgrades rather than disappears."""
    postdoc = Elig(
        citizenship="us",
        stage_tokens={"Postdoctoral/Post-graduate"},
        fields=["Sciences/Engineering/Math"],
    )
    ev = evaluate_eligibility(_meta(stage=(EARLY,)), postdoc)
    assert ev["tier"] == "conditional"
    assert ev["stage_match"] is False


def test_stage_gate_silent_when_the_applicant_stage_is_unknown():
    """Gating on an absence would empty the feed for every account that never
    answered the question."""
    unknown = Elig(citizenship="us", fields=["Sciences/Engineering/Math"])
    ev = evaluate_eligibility(_meta(stage=("Postdoctoral/Post-graduate",)), unknown)
    assert ev["tier"] == "conditional"


def test_dissertation_applicant_reaches_dissertation_awards():
    diss = Elig(
        citizenship="us",
        stage_tokens={"Dissertation Research", "Dissertation Write-Up"},
        fields=["Sciences/Engineering/Math"],
    )
    ev = evaluate_eligibility(_meta(stage=("Dissertation Write-Up",)), diss)
    assert ev["tier"] == "qualified"


def test_multi_stage_award_gates_on_its_earliest_rung():
    """An award open to doctoral *and* postdoc applicants is reachable by both."""
    ev = evaluate_eligibility(
        _meta(stage=(EARLY, "Postdoctoral/Post-graduate")), ELIG
    )
    assert ev["tier"] == "qualified"


def test_empty_facets_qualify():
    ev = evaluate_eligibility(_meta(citizenship=(), stage=(), field=()), ELIG)
    assert ev["tier"] == "qualified"


def test_scrape_miss_is_unverified_not_qualified():
    """A record whose facets are all empty passes every facet test trivially; it
    must read as unchecked rather than as a clean match for everybody."""
    meta = _meta(citizenship=(), stage=(), field=())
    meta["flags"] = {"facets_incomplete": True}
    ev = evaluate_eligibility(meta, ELIG)
    assert ev["tier"] == "unverified"
    assert any("unavailable" in r.lower() for r in ev["reasons"])


@pytest.mark.django_db
def test_withhold_unverified_drops_the_record():
    from apps.content.models import ContentItem

    meta = _meta(citizenship=(), stage=(), field=())
    meta["flags"] = {"facets_incomplete": True}
    ContentItem.objects.create(
        type=ContentItem.Type.FELLOWSHIP,
        source="illinois-fellowship-finder",
        external_id="incomplete",
        metadata=meta,
    )
    items = ContentItem.objects.filter(type=ContentItem.Type.FELLOWSHIP)
    assert len(match_fellowships(items, ELIG, TODAY)) == 1
    assert match_fellowships(items, ELIG, TODAY, withhold_unverified=True) == []


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
        # Eligible (passes hard gates) but the field does not match -> conditional
        # with a low fit. The stage is left unstated so the asymmetric stage gate
        # has nothing to fire on; this case is about the *fit* threshold.
        metadata=_meta(
            field=("Humanities/Arts/Social Sciences",),
            stage=(),
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


# ---- carry-forward: prior verdicts skip the model, new items get freed slots --


def test_fellowship_carry_forward_skips_already_scored_item():
    """A fellowship ``prior`` already scored is never re-sent to the model; its
    verdict survives, and the freed ``llm_limit`` slot goes to the unscored one."""
    from apps.content.opportunity_llm import generate_fellowship_suggestions

    ranked = [_ranked_stub("scored"), _ranked_stub("unscored", fit=0.6)]
    items = {
        "scored": _FakeItem("scored", {"title": "Scored Fellowship"}),
        "unscored": _FakeItem("unscored", {"title": "Unscored Fellowship"}),
    }
    prior = {
        "scored": {
            "match_percent": 77,
            "headline": "Carried Headline",
            "reason": "Carried reason.",
            "llm_scored_at": "2026-07-01T00:00:00+00:00",
        }
    }
    seen_prompts: list[str] = []

    def fake_complete(prompt: str) -> str:
        seen_prompts.append(prompt)
        return (
            '{"suggestions": [{"item": 1, "match": 91, '
            '"headline": "Fresh", "reason": "New report."}]}'
        )

    out = generate_fellowship_suggestions(
        {}, {}, ranked, items, llm_limit=1, prior=prior, complete=fake_complete
    )

    assert seen_prompts
    assert "Unscored Fellowship" in seen_prompts[0]
    assert "Scored Fellowship" not in seen_prompts[0]

    carried = next(s for s in out if s["content_id"] == "scored")
    assert carried["source"] == "llm"
    assert carried["match_percent"] == 77
    assert carried["headline"] == "Carried Headline"
    assert carried["llm_scored_at"] == "2026-07-01T00:00:00+00:00"
    # Eligibility fields still come from the rule engine, not the model.
    assert carried["tier"] == "qualified"

    fresh = next(s for s in out if s["content_id"] == "unscored")
    assert fresh["source"] == "llm"
    assert fresh["match_percent"] == 91


def test_fellowship_slate_entrant_gets_llm_slot_priority():
    """A fellowship that just entered the Top-25 wins the one free LLM slot over a
    higher-ranked one that has been sitting in the slate unwritten."""
    from apps.content.opportunity_llm import generate_fellowship_suggestions

    ranked = [_ranked_stub("old_high_rank"), _ranked_stub("new_low_rank", fit=0.4)]
    items = {
        "old_high_rank": _FakeItem("old_high_rank", {"title": "Old High Rank"}),
        "new_low_rank": _FakeItem("new_low_rank", {"title": "Newly Promoted"}),
    }
    seen_prompts: list[str] = []

    def fake_complete(prompt: str) -> str:
        seen_prompts.append(prompt)
        return '{"suggestions": []}'

    generate_fellowship_suggestions(
        {},
        {},
        ranked,
        items,
        llm_limit=1,
        priority_ids={"new_low_rank"},
        complete=fake_complete,
    )

    assert seen_prompts
    assert "Newly Promoted" in seen_prompts[0]
    assert "Old High Rank" not in seen_prompts[0]


# ---- match_fellowships: embedding relevance gate + blended rank (Phase B) ----


@pytest.mark.django_db
def test_match_fellowships_embed_by_id_none_matches_legacy_behavior():
    """``embed_by_id=None`` (no interest signal) surfaces/ranks exactly as the
    pure rule engine always has — a regression guard for existing callers."""
    from apps.content.models import ContentItem

    qualified = ContentItem.objects.create(
        type=ContentItem.Type.FELLOWSHIP,
        source="illinois-fellowship-finder",
        external_id="legacy_q",
        metadata=_meta(),
    )
    conditional = ContentItem.objects.create(
        type=ContentItem.Type.FELLOWSHIP,
        source="illinois-fellowship-finder",
        external_id="legacy_c",
        metadata=_meta(field=("Humanities",)),
    )
    items = ContentItem.objects.filter(type=ContentItem.Type.FELLOWSHIP)

    out = match_fellowships(items, ELIG, TODAY)  # embed_by_id defaults to None
    assert len(out) == 2
    assert all("embedding_match" not in s for s in out)
    assert all(s["fit"] == s["rule_fit"] for s in out)
    assert all(s["match_percent"] == round(s["fit"] * 100) for s in out)

    q_rank = next(s["rank"] for s in out if s["content_id"] == str(qualified.id))
    c_rank = next(s["rank"] for s in out if s["content_id"] == str(conditional.id))
    assert q_rank < c_rank


@pytest.mark.django_db
def test_match_fellowships_embed_gate_drops_irrelevant_eligible():
    """An eligible fellowship below ``embed_threshold`` is dropped entirely; one
    at/above it survives — the "eligible but irrelevant" case from the plan."""
    from apps.content.models import ContentItem

    irrelevant = ContentItem.objects.create(
        type=ContentItem.Type.FELLOWSHIP,
        source="illinois-fellowship-finder",
        external_id="irrelevant",
        metadata=_meta(),  # otherwise qualified
    )
    relevant = ContentItem.objects.create(
        type=ContentItem.Type.FELLOWSHIP,
        source="illinois-fellowship-finder",
        external_id="relevant",
        metadata=_meta(),
    )
    unretrieved = ContentItem.objects.create(
        type=ContentItem.Type.FELLOWSHIP,
        source="illinois-fellowship-finder",
        external_id="unretrieved",
        metadata=_meta(),  # never appears in embed_by_id -> counts as 0.0
    )
    items = ContentItem.objects.filter(type=ContentItem.Type.FELLOWSHIP)
    embed_by_id = {str(irrelevant.id): 0.1, str(relevant.id): 0.8}

    out = match_fellowships(
        items, ELIG, TODAY, embed_by_id=embed_by_id, embed_threshold=0.4
    )
    ids = {s["content_id"] for s in out}
    assert ids == {str(relevant.id)}
    assert str(irrelevant.id) not in ids
    assert str(unretrieved.id) not in ids


@pytest.mark.django_db
def test_match_fellowships_embed_blend_orders_relevance_over_tier():
    """A high-cosine eligible fellowship outranks a low-cosine one even when the
    low-cosine item has a better rule tier/recency."""
    from apps.content.models import ContentItem

    # Qualified + an imminent deadline -> strong rule_fit, but a weak topical match.
    high_tier_low_cosine = ContentItem.objects.create(
        type=ContentItem.Type.FELLOWSHIP,
        source="illinois-fellowship-finder",
        external_id="high_tier_low_cosine",
        metadata=_meta(deadline={"type": "true", "date": "2026-07-20", "raw": ""}),
    )
    # Conditional (field mismatch) -> weaker rule_fit, but a strong topical match.
    low_tier_high_cosine = ContentItem.objects.create(
        type=ContentItem.Type.FELLOWSHIP,
        source="illinois-fellowship-finder",
        external_id="low_tier_high_cosine",
        metadata=_meta(field=("Humanities",)),
    )
    items = ContentItem.objects.filter(type=ContentItem.Type.FELLOWSHIP)
    embed_by_id = {
        str(high_tier_low_cosine.id): 0.1,
        str(low_tier_high_cosine.id): 0.95,
    }

    out = match_fellowships(
        items, ELIG, TODAY, embed_by_id=embed_by_id, embed_threshold=0.0
    )
    ranks = {s["content_id"]: s["rank"] for s in out}
    assert ranks[str(low_tier_high_cosine.id)] < ranks[str(high_tier_low_cosine.id)]


@pytest.mark.django_db
def test_match_fellowships_match_percent_is_embedding_percent():
    """A rules-sourced row's ``match_percent`` is the topical (embedding) percent,
    not the rule-fit percent — the old value masqueraded eligibility as relevance."""
    from apps.content.models import ContentItem

    item = ContentItem.objects.create(
        type=ContentItem.Type.FELLOWSHIP,
        source="illinois-fellowship-finder",
        external_id="pct",
        metadata=_meta(),
    )
    items = ContentItem.objects.filter(type=ContentItem.Type.FELLOWSHIP)

    out = match_fellowships(
        items, ELIG, TODAY, embed_by_id={str(item.id): 0.73}, embed_threshold=0.0
    )
    assert len(out) == 1
    s = out[0]
    assert s["source"] == "rules"
    assert s["embedding_match"] == 0.73
    assert s["match_percent"] == 73
    # fit is the blend, not the raw rule score, once an embedding signal exists.
    assert s["fit"] == round(0.65 * 0.73 + 0.35 * s["rule_fit"], 4)


@pytest.mark.django_db
def test_match_fellowships_headline_reflects_strong_research_fit():
    from apps.content.models import ContentItem

    item = ContentItem.objects.create(
        type=ContentItem.Type.FELLOWSHIP,
        source="illinois-fellowship-finder",
        external_id="strongfit",
        metadata=_meta(),
    )
    out = match_fellowships(
        ContentItem.objects.filter(type=ContentItem.Type.FELLOWSHIP),
        ELIG,
        TODAY,
        embed_by_id={str(item.id): 0.9},
        embed_threshold=0.0,
    )
    assert out[0]["headline"] == "Strong research-fit match"


# ---- Interest-only mode (project targets, no eligibility gate) ----------------


def test_skip_eligibility_ranks_purely_on_embedding():
    """A project has no eligibility; fellowships rank by the embedding cosine, and
    an item an eligibility gate would drop (INTL-only) still surfaces on fit."""
    intl_only = _FakeItem(
        "intl",
        _meta(
            citizenship=(INTL,),  # a US-only user's eligibility gate would drop this
            flags={"requires_us_citizenship": False, "open_to_international": True},
        ),
    )
    on_topic = _FakeItem("ontopic", _meta())
    items = [intl_only, on_topic]
    embed_by_id = {"intl": 0.9, "ontopic": 0.5}

    out = match_fellowships(
        items,
        None,  # no Elig — skip_eligibility mode ignores it
        TODAY,
        embed_by_id=embed_by_id,
        embed_threshold=0.4,
        skip_eligibility=True,
    )
    ids = [s["content_id"] for s in out]
    # Both surface (no eligibility filter); the higher-cosine one ranks first.
    assert ids == ["intl", "ontopic"]
    top = out[0]
    assert top["tier"] == ""  # no eligibility verdict at project scope
    assert top["fit"] == 0.9  # pure embedding, not a blend
    assert top["match_percent"] == 90
    assert top["gates_failed"] == []


def test_skip_eligibility_applies_embed_threshold():
    below = _FakeItem("below", _meta())
    above = _FakeItem("above", _meta())
    out = match_fellowships(
        [below, above],
        None,
        TODAY,
        embed_by_id={"below": 0.2, "above": 0.7},
        embed_threshold=0.4,
        skip_eligibility=True,
    )
    assert [s["content_id"] for s in out] == ["above"]


def test_skip_eligibility_without_embedding_surfaces_nothing():
    """With no embedding signal a project can't rank fellowships — surface none."""
    out = match_fellowships(
        [_FakeItem("x", _meta())],
        None,
        TODAY,
        embed_by_id=None,
        skip_eligibility=True,
    )
    assert out == []


@pytest.mark.django_db
def test_persist_fellowships_writes_under_target_project():
    """The generalized persist path writes a project's fellowship scores under
    target_project (not target_user)."""
    from apps.accounts.models import Lab
    from apps.content.models import ContentItem, RelevanceScore
    from apps.content.opportunities import _persist_fellowships
    from apps.research.models import Project

    lab = Lab.objects.create(name="L", slug="l-fp")
    project = Project.objects.create(scope_lab=lab, name="P")
    item = ContentItem.objects.create(
        type=ContentItem.Type.FELLOWSHIP,
        source="illinois-fellowship-finder",
        external_id="fp1",
        metadata=_meta(),
    )
    cid = str(item.id)
    suggestion = {
        "content_id": cid,
        "tier": "",
        "fit": 0.8,
        "rule_fit": 0.0,
        "match_percent": 80,
        "gates_failed": [],
        "reasons": [],
        "headline": "Research-fit match",
        "reason": "Strong topical alignment",
        "source": "llm",
        "status": "open",
        "status_summary": "",
        "rank": 1,
        "embedding_match": 0.8,
    }
    _persist_fellowships(
        {"target_project": project},
        [suggestion],
        {cid},
        {cid: item},
        {cid: {"is_new": True, "pinned_until": None, "first_seen": ""}},
        today=TODAY,
    )
    row = RelevanceScore.objects.get(content=item, target_project=project)
    assert row.target_user_id is None
    # No percent survives persistence — the reader gets a slate verdict.
    assert row.signals["match_percent"] is None
    assert row.signals["suggested"] is True


# ---- Stage derivation --------------------------------------------------------


class _StubProfile:
    """The two attributes eligibility_from_profile reads, and nothing else."""

    def __init__(self, interests=None, academic_title="", institution=""):
        self.interests = interests or {}
        self.academic_title = academic_title
        self.institution = institution


def test_derive_stage_prefers_the_explicit_answer():
    profile = _StubProfile(
        interests={"eligibility": {"stage": "masters", "career_stage": "postdoc"}},
        academic_title="pi",
    )
    assert derive_stage(profile) == "masters"


def test_derive_stage_falls_back_to_intake_career_stage():
    """The intake agent writes career_stage in its own vocabulary; nothing used to
    bridge the two, so an answer of "postdoc" was invisible to matching."""
    profile = _StubProfile(interests={"eligibility": {"career_stage": "postdoc"}})
    assert derive_stage(profile) == "postdoc"


def test_derive_stage_falls_back_to_academic_title():
    """What makes the gate work for accounts that predate the eligibility step."""
    assert derive_stage(_StubProfile(academic_title="student")) == "doctoral_early"
    assert derive_stage(_StubProfile(academic_title="pi")) == "postdoc"


def test_derive_stage_refuses_to_guess_ambiguous_titles():
    """A staff scientist and a senior graduate student both pick these."""
    assert derive_stage(_StubProfile(academic_title="researcher")) == ""
    assert derive_stage(_StubProfile(academic_title="staff")) == ""


def test_eligibility_from_profile_uses_the_derived_stage():
    elig = eligibility_from_profile(_StubProfile(academic_title="student"))
    assert elig.stage == "doctoral_early"
    assert elig.stage_rank == 1
    ev = evaluate_eligibility(_meta(stage=("Postdoctoral/Post-graduate",)), elig)
    assert ev["tier"] == "not_eligible"


# ---- Prose constraints -------------------------------------------------------


def _constrained(**block):
    meta = _meta(stage=(), field=())
    meta["constraints"] = {
        "min_stage": "",
        "max_years_post_phd": None,
        "degree_required": "",
        "source": "patterns",
        "evidence": "",
        **block,
    }
    return meta


def test_prose_min_stage_gates_where_no_facet_exists():
    """The NSF class: the award lists no stage facet, the binding rule is prose."""
    ev = evaluate_eligibility(_constrained(min_stage="postdoc"), ELIG, TODAY)
    assert ev["tier"] == "not_eligible"


def test_prose_degree_requirement_gates_a_pre_phd_applicant():
    ev = evaluate_eligibility(_constrained(degree_required="phd"), ELIG, TODAY)
    assert ev["tier"] == "not_eligible"


def test_prose_constraints_are_silent_for_an_eligible_applicant():
    postdoc = Elig(citizenship="us", stage_tokens={"Postdoctoral/Post-graduate"})
    ev = evaluate_eligibility(_constrained(degree_required="phd"), postdoc, TODAY)
    assert ev["tier"] != "not_eligible"


def test_post_phd_window_gates_only_when_the_phd_year_is_known():
    stale = Elig(
        citizenship="us",
        stage_tokens={"Postdoctoral/Post-graduate"},
        phd_completed_year=2018,
    )
    meta = _constrained(max_years_post_phd=3, degree_required="phd")
    assert evaluate_eligibility(meta, stale, TODAY)["tier"] == "not_eligible"

    unknown_year = Elig(citizenship="us", stage_tokens={"Postdoctoral/Post-graduate"})
    assert evaluate_eligibility(meta, unknown_year, TODAY)["tier"] != "not_eligible"

    recent = Elig(
        citizenship="us",
        stage_tokens={"Postdoctoral/Post-graduate"},
        phd_completed_year=2025,
    )
    assert evaluate_eligibility(meta, recent, TODAY)["tier"] != "not_eligible"


def test_model_percent_is_clamped_on_a_hedged_row():
    """The model is told eligibility is settled and never re-litigates it, so its
    percent is pure research fit — it must not put a confident 95 on an item the
    rule engine could only call a possible fit."""
    from apps.content.opportunity_llm import generate_fellowship_suggestions

    ranked = [_ranked_stub("ccc", tier="conditional", fit=0.45)]
    items = {"ccc": _FakeItem("ccc", {"title": "X", "award_class": "fellowship"})}

    out = generate_fellowship_suggestions(
        {},
        {},
        ranked,
        items,
        complete=lambda _p: (
            '{"suggestions": [{"item": 1, "match": 95, "headline": "H", '
            '"reason": "R."}]}'
        ),
    )
    assert out[0]["source"] == "llm"
    assert out[0]["reason"] == "R."
    assert out[0]["match_percent"] == ranked[0]["match_percent"] == 45


def test_model_percent_stands_on_a_qualified_row():
    """The clamp is about hedged verdicts, not about distrusting the model."""
    from apps.content.opportunity_llm import generate_fellowship_suggestions

    ranked = [_ranked_stub("ddd", tier="qualified", fit=0.45)]
    items = {"ddd": _FakeItem("ddd", {"title": "X", "award_class": "fellowship"})}

    out = generate_fellowship_suggestions(
        {},
        {},
        ranked,
        items,
        complete=lambda _p: (
            '{"suggestions": [{"item": 1, "match": 95, "headline": "H", '
            '"reason": "R."}]}'
        ),
    )
    assert out[0]["match_percent"] == 95


def test_lab_rows_keep_the_model_percent():
    """A lab fellowship has no tier at all — there is no eligibility verdict to
    hedge against, so nothing is clamped."""
    from apps.content.opportunity_llm import generate_fellowship_suggestions

    ranked = [_ranked_stub("eee", tier="", fit=0.45)]
    items = {"eee": _FakeItem("eee", {"title": "X", "award_class": "fellowship"})}

    out = generate_fellowship_suggestions(
        {},
        {},
        ranked,
        items,
        complete=lambda _p: (
            '{"suggestions": [{"item": 1, "match": 95, "headline": "H", '
            '"reason": "R."}]}'
        ),
    )
    assert out[0]["match_percent"] == 95
