"""Backfilling fuller text — and not making things worse while doing it."""

from __future__ import annotations

from apps.scraper.collect.grants.enrich import (
    THIN_DESCRIPTION,
    apply_enrichment,
    nih_announcement_text,
    nih_guide_url,
    nsf_programme_text,
    plan_enrichment,
)
from apps.scraper.tests.collect.grants.conftest import opportunity

# Both agencies wrap their content in the same federal site furniture, byte for
# byte, on every page. These fixtures keep the shape that matters: chrome first,
# content in the middle, footer last.

NIH_PAGE = """
<html><body>
<nav>Skip to main content. An official website of the United States government.
A lock (LockLocked padlock) or https:// means you've safely connected.</nav>
<h1>PAR-25-378</h1>
<p>Purpose</p>
<p>The purpose of this notice of funding opportunity is to support research
into GPS-denied undersea navigation for Native populations health services.</p>
<p>Section VIII. Other Information</p>
<p>Weekly TOC for this Announcement</p>
<footer>NIH Funding Opportunities and Notices</footer>
</body></html>
"""

NSF_PAGE = """
<html><body>
<nav>Skip to main content. An official website of the United States government.
A lock (LockLocked padlock). Search. Menu. Find Funding. Award Search.</nav>
<p>Print this Page</p>
<p>Important information for proposers and award recipients</p>
<p>All proposals must be submitted in accordance with the requirements specified
in the funding opportunity and in the Proposal &amp; Award Policies Guide.</p>
<p>Supports research on ocean chemistry and the role of oceans in global
geochemical cycles.</p>
<p>Synopsis</p>
<p>The Chemical Oceanography Program supports research into the chemistry of
the oceans.</p>
<p>Footer</p>
<p>About Us. About NSF. Careers. Privacy. FOIA. No FEAR Act. Accessibility.</p>
</body></html>
"""


# --- URL derivation -------------------------------------------------------


def test_guide_url_follows_the_document_prefix():
    assert nih_guide_url("PAR-25-274").endswith("/pa-files/PAR-25-274.html")
    assert nih_guide_url("RFA-CA-27-021").endswith("/rfa-files/RFA-CA-27-021.html")
    assert nih_guide_url("NOT-CA-26-011").endswith("/notice-files/NOT-CA-26-011.html")


def test_an_unknown_prefix_yields_no_url_rather_than_a_guess():
    assert nih_guide_url("HT9425-23-S-SOC1") == ""


# --- chrome stripping -----------------------------------------------------
#
# The single most damaging thing this step could do is prepend a few kilobytes
# of identical boilerplate to every record in a source. The encoder truncates,
# so the chrome would be all it ever read, and every record in that source would
# embed to nearly the same vector.


def test_nih_chrome_is_stripped_from_both_ends():
    text = nih_announcement_text(NIH_PAGE)
    assert "Skip to main content" not in text
    assert "LockLocked" not in text
    assert "Weekly TOC" not in text
    assert "GPS-denied undersea navigation" in text


def test_nsf_chrome_and_standing_policy_block_are_stripped():
    text = nsf_programme_text(NSF_PAGE)
    assert "Skip to main content" not in text
    assert "All proposals must be submitted" not in text
    assert "No FEAR Act" not in text
    assert text.startswith("Supports research on ocean chemistry")


def test_stripped_text_opens_on_subject_matter():
    """What the encoder reads first has to be about this record, not the agency."""
    for text in (nih_announcement_text(NIH_PAGE), nsf_programme_text(NSF_PAGE)):
        assert "official website" not in text[:400].lower()


# --- planning -------------------------------------------------------------


def test_plan_targets_nih_records_with_no_native_data():
    orphan = opportunity(opportunity_number="PAR-27-098", contributing_sources=["grants_gov"])
    native = opportunity(
        opportunity_number="PAR-25-274", contributing_sources=["grants_gov", "nih_guide"]
    )
    plan = plan_enrichment([orphan, native])
    assert [number for number, _ in plan.nih_pages] == ["PAR-27-098"]


def test_plan_targets_only_thin_nsf_records():
    thin = opportunity(source="nsf", source_record_id="a", source_url="https://nsf.gov/a",
                       description="Short.")
    full = opportunity(source="nsf", source_record_id="b", source_url="https://nsf.gov/b",
                       description="x" * (THIN_DESCRIPTION + 1))
    plan = plan_enrichment([thin, full])
    assert len(plan.nsf_pages) == 1


def test_plan_is_capped_by_limit():
    records = [
        opportunity(opportunity_number=f"PAR-27-{n:03}", source_record_id=str(n),
                    contributing_sources=["grants_gov"])
        for n in range(10)
    ]
    assert len(plan_enrichment(records, limit=3).nih_pages) == 3


# --- applying -------------------------------------------------------------


def test_applying_replaces_thin_text_and_credits_the_funder():
    record = opportunity(
        opportunity_number="PAR-25-378",
        description="Short abstract.",
        contributing_sources=["grants_gov"],
    )
    improved, _ = apply_enrichment([record], {"nih_guide": {"PAR-25-378": NIH_PAGE}, "nsf": {}})

    assert improved == 1
    assert "GPS-denied undersea navigation" in record.description
    # The text is NIH's now, and merge precedence downstream has to know.
    assert "nih_guide" in record.contributing_sources


def test_a_page_that_yields_less_than_we_had_is_not_applied():
    """A short result is a parse miss, not an improvement.

    Overwriting would degrade the record while reporting a success — which is
    worse than doing nothing, because the number says it worked.
    """
    record = opportunity(opportunity_number="PAR-25-378", description="x" * 20_000)
    improved, untouched = apply_enrichment(
        [record], {"nih_guide": {"PAR-25-378": NIH_PAGE}, "nsf": {}}
    )
    assert (improved, untouched) == (0, 1)
    assert record.description == "x" * 20_000


def test_a_record_with_no_fetched_page_is_left_alone():
    record = opportunity(opportunity_number="PAR-99-999", description="Short.")
    improved, untouched = apply_enrichment([record], {"nih_guide": {}, "nsf": {}})
    assert (improved, untouched) == (0, 1)


def test_applying_touches_no_network():
    """The whole point of storing pages: the apply half re-runs offline."""
    import apps.scraper.collect.grants.enrich as module

    assert not hasattr(module.apply_enrichment, "__wrapped__")
    record = opportunity(opportunity_number="PAR-25-378", description="Short.")
    # No client is passed, so there is nothing it could call.
    apply_enrichment([record], {"nih_guide": {"PAR-25-378": NIH_PAGE}, "nsf": {}})
    assert "GPS-denied" in record.description
