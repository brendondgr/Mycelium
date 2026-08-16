"""Persistence, the open-set invariant, and idempotency."""

from __future__ import annotations

from datetime import date

from apps.scraper.collect.grants.store import Store
from apps.scraper.tests.collect.grants.conftest import opportunity

TODAY = date(2026, 8, 15)


def make_store(tmp_path) -> Store:
    return Store(tmp_path / "opportunities.db")


# --- upsert --------------------------------------------------------------


def test_insert_then_reread(tmp_path):
    with make_store(tmp_path) as store:
        stats = store.upsert_all([opportunity()])
        assert stats.inserted == 1
        (stored,) = store.all_records()
        assert stored.opportunity_number == "PA-25-001"
        assert stored.first_seen is not None


def test_rerunning_an_unchanged_record_writes_nothing(tmp_path):
    with make_store(tmp_path) as store:
        store.upsert_all([opportunity()], now="2026-08-15T00:00:00Z")
        stats = store.upsert_all([opportunity()], now="2026-08-16T00:00:00Z")

    assert stats.inserted == 0
    assert stats.updated == 0
    assert stats.unchanged == 1


def test_last_fetched_is_not_touched_when_nothing_changed(tmp_path):
    # If it were, "updated" would be true on every run and the idempotency check
    # in the smoke list could never fail.
    with make_store(tmp_path) as store:
        store.upsert_all([opportunity()], now="2026-08-15T00:00:00Z")
        store.upsert_all([opportunity()], now="2026-08-16T00:00:00Z")
        (stored,) = store.all_records()
    assert stored.last_fetched == "2026-08-15T00:00:00Z"


def test_a_genuine_source_change_is_an_update(tmp_path):
    with make_store(tmp_path) as store:
        store.upsert_all([opportunity()])
        stats = store.upsert_all([opportunity(close_date="2027-06-01")])
    assert stats.updated == 1


def test_first_seen_survives_every_later_run(tmp_path):
    with make_store(tmp_path) as store:
        store.upsert_all([opportunity()], now="2026-01-01T00:00:00Z")
        store.upsert_all([opportunity(title="Renamed")], now="2026-09-09T00:00:00Z")
        (stored,) = store.all_records()
    assert stored.first_seen == "2026-01-01T00:00:00Z"
    assert stored.last_fetched == "2026-09-09T00:00:00Z"


def test_records_from_two_sources_with_one_number_share_a_row(tmp_path):
    with make_store(tmp_path) as store:
        store.upsert_all([opportunity(source="grants_gov", source_record_id="1")])
        store.upsert_all([opportunity(source="nih_guide", source_record_id="2")])
        assert store.count() == 1


# --- prune ---------------------------------------------------------------


def test_prune_removes_a_passed_deadline(tmp_path):
    with make_store(tmp_path) as store:
        store.upsert_all([opportunity(close_date="2025-01-01")])
        assert store.prune(TODAY) == 1
        assert store.count() == 0


def test_prune_keeps_a_rolling_opportunity(tmp_path):
    # Null close date means "open indefinitely", not "unknown, discard".
    with make_store(tmp_path) as store:
        store.upsert_all([opportunity(close_date=None)])
        assert store.prune(TODAY) == 0
        assert store.count() == 1


def test_prune_keeps_a_recurring_cycle_with_a_future_round(tmp_path):
    with make_store(tmp_path) as store:
        store.upsert_all(
            [opportunity(close_date="2025-02-01", additional_due_dates=["2027-02-01"])]
        )
        assert store.prune(TODAY) == 0


def test_prune_removes_a_recurring_cycle_once_every_round_has_passed(tmp_path):
    with make_store(tmp_path) as store:
        store.upsert_all(
            [opportunity(close_date="2024-02-01", additional_due_dates=["2025-02-01"])]
        )
        assert store.prune(TODAY) == 1


def test_prune_judges_an_overlay_on_its_own_expiration(tmp_path):
    expired = opportunity(
        source_record_id="o1",
        opportunity_number="NOT-CA-24-001",
        record_kind="overlay",
        close_date=None,
        expiration_date="2025-01-01",
    )
    live = opportunity(
        source_record_id="o2",
        opportunity_number="NOT-CA-27-001",
        record_kind="overlay",
        close_date=None,
        expiration_date="2028-01-01",
    )
    with make_store(tmp_path) as store:
        store.upsert_all([expired, live])
        assert store.prune(TODAY) == 1
        (survivor,) = store.all_records()
        assert survivor.opportunity_number == "NOT-CA-27-001"


def test_an_expired_overlay_dies_while_its_open_parent_lives(tmp_path):
    parent = opportunity(source_record_id="p", opportunity_number="PA-25-172", close_date="2028-01-01")
    overlay = opportunity(
        source_record_id="o",
        opportunity_number="NOT-CA-24-001",
        record_kind="overlay",
        parent_opportunity_number="PA-25-172",
        close_date=None,
        expiration_date="2025-01-01",
    )
    with make_store(tmp_path) as store:
        store.upsert_all([parent, overlay])
        assert store.prune(TODAY) == 1
        (survivor,) = store.all_records()
        assert survivor.record_kind == "standalone"


# --- bookkeeping ---------------------------------------------------------


def test_round_trip_preserves_every_field(tmp_path):
    original = opportunity(
        categories=["a", "b"],
        additional_due_dates=["2027-01-01"],
        contributing_sources=["grants_gov", "nih_guide"],
        review_candidates=["num:X"],
        award_floor=1.0,
        award_ceiling=2.0,
        expected_awards=3,
        currency="EUR",
        raw={"nested": {"value": 1}},
    )
    with make_store(tmp_path) as store:
        store.upsert_all([original])
        (stored,) = store.all_records()

    assert stored.categories == ["a", "b"]
    assert stored.additional_due_dates == ["2027-01-01"]
    assert set(stored.contributing_sources) == {"grants_gov", "nih_guide"}
    assert stored.review_candidates == ["num:X"]
    assert stored.currency == "EUR"
    assert stored.raw == {"nested": {"value": 1}}


def test_errors_are_recorded_per_run(tmp_path):
    with make_store(tmp_path) as store:
        store.record_error("run1", "sbir", "fetch", "HTTP 403")
        (row,) = store.errors_for("run1")
        assert row["source"] == "sbir"
        assert "403" in row["message"]
