"""The store's two conference-specific behaviours: retention and extensions.

Both are places where copying the funding collector would be a bug.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.scraper.collect.conferences.record import (
    ConferenceInstance,
    ConferenceSeries,
    Deadline,
)
from apps.scraper.collect.conferences.store import ConferenceStore, merge_deadlines

NOW = datetime(2026, 8, 16, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def store(tmp_path):
    with ConferenceStore(tmp_path / "conferences.db") as opened:
        yield opened


def deadline(**overrides) -> Deadline:
    base = {
        "kind": "submission",
        "raw": "2027-01-15 23:59:59",
        "instant": "2027-01-16T11:59:59Z",
        "basis": "AoE",
        "round_label": "round 1",
        "source": "ccf_deadlines",
    }
    return Deadline(**{**base, **overrides})


def instance(**overrides) -> ConferenceInstance:
    base = {
        "source": "ccf_deadlines",
        "source_record_id": "sigmod|sigmod|2027",
        "series_key": "conf/sigmod",
        "title": "ACM Conference on Management of Data",
        "acronym": "SIGMOD",
        "year_label": "2027",
        "deadlines": [deadline()],
    }
    return ConferenceInstance(**{**base, **overrides})


# --- retention, not pruning ----------------------------------------------


def test_a_past_instance_is_marked_inactive_and_is_still_retrievable(store):
    """The funding store deletes expired records. Doing that here would throw
    away 1,516 of 1,605 deadline entries and destroy the longevity signal."""
    past = instance(
        source_record_id="old",
        year_label="2024",
        deadlines=[deadline(instant="2024-01-16T11:59:59Z")],
    )
    store.upsert_instances([past])
    assert store.mark_inactive(NOW) == 1

    stored = store.all_instances()
    assert len(stored) == 1, "the record must still exist"
    assert stored[0].active is False
    assert store.count_instances() == 1
    assert store.count_instances(active_only=True) == 0


def test_a_future_instance_stays_active(store):
    store.upsert_instances([instance()])
    store.mark_inactive(NOW)
    assert store.count_instances(active_only=True) == 1


def test_an_instance_whose_only_future_date_is_a_notification_is_inactive(store):
    """Surface on the submission deadline, never on anything else.

    A venue that has stopped accepting papers is not actionable, however many
    future dates its timeline still carries.
    """
    record = instance(
        deadlines=[
            deadline(kind="submission", instant="2026-01-16T11:59:59Z"),
            deadline(kind="notification", instant="2027-03-01T00:00:00Z", round_label=""),
        ]
    )
    store.upsert_instances([record])
    store.mark_inactive(NOW)
    assert store.count_instances(active_only=True) == 0


def test_an_abstract_deadline_alone_keeps_a_record_active(store):
    """Missing the abstract registration disqualifies you even if the paper is
    ready, so it counts as the venue still being open."""
    record = instance(deadlines=[deadline(kind="abstract", instant="2027-01-01T00:00:00Z")])
    store.upsert_instances([record])
    store.mark_inactive(NOW)
    assert store.count_instances(active_only=True) == 1


# --- deadline extensions -------------------------------------------------


def test_an_extension_updates_the_existing_entry_rather_than_appending(store):
    """Extensions are extremely common. Appending would show a venue that moved
    its deadline twice as three separate rounds."""
    store.upsert_instances([instance()])

    extended = instance(deadlines=[deadline(instant="2027-02-16T11:59:59Z", raw="2027-02-15")])
    stats = store.upsert_instances([extended])

    stored = store.all_instances()[0]
    assert len(stored.deadlines) == 1, "one round, not two"
    assert stored.deadlines[0].instant == "2027-02-16T11:59:59Z"
    assert stored.deadlines[0].extension_count == 1
    assert stats.extensions == 1


def test_repeated_extensions_accumulate_because_the_count_is_the_signal():
    """One extension is ordinary; four is a predatory red flag."""
    stored = [deadline(instant="2027-01-16T11:59:59Z")]
    for month in (2, 3, 4):
        stored, _ = merge_deadlines(stored, [deadline(instant=f"2027-0{month}-16T11:59:59Z")])
    assert len(stored) == 1
    assert stored[0].extension_count == 3


def test_distinct_rounds_stay_distinct(store):
    """SIGMOD runs four rounds and VLDB twelve. They must not collapse."""
    rounds = [
        deadline(round_label=f"round {n}", instant=f"2027-0{n}-16T11:59:59Z") for n in (1, 2, 3, 4)
    ]
    store.upsert_instances([instance(deadlines=rounds)])
    stored = store.all_instances()[0]
    assert len(stored.deadlines) == 4
    assert [d.round_label for d in stored.deadlines] == [
        "round 1",
        "round 2",
        "round 3",
        "round 4",
    ]


def test_a_bare_date_source_cannot_overwrite_an_explicit_timezone():
    """Caught by the dedupe tests: the quality ordering was being undone here.

    A source that only knows the calendar date silently moved a properly-zoned
    deadline by up to a day -- the exact failure the three-value timezone model
    exists to prevent.
    """
    zoned = [deadline(instant="2027-01-16T11:59:59Z", basis="AoE")]
    merged, extensions = merge_deadlines(
        zoned, [deadline(instant="2027-01-15T00:00:00Z", basis="inferred:date-only")]
    )
    assert merged[0].basis == "AoE"
    assert merged[0].instant == "2027-01-16T11:59:59Z"
    assert extensions == 0


def test_an_equally_trustworthy_source_may_still_update():
    """The guard must not freeze a deadline against a legitimate extension."""
    merged, extensions = merge_deadlines(
        [deadline(instant="2027-01-16T11:59:59Z", basis="AoE")],
        [deadline(instant="2027-02-16T11:59:59Z", basis="AoE")],
    )
    assert merged[0].instant == "2027-02-16T11:59:59Z"
    assert extensions == 1


def test_a_real_basis_may_replace_an_inferred_one():
    merged, _ = merge_deadlines(
        [deadline(instant="2027-01-15T00:00:00Z", basis="inferred:date-only")],
        [deadline(instant="2027-01-16T11:59:59Z", basis="AoE")],
    )
    assert merged[0].basis == "AoE"


def test_a_deadline_moving_earlier_is_not_counted_as_an_extension():
    stored = [deadline(instant="2027-03-16T11:59:59Z")]
    stored, extensions = merge_deadlines(stored, [deadline(instant="2027-01-16T11:59:59Z")])
    assert extensions == 0
    assert stored[0].extension_count == 0


def test_merged_deadlines_come_back_in_chronological_order():
    """Several source instances are unordered; a couple repeat a value."""
    merged, _ = merge_deadlines(
        [deadline(round_label="late", instant="2027-06-01T00:00:00Z")],
        [deadline(round_label="early", instant="2027-01-01T00:00:00Z")],
    )
    assert [d.round_label for d in merged] == ["early", "late"]


# --- idempotency ---------------------------------------------------------


def test_a_second_identical_run_writes_nothing_at_all(store):
    """The check is only meaningful because the store refuses to touch
    last_fetched when nothing else changed."""
    store.upsert_instances([instance()])
    stats = store.upsert_instances([instance()])
    assert (stats.inserted, stats.updated) == (0, 0)
    assert stats.unchanged == 1


def test_first_seen_survives_an_update(store):
    store.upsert_instances([instance()], now="2026-01-01T00:00:00Z")
    store.upsert_instances([instance(title="Renamed")], now="2026-06-01T00:00:00Z")
    stored = store.all_instances()[0]
    assert stored.first_seen == "2026-01-01T00:00:00Z"
    assert stored.last_fetched == "2026-06-01T00:00:00Z"


def test_deactivating_a_record_does_not_make_the_next_run_report_a_change(store):
    """`active` is computed from the clock, not the payload. If it counted as a
    source change, every run after a deadline passed would report an update and
    the idempotency check could never fail."""
    past = instance(deadlines=[deadline(instant="2024-01-16T11:59:59Z")])
    store.upsert_instances([past])
    store.mark_inactive(NOW)
    stats = store.upsert_instances([past])
    assert (stats.inserted, stats.updated) == (0, 0)


# --- series --------------------------------------------------------------


def test_series_round_trip_preserves_rankings_from_several_systems(store):
    """CCF, CORE and THCPL arrive from different places and must not overwrite
    each other."""
    series = ConferenceSeries(
        series_key="conf/sigmod",
        acronym="SIGMOD",
        full_name="ACM Conference on Management of Data",
        rankings={
            "ccf": {"rank": "A", "edition": "2022"},
            "core": {"rank": "A*", "edition": "ICORE2026"},
            "thcpl": {"rank": "A", "edition": ""},
        },
        dblp_key="conf/sigmod",
        dblp_found=True,
        indexed_years=44,
        trust_tier="A",
    )
    store.upsert_series([series])
    stored = store.all_series()[0]
    assert stored.rankings["core"] == {"rank": "A*", "edition": "ICORE2026"}
    assert stored.rankings["ccf"]["rank"] == "A"
    assert stored.indexed_years == 44


def test_tier_c_is_counted_not_dropped(store):
    """Quarantined records must be visibly withheld, never invisibly missing."""
    store.upsert_series(
        [
            ConferenceSeries(series_key="conf/real", trust_tier="A"),
            ConferenceSeries(series_key="gen:spam", trust_tier="C"),
        ]
    )
    store.upsert_instances(
        [
            instance(series_key="conf/real", source_record_id="a", year_label="2027"),
            instance(series_key="gen:spam", source_record_id="b", year_label="2027"),
        ]
    )
    assert store.count_by_tier() == {"A": 1, "C": 1}
    assert store.quarantined_count() == 1


def test_an_unknown_trust_tier_is_rejected():
    with pytest.raises(ValueError, match="unknown trust tier"):
        ConferenceSeries(series_key="x", trust_tier="Gold")


def test_a_series_is_only_surfaceable_with_a_tier():
    assert ConferenceSeries(series_key="x", trust_tier="A").is_surfaceable is True
    assert ConferenceSeries(series_key="x", trust_tier="B").is_surfaceable is True
    assert ConferenceSeries(series_key="x", trust_tier="C").is_surfaceable is False
    assert ConferenceSeries(series_key="x").is_surfaceable is False


def test_deadlines_are_ordered_on_insert_not_only_on_merge(store):
    """A first insert must store the same order a merge would produce.

    Sorting only inside ``merge_deadlines`` meant the initial insert kept
    whatever order the adapter emitted and the *second* run sorted it, so a
    corpus reported one phantom update per affected record and a freshly built
    store could fail the "multi-round venues are ordered" check until it had
    been collected twice.
    """
    record = instance(
        source_record_id="unordered",
        deadlines=[
            deadline(kind="abstract", instant="2026-12-05T18:30:00Z"),
            deadline(kind="submission", instant="2026-11-23T18:30:00Z"),
        ],
    )
    assert store.upsert_instances([record]).inserted == 1

    stored = store.all_instances()[0]
    assert [d.instant for d in stored.deadlines] == [
        "2026-11-23T18:30:00Z",
        "2026-12-05T18:30:00Z",
    ]

    # And the second run therefore has nothing to say about it.
    again = store.upsert_instances(
        [
            instance(
                source_record_id="unordered",
                deadlines=[
                    deadline(kind="abstract", instant="2026-12-05T18:30:00Z"),
                    deadline(kind="submission", instant="2026-11-23T18:30:00Z"),
                ],
            )
        ]
    )
    assert (again.inserted, again.updated, again.unchanged) == (0, 0, 1)
