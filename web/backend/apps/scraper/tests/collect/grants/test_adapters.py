"""Each adapter's parse stage, driven entirely from stored raw payloads."""

from __future__ import annotations

from apps.scraper.collect.grants.adapters.eu_portal import EUPortalAdapter
from apps.scraper.collect.grants.adapters.grants_gov import GrantsGovAdapter
from apps.scraper.collect.grants.adapters.nih_guide import NIHGuideAdapter
from apps.scraper.collect.grants.adapters.nsf import NSFAdapter
from apps.scraper.collect.grants.adapters.sam_gov import SAMGovAdapter
from apps.scraper.collect.grants.adapters.sbir import SBIRAdapter
from apps.scraper.tests.collect.grants.conftest import (
    EU_TOPIC,
    GRANTS_GOV_DETAIL,
    GRANTS_GOV_FORECAST_DETAIL,
    GRANTS_GOV_FORECAST_SUMMARY,
    GRANTS_GOV_SUMMARY,
    NIH_ANNOUNCEMENT,
    NIH_ORPHAN_NOTICE,
    NIH_OVERLAY_NOTICE,
    NSF_ROLLING_ITEM,
    NSF_UPCOMING_ITEM,
    SBIR_CLOSED,
    SBIR_SOLICITATION,
    bundle,
    opportunity,
)

# --- Grants.gov (P0) -----------------------------------------------------


def test_grants_gov_merges_summary_and_detail():
    raw = bundle(
        "grants_gov", [GRANTS_GOV_SUMMARY], details={"357305": GRANTS_GOV_DETAIL}
    )
    (record,) = GrantsGovAdapter().parse(raw)

    assert record.opportunity_number == "PAR-25-274"
    assert record.status == "open"
    assert record.close_date == "2026-11-17"
    # The verbatim string is kept because "12:00:00 AM EST" is not the instant
    # applicants actually face.
    assert record.close_date_text == "Nov 17, 2026 12:00:00 AM EST"
    assert "feasibility trials" in record.description
    assert "- One" in record.description  # list structure survived
    assert record.eligibility.startswith("Other Eligible Applicants")
    # CFDA numbers moved to their own column; categories holds subjects only.
    assert record.assistance_listings == ["93.213"]
    assert record.categories == ["Health"]


def test_grants_gov_literal_none_award_is_not_a_number():
    raw = bundle("grants_gov", [GRANTS_GOV_SUMMARY], details={"357305": GRANTS_GOV_DETAIL})
    (record,) = GrantsGovAdapter().parse(raw)
    assert record.award_floor is None
    assert record.award_ceiling is None


def test_grants_gov_reads_forecast_payloads_not_just_synopsis():
    # Forecast records put everything under "forecast". Reading only "synopsis"
    # would silently blank every forecasted record's description and money.
    raw = bundle(
        "grants_gov",
        [GRANTS_GOV_FORECAST_SUMMARY],
        details={"355824": GRANTS_GOV_FORECAST_DETAIL},
    )
    (record,) = GrantsGovAdapter().parse(raw)

    assert record.status == "forecasted"
    assert record.description == "Forecast text."
    assert record.award_floor == 50_000.0
    assert record.award_ceiling == 250_000.0
    assert record.expected_awards == 3
    assert record.close_date == "2027-06-23"


# --- SBIR (P1) -----------------------------------------------------------


def test_sbir_flattens_topics_and_subtopics_into_first_class_records():
    records = SBIRAdapter().parse(bundle("sbir", [SBIR_SOLICITATION]))

    kinds = [r.record_kind for r in records]
    assert kinds.count("standalone") == 1
    # Two topics plus one subtopic; a solicitation that yields one record has
    # thrown away nearly all its content.
    assert kinds.count("topic") == 3
    assert len(records) > 1


def test_sbir_topics_point_at_their_parent_and_inherit_its_dates():
    records = SBIRAdapter().parse(bundle("sbir", [SBIR_SOLICITATION]))
    parent = next(r for r in records if r.record_kind == "standalone")
    topics = [r for r in records if r.record_kind == "topic"]

    for topic in topics:
        assert topic.parent_opportunity_number == parent.opportunity_number
        assert topic.close_date == parent.close_date
        assert topic.open_date == parent.open_date
        assert topic.status == parent.status


def test_sbir_topic_carries_the_technical_description():
    records = SBIRAdapter().parse(bundle("sbir", [SBIR_SOLICITATION]))
    navigation = next(r for r in records if r.opportunity_number == "N261-001")
    assert "GPS-denied undersea navigation" in navigation.description
    assert navigation.funder_subunit == "Navy"


def test_sbir_filters_closed_solicitations_locally():
    # Probed: the endpoint offers no reliable server-side status filter, so the
    # whole set is pulled and filtered here.
    records = SBIRAdapter().parse(bundle("sbir", [SBIR_SOLICITATION, SBIR_CLOSED]))
    assert all("Old Solicitation" not in r.title for r in records)


# --- structured facets ---------------------------------------------------
#
# Every field below was already in the payload and reachable only by parsing JSON
# at query time, which is why no filter could use it.


def test_grants_gov_promotes_applicant_types_and_instruments():
    (record,) = GrantsGovAdapter().parse(
        bundle("grants_gov", [GRANTS_GOV_SUMMARY], details={"357305": GRANTS_GOV_DETAIL})
    )
    assert record.funding_instruments == ["Grant"]
    assert record.applicant_types == ["State governments", "Small businesses"]


def test_grants_gov_promotes_assistance_listings():
    (record,) = GrantsGovAdapter().parse(
        bundle("grants_gov", [GRANTS_GOV_SUMMARY], details={"357305": GRANTS_GOV_DETAIL})
    )
    assert record.assistance_listings == ["93.213"]


def test_cost_sharing_keeps_unknown_distinct_from_not_required():
    """An omitted cost-share read as 'not required' is a late, disqualifying surprise."""
    detail = {**GRANTS_GOV_DETAIL, "synopsis": {**GRANTS_GOV_DETAIL["synopsis"], "costSharing": False}}
    (no,) = GrantsGovAdapter().parse(
        bundle("grants_gov", [GRANTS_GOV_SUMMARY], details={"357305": detail})
    )
    assert no.cost_sharing is False

    (unknown,) = GrantsGovAdapter().parse(
        bundle("grants_gov", [GRANTS_GOV_SUMMARY], details={"357305": GRANTS_GOV_DETAIL})
    )
    assert unknown.cost_sharing is None


def test_grants_gov_takes_the_canonical_top_agency_code():
    (record,) = GrantsGovAdapter().parse(
        bundle("grants_gov", [GRANTS_GOV_SUMMARY], details={"357305": GRANTS_GOV_DETAIL})
    )
    assert record.agency_code == "HHS"


def test_nih_promotes_activity_codes_and_participating_institutes():
    (record,) = NIHGuideAdapter().parse(bundle("nih_guide", [NIH_ANNOUNCEMENT]))
    assert record.activity_codes == ["R01"]
    assert record.participating_units == ["NCI", "NIA"]
    assert record.opportunity_category == "PA"


def test_eu_promotes_action_type_and_deadline_model():
    (record,) = EUPortalAdapter().parse(bundle("eu_portal", [EU_TOPIC]))
    assert record.action_types == ["HORIZON TMA MSCA Cofund Doctoral programme"]
    assert record.deadline_model == "single-stage"
    assert "HORIZON-MSCA-2027-COFUND-01-01" in record.topic_keywords


def test_eu_topic_conditions_become_eligibility_not_description():
    """Admissibility boilerplate is near-identical across a programme.

    Concatenated into the description it dilutes the subject matter retrieval is
    supposed to match on; as eligibility it answers a question a reader has.
    """
    (record,) = EUPortalAdapter().parse(bundle("eu_portal", [EU_TOPIC]))
    assert "Legal entities established in" in record.eligibility
    assert "Legal entities established in" not in record.description
    assert "Deeper skills" in record.description


def test_merged_facets_are_unioned_not_overwritten():
    """A record can be both a grant and a cooperative agreement.

    Unlike prose, where one source must win because two paragraphs cannot both be
    the description, narrowing a facet list on merge loses real filter values.
    """
    from apps.scraper.collect.grants.dedupe import merge_pair

    native = opportunity(
        source="nih_guide", activity_codes=["R01"], applicant_types=[], cost_sharing=None
    )
    aggregator = opportunity(
        source="grants_gov",
        activity_codes=[],
        applicant_types=["State governments"],
        funding_instruments=["Grant", "Cooperative Agreement"],
        cost_sharing=True,
    )
    merged = merge_pair(native, aggregator)
    assert merged.activity_codes == ["R01"]
    assert merged.applicant_types == ["State governments"]
    assert merged.funding_instruments == ["Grant", "Cooperative Agreement"]
    assert merged.cost_sharing is True


# --- NIH (P3) ------------------------------------------------------------


def test_nih_announcement_from_structured_xml():
    records = NIHGuideAdapter().parse(bundle("nih_guide", [NIH_ANNOUNCEMENT]))
    (record,) = records

    assert record.opportunity_number == "PA-25-172"
    assert record.record_kind == "standalone"
    assert record.funder_subunit == "NCI"
    assert record.close_date == "2028-01-07"  # LARD
    # "Multiple dates, see announcement." is prose, not a date: it belongs in the
    # verbatim field and nowhere near close_date.
    assert record.close_date_text == "Multiple dates, see announcement."
    assert record.expiration_date == "2028-01-08"
    assert record.open_date == "2025-01-05"


# --- NIH recurring cycles and letters of intent ---------------------------


def test_nih_multiple_dates_becomes_the_actual_standard_cycle():
    """LARD is the end of a cycle, not the next round.

    The fixture is a real R01 running to 2028-01-07 and saying only "Multiple
    dates, see announcement." Stored as one date it advertises a deadline
    seventeen months out while a round is due in weeks.
    """
    (record,) = NIHGuideAdapter().parse(bundle("nih_guide", [NIH_ANNOUNCEMENT]))

    assert record.close_date == "2028-01-07"  # LARD is still the final round
    assert record.dates_inferred is True
    # R01 standard dates: 5 February, 5 June, 5 October.
    assert "2026-10-05" in record.additional_due_dates
    assert "2027-02-05" in record.additional_due_dates
    assert all(day.endswith("-05") for day in record.additional_due_dates)


def test_nih_derived_rounds_stay_inside_the_announcement_window():
    (record,) = NIHGuideAdapter().parse(bundle("nih_guide", [NIH_ANNOUNCEMENT]))
    assert all("2025-01-05" <= day < "2028-01-07" for day in record.additional_due_dates)


def test_nih_cycle_derivation_is_deterministic_not_clock_dependent():
    """Parsing must reproduce from a stored payload months later."""
    first = NIHGuideAdapter().parse(bundle("nih_guide", [NIH_ANNOUNCEMENT]))[0]
    second = NIHGuideAdapter().parse(bundle("nih_guide", [NIH_ANNOUNCEMENT]))[0]
    assert first.additional_due_dates == second.additional_due_dates


def test_nih_activity_code_selects_its_own_cycle_not_a_family_default():
    """R21 is the 16th, R01 the 5th. A generic 'R' rule would get one of them wrong."""
    r21 = {**NIH_ANNOUNCEMENT, "ActivityCodes": "R21", "DocNum": "PA-25-999"}
    (record,) = NIHGuideAdapter().parse(bundle("nih_guide", [r21]))
    assert all(day.endswith("-16") for day in record.additional_due_dates)


def test_nih_unknown_activity_code_derives_nothing_rather_than_guessing():
    weird = {**NIH_ANNOUNCEMENT, "ActivityCodes": "ZZ99", "DocNum": "PA-25-998"}
    (record,) = NIHGuideAdapter().parse(bundle("nih_guide", [weird]))
    assert record.additional_due_dates == []
    assert record.dates_inferred is False


def test_nih_derives_nothing_when_the_announcement_sets_its_own_schedule():
    """A LARD off every published family means custom dates, not standard ones.

    An invented deadline is worse than a terse one because it looks specific, so
    the inference has to agree with a signal already in the record before it is
    allowed to run.
    """
    custom = {**NIH_ANNOUNCEMENT, "LARD": "2027-11-12", "DocNum": "PAR-25-204"}
    (record,) = NIHGuideAdapter().parse(bundle("nih_guide", [custom]))
    assert record.additional_due_dates == []
    assert record.dates_inferred is False


def test_nih_derives_when_the_last_date_falls_on_the_aids_cycle():
    """January 7 is an AIDS standard date: this announcement does run to a cycle."""
    aids = {**NIH_ANNOUNCEMENT, "LARD": "2028-01-07", "DocNum": "PA-25-172"}
    (record,) = NIHGuideAdapter().parse(bundle("nih_guide", [aids]))
    assert record.dates_inferred is True


def test_nih_derives_when_the_last_date_falls_on_the_renewal_cycle():
    """R01 renewals are due 5 March / 5 July / 5 November."""
    renewal = {**NIH_ANNOUNCEMENT, "LARD": "2027-11-05", "DocNum": "PA-25-995"}
    (record,) = NIHGuideAdapter().parse(bundle("nih_guide", [renewal]))
    assert record.dates_inferred is True


def test_nih_single_deadline_announcement_gets_no_derived_rounds():
    """Only 'multiple dates' prose means a standard cycle; a real date is a real date."""
    single = {
        **NIH_ANNOUNCEMENT,
        "AppReceiptDate": "November 17, 2026",
        "DocNum": "RFA-CA-25-001",
    }
    (record,) = NIHGuideAdapter().parse(bundle("nih_guide", [single]))
    assert record.additional_due_dates == []
    assert record.dates_inferred is False


def test_nih_letter_of_intent_is_captured_even_when_it_is_not_a_date():
    """"30 days prior" is not parseable but is exactly what the applicant must act on."""
    (record,) = NIHGuideAdapter().parse(bundle("nih_guide", [NIH_ANNOUNCEMENT]))
    assert record.intent_date is None
    assert record.intent_date_text == "30 days prior to application due date."


def test_nih_absolute_letter_of_intent_date_is_parsed():
    dated = {**NIH_ANNOUNCEMENT, "IntentDate": "January 17, 2027", "DocNum": "PA-25-997"}
    (record,) = NIHGuideAdapter().parse(bundle("nih_guide", [dated]))
    assert record.intent_date == "2027-01-17"


def test_nih_not_applicable_letter_of_intent_is_dropped_not_displayed():
    none = {**NIH_ANNOUNCEMENT, "IntentDate": "Not applicable.", "DocNum": "PA-25-996"}
    (record,) = NIHGuideAdapter().parse(bundle("nih_guide", [none]))
    assert record.intent_date is None
    assert record.intent_date_text == ""


def test_nih_overlay_is_a_record_of_its_own_with_a_parent_pointer():
    records = NIHGuideAdapter().parse(
        bundle("nih_guide", [], notices=[NIH_OVERLAY_NOTICE])
    )
    (overlay,) = records

    assert overlay.record_kind == "overlay"
    assert overlay.opportunity_number == "NOT-CA-26-011"
    assert overlay.parent_opportunity_number == "PA-25-172"
    # The second parent is real data and must not be dropped — but it is an
    # identifier, so it lives with the other identifiers, not among subjects.
    assert overlay.related_numbers == ["PAR-24-122"]
    assert overlay.categories == []
    assert "sleep disruption and cancer" in overlay.description
    # Overlays carry no deadline of their own; inventing one would make prune lie.
    assert overlay.close_date is None
    assert overlay.expiration_date == "2029-01-08"


def test_nih_overlay_with_no_parent_is_flagged_not_silently_accepted():
    (record,) = NIHGuideAdapter().parse(
        bundle("nih_guide", [], notices=[NIH_ORPHAN_NOTICE])
    )
    assert record.record_kind == "overlay"
    assert record.parent_opportunity_number is None
    assert record.unresolved_parent is True


def test_nih_mixed_feed_produces_both_kinds():
    records = NIHGuideAdapter().parse(
        bundle("nih_guide", [NIH_ANNOUNCEMENT], notices=[NIH_OVERLAY_NOTICE])
    )
    assert {r.record_kind for r in records} == {"standalone", "overlay"}


# --- NSF (P4) ------------------------------------------------------------


def test_nsf_extracts_publication_number_and_labelled_due_date():
    (record,) = NSFAdapter().parse(bundle("nsf", [NSF_UPCOMING_ITEM]))
    assert record.opportunity_number == "PD 23-1650"
    assert record.close_date == "2027-08-17"
    assert "Full Proposal Target Date" in record.close_date_text


def test_nsf_accepted_anytime_is_rolling_not_a_missing_date():
    (record,) = NSFAdapter().parse(bundle("nsf", [NSF_ROLLING_ITEM]))
    assert record.close_date is None
    # The phrase is the only record of *why* there is no date — a deliberate
    # NSF mechanism rather than a date we failed to parse.
    assert record.close_date_text == "Full Proposal Accepted Anytime"
    # The four-category distinction is why this adapter exists at all. It is a
    # document kind, not a subject, so it lives in opportunity_category now.
    assert record.opportunity_category == "Program Description"


def test_nsf_merges_the_same_opportunity_seen_in_both_feeds():
    duplicate = {**NSF_UPCOMING_ITEM, "feed": "announcements", "description": "<p>Short.</p>"}
    records = NSFAdapter().parse(bundle("nsf", [NSF_UPCOMING_ITEM, duplicate]))
    assert len(records) == 1
    assert records[0].close_date == "2027-08-17"


# --- EU portal (P5) ------------------------------------------------------


def test_eu_topic_parses_inline_description_without_a_second_fetch():
    (record,) = EUPortalAdapter().parse(bundle("eu_portal", [EU_TOPIC]))
    # descriptionByte carries the full text, contrary to the briefing's note.
    assert "Expected Outcome" in record.description
    assert "- Deeper skills." in record.description


def test_eu_topic_is_a_topic_under_its_call():
    (record,) = EUPortalAdapter().parse(bundle("eu_portal", [EU_TOPIC]))
    assert record.record_kind == "topic"
    assert record.parent_opportunity_number == "HORIZON-MSCA-2027-COFUND-01"
    assert record.currency == "EUR"
    assert record.status == "forecasted"
    assert record.close_date == "2027-04-06"


def test_eu_budget_blob_becomes_numbers():
    (record,) = EUPortalAdapter().parse(bundle("eu_portal", [EU_TOPIC]))
    assert record.award_floor == 1_000_000.0
    assert record.award_ceiling == 5_000_000.0
    assert record.total_program_funding == 51_251_165.0
    assert record.expected_awards == 4


def test_eu_unparseable_budget_yields_no_invented_numbers():
    broken = {**EU_TOPIC, "metadata": {**EU_TOPIC["metadata"], "budgetOverview": ["{not json"]}}
    (record,) = EUPortalAdapter().parse(bundle("eu_portal", [broken]))
    assert record.award_floor is None
    assert record.total_program_funding is None


# --- SAM.gov (P6) --------------------------------------------------------


def test_sam_gov_is_disabled_without_a_key_and_says_why():
    enabled, reason = SAMGovAdapter(api_key="").available()
    assert enabled is False
    assert "SAM_API_KEY" in reason


def test_sam_gov_enables_with_a_key():
    enabled, _ = SAMGovAdapter(api_key="abc123").available()
    assert enabled is True


def test_sam_gov_parses_a_notice():
    row = {
        "noticeId": "abc",
        "solicitationNumber": "HR001126S0001",
        "title": "Broad Agency Announcement: Resilient Systems",
        "fullParentPathName": "DEPT OF DEFENSE.DARPA",
        "subTier": "DARPA",
        "type": "Solicitation",
        "baseType": "Solicitation",
        "postedDate": "2026-05-01",
        "responseDeadLine": "2027-04-30T17:00:00-04:00",
        "description": "<p>DARPA seeks proposals.</p>",
        "uiLink": "https://sam.gov/opp/abc/view",
        "active": "Yes",
    }
    (record,) = SAMGovAdapter(api_key="k").parse(bundle("sam_gov", [row]))
    assert record.opportunity_number == "HR001126S0001"
    assert record.close_date == "2027-04-30"
    assert record.funder_subunit == "DARPA"


def test_nsf_survives_the_bare_ampersands_in_its_own_feed():
    """NSF publishes "CDS&E" unescaped, which is invalid XML.

    A strict parser rejects the entire document over one program title, so the
    source contributed nothing at all until the ampersand was repaired.
    """
    import xml.etree.ElementTree as ET

    import pytest

    from apps.scraper.collect.grants.adapters.nsf import _repair_xml

    broken = (
        b"<rss><channel><item>"
        b"<title>Computational and Data-Enabled Science and Engineering (CDS&E)</title>"
        b"<link>https://example.org/a&amp;b</link>"
        b"</item></channel></rss>"
    )
    with pytest.raises(ET.ParseError):
        ET.fromstring(broken)

    root = ET.fromstring(_repair_xml(broken))
    assert root.findtext(".//title").endswith("(CDS&E)")
    # An ampersand that was already an entity must survive untouched.
    assert root.findtext(".//link") == "https://example.org/a&b"
