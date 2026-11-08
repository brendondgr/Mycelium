"""The object model's invariants.

Mostly one idea: the things the briefing says must not be collapsed are not
collapsed.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tools.retrieval.collect.conferences.record import (
    SUBMISSION_TYPES,
    ConferenceInstance,
    ConferenceSeries,
    Deadline,
)

NOW = datetime(2026, 8, 16, 12, 0, 0, tzinfo=UTC)


def test_deadlines_are_an_ordered_list_not_a_single_field():
    """278 of 1,161 instances carry more than one round and VLDB carries twelve.

    A schema with one `deadline` column is wrong on a quarter of the corpus.
    """
    record = ConferenceInstance(
        source="ccf_deadlines",
        source_record_id="vldb|2027",
        deadlines=[
            Deadline(kind="abstract", instant="2026-03-25T17:00:00Z", round_label="r1"),
            Deadline(kind="submission", instant="2026-04-01T17:00:00Z", round_label="r1"),
            Deadline(kind="submission", instant="2026-05-01T17:00:00Z", round_label="r2"),
        ],
    )
    assert len(record.deadlines) == 3
    # All three gate submission: the abstract registration counts, because
    # missing it disqualifies you even with the paper written.
    assert len(record.submission_deadlines) == 3
    assert {d.round_label for d in record.deadlines} == {"r1", "r2"}


def test_the_next_submission_deadline_is_the_soonest_future_one():
    record = ConferenceInstance(
        source="s",
        source_record_id="1",
        deadlines=[
            Deadline(kind="submission", instant="2026-01-01T00:00:00Z", round_label="past"),
            Deadline(kind="submission", instant="2027-01-01T00:00:00Z", round_label="later"),
            Deadline(kind="submission", instant="2026-10-01T00:00:00Z", round_label="soonest"),
        ],
    )
    assert record.next_submission_deadline(NOW).round_label == "soonest"


def test_relevance_ignores_the_event_date_entirely():
    """Filtering on event date instead of deadline is the single most common
    design error here: a June conference with a January deadline is worthless to
    surface in March."""
    record = ConferenceInstance(
        source="s",
        source_record_id="1",
        event_start="2027-06-01",  # comfortably in the future
        deadlines=[Deadline(kind="submission", instant="2026-01-01T00:00:00Z")],
    )
    assert record.is_relevant(NOW) is False


def test_a_notification_date_does_not_make_a_record_relevant():
    record = ConferenceInstance(
        source="s",
        source_record_id="1",
        deadlines=[Deadline(kind="notification", instant="2027-06-01T00:00:00Z")],
    )
    assert record.is_relevant(NOW) is False


def test_only_abstract_and_submission_count_as_submission_types():
    assert SUBMISSION_TYPES == {"abstract", "submission"}
    assert Deadline(kind="abstract").is_submission is True
    assert Deadline(kind="camera_ready").is_submission is False


def test_year_label_and_event_dates_are_stored_separately():
    """AAAI's 2026 edition is held in January 2026 with a 2025 deadline, and six
    instances in the structured corpus contradict their own date string."""
    record = ConferenceInstance(
        source="ccf_deadlines",
        source_record_id="sigmetrics27",
        year_label="2025",
        event_dates_text="June 7-11, 2027",
        event_start="2027-06-07",
    )
    assert record.year_label == "2025"
    assert record.event_start == "2027-06-07"


def test_deadline_identity_is_type_and_round_not_the_date():
    """An extension changes the date; it must still be recognised as the same
    entry or every extension appends a duplicate."""
    before = Deadline(kind="submission", round_label="Round 1", instant="2027-01-01T00:00:00Z")
    after = Deadline(kind="submission", round_label="round 1", instant="2027-03-01T00:00:00Z")
    assert before.identity == after.identity


def test_an_unknown_record_kind_is_a_parse_bug_not_a_new_category():
    with pytest.raises(ValueError, match="unknown record kind"):
        ConferenceInstance(source="s", source_record_id="1", record_kind="symposium")


def test_an_unknown_deadline_type_is_rejected():
    with pytest.raises(ValueError, match="unknown deadline type"):
        Deadline(kind="whenever")


def test_a_track_points_at_its_parent_instance():
    """Workshops and tracks are separate records with their own deadlines, not
    folded into the parent."""
    track = ConferenceInstance(
        source="s",
        source_record_id="ws1",
        record_kind="workshop",
        series_key="conf/x",
        parent_instance_key="conf/parent|2027|conference",
    )
    assert track.record_kind == "workshop"
    assert track.parent_instance_key == "conf/parent|2027|conference"


def test_contributing_sources_defaults_to_the_originating_source():
    record = ConferenceInstance(source="wikicfp", source_record_id="1")
    assert record.contributing_sources == ["wikicfp"]


def test_instance_key_falls_back_to_the_source_id_before_resolution():
    """Records arrive before the resolve stage has given them a series key."""
    unresolved = ConferenceInstance(source="wikicfp", source_record_id="194568")
    assert unresolved.instance_key == "src:wikicfp:194568"

    resolved = unresolved.copy(series_key="conf/cogmi", year_label="2026")
    assert resolved.instance_key == "conf/cogmi|2026|conference"


def test_an_estimated_deadline_is_never_indistinguishable_from_a_confirmed_one():
    assert Deadline(kind="submission").is_estimated is False
    assert Deadline(kind="submission", is_estimated=True).is_estimated is True


def test_series_carries_acronym_variants_because_venues_rename():
    series = ConferenceSeries(
        series_key="conf/nips",
        acronym="NeurIPS",
        acronym_variants=["NIPS"],
        name_variants=["Advances in Neural Information Processing Systems"],
    )
    assert "NIPS" in series.acronym_variants
