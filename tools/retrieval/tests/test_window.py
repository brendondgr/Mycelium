from datetime import UTC, datetime

from tools.retrieval.window import ScanWindow, shift_months


def test_around_today_spans_two_months_back_one_forward(monkeypatch):
    fixed = datetime(2026, 6, 29, 12, 0, tzinfo=UTC)

    class _FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed

    monkeypatch.setattr("tools.retrieval.window.datetime", _FixedDateTime)

    window = ScanWindow.around_today()
    assert window.since_date == "2026-04-29"
    assert window.until_date == "2026-07-29"
    assert str(window) == "2026-04-29 → 2026-07-29"


def test_shift_months_clamps_day_on_short_month():
    # Mar 31 minus one month clamps to Feb's last day (non-leap year).
    assert shift_months(datetime(2026, 3, 31), -1).date().isoformat() == "2026-02-28"
    # Plain month subtraction keeps the day when it is valid.
    assert shift_months(datetime(2026, 1, 31), -1).date().isoformat() == "2025-12-31"


def test_shift_months_handles_leap_year():
    assert shift_months(datetime(2024, 1, 31), 1).date().isoformat() == "2024-02-29"


def test_shift_months_crosses_year_boundary():
    assert shift_months(datetime(2026, 1, 15), -2).date().isoformat() == "2025-11-15"
    assert shift_months(datetime(2026, 12, 15), 2).date().isoformat() == "2027-02-15"


def test_custom_window_spans():
    fixed = datetime(2026, 3, 15, tzinfo=UTC)

    class _FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed

    import tools.retrieval.window as window_module

    original = window_module.datetime
    window_module.datetime = _FixedDateTime
    try:
        window = ScanWindow.around_today(months_back=3, months_forward=0)
        assert window.since_date == "2025-12-15"
        assert window.until_date == "2026-03-15"
    finally:
        window_module.datetime = original
