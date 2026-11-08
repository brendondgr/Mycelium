"""The audit harness must be falsifiable before it is trusted.

Each check gets two assertions: it fires on a record that has the defect, and it
stays silent on one that does not. A check that only ever gets exercised against
clean fixtures proves nothing — it would report zero just as happily if it were
broken.
"""

from __future__ import annotations

from datetime import date

import pytest

from tools.retrieval.collect.grants import quality
from tools.retrieval.collect.grants.quality import (
    Finding,
    as_baseline,
    format_report,
    run_checks,
)
from tools.retrieval.tests.collect.grants.conftest import opportunity

TODAY = date(2026, 8, 16)


def find(records, key: str) -> Finding:
    findings = {f.key: f for f in run_checks(records, TODAY)}
    return findings[key]


def clean() -> list:
    """A record with none of the defects the harness looks for."""
    return [
        opportunity(
            opportunity_number="XYZ-99-001",
            title="A Perfectly Ordinary Opportunity",
            description="A sufficiently long description of the research programme. " * 8,
            categories=["Health", "Environment"],
            close_date="2027-03-01",
            posted_date="2026-01-01",
            open_date="2026-02-01",
            funding_instruments=["Grant"],
            applicant_types=["State governments"],
        )
    ]


def test_clean_corpus_reports_no_defects():
    for finding in run_checks(clean(), TODAY):
        assert finding.count == 0, f"{finding.key} fired on a clean record: {finding.examples}"


# --- date checks ----------------------------------------------------------


def test_past_deadline_fires_and_only_on_past():
    assert find([opportunity(close_date="2026-01-01")], "past_deadline").count == 1
    assert find([opportunity(close_date="2027-01-01")], "past_deadline").count == 0


def test_rolling_record_is_not_a_past_deadline():
    """A null close date is 'open indefinitely', never 'overdue'."""
    assert find([opportunity(close_date=None)], "past_deadline").count == 0


def test_wrong_round_fires_when_close_date_is_the_first_round():
    """The EU shape: close_date held deadlineDate[0] instead of the final round."""
    stale = opportunity(close_date="2021-09-21", additional_due_dates=["2026-09-21"])
    assert find([stale], "wrong_round_selected").count == 1


def test_wrong_round_silent_when_close_date_is_the_final_round():
    right = opportunity(close_date="2027-02-05", additional_due_dates=["2026-10-05"])
    assert find([right], "wrong_round_selected").count == 0


def test_single_round_records_are_not_in_the_population():
    """A one-deadline record cannot have picked the wrong round."""
    assert find([opportunity(close_date="2027-01-01")], "wrong_round_selected").total == 0


def test_future_posted_date():
    assert find([opportunity(posted_date="2027-01-01")], "future_posted_date").count == 1
    assert find([opportunity(posted_date="2025-01-01")], "future_posted_date").count == 0


def test_date_order_catches_close_before_open():
    bad = opportunity(open_date="2027-06-01", close_date="2027-01-01")
    assert find([bad], "date_order").count == 1


def test_date_order_catches_expiry_before_close():
    bad = opportunity(close_date="2027-04-09", expiration_date="2027-02-26")
    assert find([bad], "date_order").count == 1


def test_implausible_deadline():
    assert find([opportunity(close_date="2099-01-01")], "implausible_deadline").count == 1
    assert find([opportunity(close_date="2030-01-01")], "implausible_deadline").count == 0


def test_unparsed_multi_date():
    said = opportunity(close_date_text="Multiple dates, see announcement.")
    assert find([said], "unparsed_multi_date").count == 1
    parsed = opportunity(
        close_date_text="Multiple dates, see announcement.",
        close_date="2026-10-05",
        additional_due_dates=["2027-02-05"],
    )
    assert find([parsed], "unparsed_multi_date").count == 0


# --- money ----------------------------------------------------------------


def test_amount_order_catches_ceiling_above_programme_total():
    bad = opportunity(award_ceiling=50_000_000, total_program_funding=10_000_000)
    assert find([bad], "amount_order").count == 1


def test_amount_order_allows_ceiling_equal_to_total():
    """A single-award programme is legitimate and must not be flagged."""
    ok = opportunity(award_ceiling=10_000_000, total_program_funding=10_000_000)
    assert find([ok], "amount_order").count == 0


# --- identity and duplicates ----------------------------------------------


def test_unflagged_duplicates_fires_on_an_unflagged_pair():
    pair = [
        opportunity(source_record_id="a", opportunity_number="X-1", title="Rail Studies"),
        opportunity(source_record_id="b", opportunity_number="X-2", title="Rail Studies"),
    ]
    assert find(pair, "unflagged_duplicates").count == 2


def test_unflagged_duplicates_silent_once_the_pair_is_flagged():
    pair = [
        opportunity(
            source_record_id="a", opportunity_number="X-1", title="Rail Studies",
            review_candidates=["num:X2"],
        ),
        opportunity(source_record_id="b", opportunity_number="X-2", title="Rail Studies"),
    ]
    assert find(pair, "unflagged_duplicates").count == 0


def test_titles_that_only_share_a_prefix_are_not_duplicates():
    """NIH's K23 pair differs only in a trailing clause that decides eligibility.

    Calling those duplicates would push dedupe toward the exact merge it exists
    to avoid.
    """
    pair = [
        opportunity(
            source_record_id="a", opportunity_number="PA-24-185",
            title="Mentored Patient-Oriented Research Career Development Award "
                  "(Parent K23 Independent Clinical Trial Not Allowed)",
        ),
        opportunity(
            source_record_id="b", opportunity_number="PA-24-186",
            title="Mentored Patient-Oriented Research Career Development Award "
                  "(Parent K23 Independent Basic Experimental Studies with Humans Required)",
        ),
    ]
    assert find(pair, "unflagged_duplicates").count == 0


def test_different_deadlines_are_not_duplicates():
    pair = [
        opportunity(source_record_id="a", opportunity_number="X-1", close_date="2027-01-01"),
        opportunity(source_record_id="b", opportunity_number="X-2", close_date="2027-06-01"),
    ]
    assert find(pair, "unflagged_duplicates").count == 0


def test_missing_native_data_fires_on_an_nih_number_without_nih():
    orphan = opportunity(opportunity_number="PAR-27-098", contributing_sources=["grants_gov"])
    assert find([orphan], "missing_native_data").count == 1


def test_missing_native_data_silent_when_the_funder_contributed():
    native = opportunity(
        opportunity_number="PAR-27-098", contributing_sources=["grants_gov", "nih_guide"]
    )
    assert find([native], "missing_native_data").count == 0


def test_non_native_numbers_are_outside_the_population():
    """A DoD number says nothing about NIH or NSF coverage."""
    assert find([opportunity(opportunity_number="HT9425-23-S-SOC1")], "missing_native_data").total == 0


def test_missing_identifier():
    assert find([opportunity(opportunity_number="")], "missing_identifier").count == 1


# --- text -----------------------------------------------------------------


def test_empty_description():
    assert find([opportunity(description="")], "empty_description").count == 1


def test_pointer_description():
    pointer = opportunity(description="See the application guidelines at arts.gov.")
    assert find([pointer], "pointer_description").count == 1


def test_long_text_beginning_with_see_is_not_a_pointer():
    """'See also' inside a real description is not a stub."""
    real = opportunity(description="See the full programme rationale below. " + "Detail. " * 60)
    assert find([real], "pointer_description").count == 0


def test_html_residue():
    assert find([opportunity(description="<p>Still tagged.</p>")], "html_residue").count == 1
    assert find([opportunity(description="Clean &amp; tidy")], "html_residue").count == 1
    assert find([opportunity(description="Clean and tidy")], "html_residue").count == 0


def test_glued_words():
    glued = opportunity(description="TheChemical OceanographyProgram supports research.")
    assert find([glued], "glued_words").count == 1


def test_ordinary_camel_case_terms_are_not_glued_words():
    """Real words that happen to be capitalised mid-token must not trip this."""
    ok = opportunity(description="Research on JavaScript and DNA sequencing methods.")
    assert find([ok], "glued_words").count == 0


def test_mixed_categories_fires_on_eligibility_prose():
    mixed = opportunity(
        categories=["Health", "Nonprofits having a 501(c)(3) status with the IRS"]
    )
    assert find([mixed], "mixed_categories").count == 1


def test_mixed_categories_fires_on_document_kind_markers():
    assert find([opportunity(categories=["synopsis"])], "mixed_categories").count == 1


def test_unfilterable_fires_on_a_record_with_no_facets():
    bare = opportunity(applicant_types=[], funding_instruments=[], activity_codes=[])
    assert find([bare], "unfilterable").count == 1


def test_unfilterable_silent_once_any_facet_is_present():
    assert find([opportunity(activity_codes=["R01"])], "unfilterable").count == 0
    # An explicit "cost sharing not required" is itself a filterable fact.
    assert find([opportunity(cost_sharing=False)], "unfilterable").count == 0


def test_mixed_categories_silent_on_real_subjects():
    assert find([opportunity(categories=["Health", "AI", "Environment"])], "mixed_categories").count == 0


# --- reporting semantics --------------------------------------------------


def test_a_check_with_nothing_to_measure_reports_na_not_zero():
    """Reporting 0/0 as a pass would claim a verification that never happened."""
    finding = find([opportunity(opportunity_number="ZZ-1")], "wrong_round_selected")
    assert not finding.applicable
    assert "n/a" in finding.line()


def test_report_shows_delta_against_a_baseline():
    records = [opportunity(close_date="2026-01-01")]
    findings = run_checks(records, TODAY)
    text = format_report(findings, baseline={"past_deadline": 5})
    assert "-4" in text


def test_baseline_omits_inapplicable_checks():
    """An n/a check must not be recorded as a zero that a later run 'regresses' from."""
    baseline = as_baseline(run_checks([opportunity(opportunity_number="ZZ-1")], TODAY))
    assert "wrong_round_selected" not in baseline


def test_every_check_declares_a_known_severity():
    for finding in run_checks(clean(), TODAY):
        assert finding.severity in quality.SEVERITIES


def test_every_check_has_a_unique_key():
    keys = [f.key for f in run_checks(clean(), TODAY)]
    assert len(keys) == len(set(keys))


@pytest.mark.parametrize("finding", run_checks(clean(), TODAY), ids=lambda f: f.key)
def test_every_check_explains_why_it_matters(finding):
    """A count with no explanation is a number nobody can act on."""
    assert len(finding.detail) > 40
    assert finding.label
