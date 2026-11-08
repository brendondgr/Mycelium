"""The three dedupe layers and the merge policy.

The most important assertion in this file is the negative one: layer 3 must not
merge. A false merge silently deletes an opportunity a user should have seen and
leaves no trace, which is strictly worse than a visible duplicate.
"""

from __future__ import annotations

from tools.retrieval.collect.grants.dedupe import (
    deduplicate,
    merge_pair,
    resolve_overlay_parents,
)
from tools.retrieval.tests.collect.grants.conftest import opportunity

# --- layer 1 -------------------------------------------------------------


def test_layer1_collapses_the_same_record_from_one_source():
    first = opportunity(source_record_id="1", categories=["cancer"])
    second = opportunity(source_record_id="1", categories=["sleep"])

    records, report = deduplicate([first, second])

    assert len(records) == 1
    assert report.layer1_collapsed == 1
    # Query tags are merged, not overwritten: each query's contribution survives.
    assert set(records[0].categories) == {"cancer", "sleep"}


def test_layer1_keeps_the_longer_description():
    short = opportunity(source_record_id="1", description="Short.")
    long = opportunity(source_record_id="1", description="A considerably longer description.")

    records, _ = deduplicate([short, long])
    assert records[0].description == "A considerably longer description."


def test_layer1_leaves_genuinely_different_records_alone():
    records, report = deduplicate(
        [opportunity(source_record_id="1"), opportunity(source_record_id="2", opportunity_number="PA-25-002")]
    )
    assert len(records) == 2
    assert report.layer1_collapsed == 0


# --- layer 2 -------------------------------------------------------------


def test_layer2_merges_across_sources_on_the_normalized_number():
    aggregator = opportunity(source="grants_gov", source_record_id="1", opportunity_number="PAR-25-274")
    native = opportunity(source="nih_guide", source_record_id="9", opportunity_number="par 25 274")

    records, report = deduplicate([aggregator, native])

    assert len(records) == 1
    assert report.layer2_merged == 1
    assert set(records[0].contributing_sources) == {"grants_gov", "nih_guide"}


def test_layer2_does_not_merge_an_overlay_into_its_parent():
    # An overlay that quotes its parent's number is not the same record as the
    # parent — merging them would destroy the distinction section 1 insists on.
    parent = opportunity(source="grants_gov", source_record_id="1", opportunity_number="PA-25-172")
    overlay = opportunity(
        source="nih_guide",
        source_record_id="2",
        opportunity_number="PA-25-172",
        record_kind="overlay",
        close_date=None,
    )
    records, _ = deduplicate([parent, overlay])
    assert len(records) == 2


def test_layer2_leaves_numberless_records_untouched():
    records, report = deduplicate(
        [
            opportunity(source="nsf", source_record_id="a", opportunity_number="", title="Alpha"),
            opportunity(source="nsf", source_record_id="b", opportunity_number="", title="Beta"),
        ]
    )
    assert len(records) == 2
    assert report.layer2_merged == 0


# --- merge policy --------------------------------------------------------


def test_funder_native_wins_descriptive_text():
    aggregator = opportunity(
        source="grants_gov", source_record_id="1", description="Short agency blurb."
    )
    native = opportunity(
        source="nih_guide",
        source_record_id="2",
        description="A much longer funder-written purpose statement with real detail.",
    )
    merged = merge_pair(aggregator, native)
    assert merged.description == native.description


def test_funder_native_wins_descriptive_text_even_when_shorter():
    # The rule is "the funder's source wins", not "the longer string wins". Real
    # case: Grants.gov's copy of an NSF program description has lost its
    # non-breaking spaces, which makes it *longer* and worse.
    aggregator = opportunity(
        source="grants_gov",
        source_record_id="1",
        description="TheChemical OceanographyProgram supports research into chemistry.",
    )
    native = opportunity(
        source="nsf",
        source_record_id="2",
        description="The Chemical Oceanography Program supports research.",
    )
    merged = merge_pair(aggregator, native)
    assert merged.description == native.description


def test_an_empty_funder_description_falls_back_to_the_aggregator():
    aggregator = opportunity(source="grants_gov", source_record_id="1", description="Real text.")
    native = opportunity(source="nsf", source_record_id="2", description="")
    assert merge_pair(aggregator, native).description == "Real text."


def test_two_funder_native_sources_fall_back_to_the_longer_text():
    left = opportunity(source="nsf", source_record_id="1", description="Short.")
    right = opportunity(source="nih_guide", source_record_id="2", description="Much longer text.")
    assert merge_pair(left, right).description == "Much longer text."


def test_aggregator_wins_structured_dates_and_money():
    aggregator = opportunity(
        source="grants_gov",
        source_record_id="1",
        close_date="2027-03-01",
        award_ceiling=500_000.0,
    )
    native = opportunity(
        source="nih_guide", source_record_id="2", close_date="2027-03-02", award_ceiling=None
    )
    merged = merge_pair(aggregator, native)
    assert merged.close_date == "2027-03-01"
    assert merged.award_ceiling == 500_000.0


def test_aggregator_gaps_fall_back_to_the_funder():
    aggregator = opportunity(source="grants_gov", source_record_id="1", award_floor=None)
    native = opportunity(source="nih_guide", source_record_id="2", award_floor=25_000.0)
    assert merge_pair(aggregator, native).award_floor == 25_000.0


def test_contributing_sources_are_always_unioned():
    merged = merge_pair(
        opportunity(source="grants_gov", source_record_id="1"),
        opportunity(source="nih_guide", source_record_id="2"),
    )
    assert set(merged.contributing_sources) == {"grants_gov", "nih_guide"}


def test_merge_keeps_both_raw_payloads():
    merged = merge_pair(
        opportunity(source="grants_gov", source_record_id="1", raw={"a": 1}),
        opportunity(source="nih_guide", source_record_id="2", raw={"b": 2}),
    )
    assert merged.raw["grants_gov"] == {"a": 1}
    assert merged.raw["nih_guide"] == {"b": 2}


# --- layer 3 -------------------------------------------------------------


def test_layer3_flags_a_likely_duplicate_without_merging_it():
    left = opportunity(
        source="grants_gov",
        source_record_id="1",
        opportunity_number="",
        title="Advanced Robotics for Undersea Exploration",
        close_date="2027-05-01",
    )
    right = opportunity(
        source="nsf",
        source_record_id="2",
        opportunity_number="",
        title="Advanced Robotics for Undersea Exploration",
        close_date="2027-05-01",
    )

    records, report = deduplicate([left, right])

    # Both records survive. This is the whole point.
    assert len(records) == 2
    assert report.layer3_flagged == 1
    assert report.review_pairs
    assert records[0].review_candidates and records[1].review_candidates


def test_layer3_does_not_flag_records_with_different_close_dates():
    left = opportunity(source="grants_gov", source_record_id="1", opportunity_number="", close_date="2027-05-01")
    right = opportunity(source="nsf", source_record_id="2", opportunity_number="", close_date="2028-05-01")
    _, report = deduplicate([left, right])
    assert report.layer3_flagged == 0


def test_layer3_ignores_pairs_layer2_already_settled():
    left = opportunity(source="grants_gov", source_record_id="1", opportunity_number="PA-25-001")
    right = opportunity(source="nih_guide", source_record_id="2", opportunity_number="PA-25-001")
    _, report = deduplicate([left, right])
    assert report.layer2_merged == 1
    assert report.layer3_flagged == 0


def test_layer3_compares_within_a_source_too():
    """Layer 3 used to skip same-source pairs, which was where most of them were.

    Of 49 same-title same-deadline groups in the live corpus, 47 were within one
    source and so were never looked at. Layer 1 cannot cover this: it keys on the
    source's own record id, which differs by definition for two separately
    published records.
    """
    left = opportunity(source="nsf", source_record_id="1", opportunity_number="", title="Same Title")
    right = opportunity(source="nsf", source_record_id="2", opportunity_number="", title="Same Title")
    _, report = deduplicate([left, right])
    assert report.layer3_flagged == 1


def test_the_eu_lump_sum_twin_is_flagged_not_merged():
    """The real shape: one topic published under a standard and a lump-sum call.

    Related but not interchangeable — the funding rules differ — so the outcome
    must be a visible link, never a silent deletion of one of them.
    """
    standard = opportunity(
        source="eu_portal",
        source_record_id="a",
        opportunity_number="HORIZON-EURATOM-2026-01-06",
        title="Support for the Sustainable Nuclear Energy Technology Platform",
        close_date="2026-09-15",
    )
    lump_sum = opportunity(
        source="eu_portal",
        source_record_id="b",
        opportunity_number="HORIZON-EURATOM-LS-2026-01-06",
        title="Support for the Sustainable Nuclear Energy Technology Platform",
        close_date="2026-09-15",
    )
    merged, report = deduplicate([standard, lump_sum])

    assert len(merged) == 2, "a fuzzy match must never delete an opportunity"
    assert report.layer3_flagged == 1
    assert merged[0].review_candidates and merged[1].review_candidates


def test_a_topic_is_not_flagged_as_a_duplicate_of_its_own_parent():
    """A topic inherits its parent's title and dates; that is a recorded
    relationship, not a suspected duplicate, and flagging it buries the real ones."""
    parent = opportunity(
        source="sbir", source_record_id="p", opportunity_number="DoD SBIR 26.1",
        title="DoD SBIR 26.1 Annual", close_date="2026-12-18",
    )
    topic = opportunity(
        source="sbir", source_record_id="t", opportunity_number="N261-001",
        parent_opportunity_number="DoD SBIR 26.1", record_kind="topic",
        title="DoD SBIR 26.1 Annual", close_date="2026-12-18",
    )
    _, report = deduplicate([parent, topic])
    assert report.layer3_flagged == 0


# --- overlay resolution --------------------------------------------------


def test_overlay_with_a_present_parent_is_marked_resolved():
    parent = opportunity(source="nih_guide", source_record_id="1", opportunity_number="PA-25-172")
    overlay = opportunity(
        source="nih_guide",
        source_record_id="2",
        opportunity_number="NOT-CA-26-011",
        parent_opportunity_number="PA-25-172",
        record_kind="overlay",
        close_date=None,
    )
    unresolved = resolve_overlay_parents([parent, overlay])
    assert unresolved == 0
    assert overlay.unresolved_parent is False


def test_overlay_pointing_at_an_absent_parent_is_flagged():
    overlay = opportunity(
        source="nih_guide",
        source_record_id="2",
        opportunity_number="NOT-CA-26-011",
        parent_opportunity_number="PA-99-999",
        record_kind="overlay",
        close_date=None,
    )
    assert resolve_overlay_parents([overlay]) == 1
    assert overlay.unresolved_parent is True
