"""Change history: what moved, phrased so a reader can act on it."""

from __future__ import annotations

from tools.retrieval.collect.grants.history import diff_rows
from tools.retrieval.collect.grants.store import Store
from tools.retrieval.tests.collect.grants.conftest import opportunity

AT = "2026-08-17T09:00:00Z"


def rows(**overrides):
    return opportunity(**overrides).to_row()


# --- what counts as a change ---------------------------------------------


def test_a_deadline_move_is_recorded_with_its_direction():
    """An extension and a date brought forward are opposite news."""
    before = rows(close_date="2026-09-22")
    after = rows(close_date="2027-12-01")
    (change,) = [c for c in diff_rows("k", before, after, AT) if c.field == "close_date"]

    assert change.direction == "extended"
    assert change.describe() == "deadline: 2026-09-22 → 2027-12-01 (extended)"


def test_a_deadline_brought_forward_says_so():
    before = rows(close_date="2027-12-01")
    after = rows(close_date="2026-09-22")
    (change,) = [c for c in diff_rows("k", before, after, AT) if c.field == "close_date"]
    assert change.direction == "brought forward"


def test_money_and_eligibility_changes_are_tracked():
    changed = {
        c.field
        for c in diff_rows(
            "k",
            rows(award_ceiling=100.0, cost_sharing=False),
            rows(award_ceiling=200.0, cost_sharing=True),
            AT,
        )
    }
    assert {"award_ceiling", "cost_sharing"} <= changed


def test_money_reads_as_money_not_as_digits_to_count():
    (change,) = [
        c
        for c in diff_rows(
            "k", rows(award_ceiling=20_000_000.0), rows(award_ceiling=40_000_000.0), AT
        )
        if c.field == "award_ceiling"
    ]
    assert change.describe() == "award ceiling: 20.0M → 40.0M"


def test_bookkeeping_churn_is_not_a_change():
    """Recording that a payload's byte order shifted would bury the deadline move."""
    assert diff_rows("k", rows(), rows(), AT) == []
    assert (
        diff_rows("k", rows(source_url="https://a"), rows(source_url="https://b"), AT) == []
    )


def test_a_description_edit_is_noted_without_storing_the_text():
    """A revision history of 5 KB descriptions would dwarf the store it describes."""
    (change,) = diff_rows("k", rows(description="old " * 500), rows(description="new " * 500), AT)
    assert change.field == "description"
    assert change.describe() == "description rewritten"
    assert (change.before, change.after) == ("", "")


def test_a_list_change_reads_as_text_not_json():
    (change,) = [
        c
        for c in diff_rows(
            "k",
            rows(additional_due_dates=["2026-10-05"]),
            rows(additional_due_dates=["2026-10-05", "2027-02-05"]),
            AT,
        )
        if c.field == "additional_due_dates"
    ]
    assert change.after == "2026-10-05, 2027-02-05"
    assert "[" not in change.describe()


# --- through the store ----------------------------------------------------


def test_the_store_records_an_amendment(tmp_path):
    with Store(tmp_path / "db.sqlite") as store:
        record = opportunity(close_date="2026-09-22", award_ceiling=20_000_000.0)
        store.upsert_all([record])
        assert store.changes_for(record.stable_key) == []

        record.close_date = "2027-12-01"
        record.award_ceiling = 40_000_000.0
        store.upsert_all([record], now=AT)

        described = [c.describe() for c in store.changes_for(record.stable_key)]

    assert "deadline: 2026-09-22 → 2027-12-01 (extended)" in described
    assert any("award ceiling" in line for line in described)


def test_an_unchanged_record_writes_no_history(tmp_path):
    """The same guard that keeps last_fetched untouched keeps history clean."""
    with Store(tmp_path / "db.sqlite") as store:
        record = opportunity()
        store.upsert_all([record])
        store.upsert_all([record])
        store.upsert_all([record])
        assert store.changes_for(record.stable_key) == []


def test_a_source_reported_extension_is_recorded_on_first_sight(tmp_path):
    """755 Grants.gov records report the deadline they used to have.

    Without this, an extension announced before we started watching would be
    invisible forever.
    """
    with Store(tmp_path / "db.sqlite") as store:
        record = opportunity(close_date="2026-11-17", original_close_date="2026-09-30")
        store.upsert_all([record])
        (change,) = store.changes_for(record.stable_key)

    assert change.field == "close_date"
    assert change.direction == "extended"
    assert change.describe() == "deadline: 2026-09-30 → 2026-11-17 (extended)"


def test_no_phantom_extension_when_the_original_matches(tmp_path):
    with Store(tmp_path / "db.sqlite") as store:
        record = opportunity(close_date="2026-11-17", original_close_date="2026-11-17")
        store.upsert_all([record])
        assert store.changes_for(record.stable_key) == []


def test_changes_since_filters_by_time(tmp_path):
    with Store(tmp_path / "db.sqlite") as store:
        record = opportunity(close_date="2026-01-01")
        store.upsert_all([record], now="2026-01-01T00:00:00Z")
        record.close_date = "2026-06-01"
        store.upsert_all([record], now="2026-06-01T00:00:00Z")
        record.close_date = "2026-09-01"
        store.upsert_all([record], now="2026-09-01T00:00:00Z")

        assert len(store.changes_since("")) == 2
        assert len(store.changes_since("2026-07-01")) == 1
