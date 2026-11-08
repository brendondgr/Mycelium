"""Timezone handling, which the briefing calls out as the thing that will burn you.

Being off by one day on a submission deadline is a user-visible, trust-destroying
failure, and it is what happens by default. The headline assertion is the
briefing's own smoke check: an AoE deadline dated the 15th resolves to noon UTC
on the 16th.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tools.retrieval.collect.conferences.timezones import (
    AOE,
    TimezoneBasisError,
    is_future,
    parse_basis,
    parse_local,
    resolve_instant,
    to_iso_instant,
)


def instant(value: str, basis: str) -> str | None:
    return to_iso_instant(resolve_instant(value, basis))


# --- the briefing's headline check ---------------------------------------


def test_aoe_deadline_dated_the_15th_resolves_to_noon_utc_on_the_16th():
    """Briefing section 10, verbatim. Verified by hand against a known venue."""
    assert instant("2026-01-15 23:59:59", "AoE") == "2026-01-16T11:59:59Z"


def test_a_bare_aoe_date_is_the_end_of_that_day_not_its_midnight():
    """"The deadline is the 15th" means the 15th is still usable.

    Truncating to midnight would silently move every such deadline a day early.
    """
    assert instant("2026-01-15", "AoE") == "2026-01-16T11:59:59Z"


def test_aoe_offset_is_utc_minus_twelve():
    assert AOE.utcoffset(None).total_seconds() == -12 * 3600


# --- AoE and UTC-12 are the same thing spelled two ways ------------------


def test_aoe_and_utc_minus_twelve_resolve_identically():
    """The upstream project migrated the label and never backfilled, so 2026
    entries still split 199 AoE / 45 UTC-12 for the same meaning."""
    assert instant("2026-01-15 23:59:59", "AoE") == instant("2026-01-15 23:59:59", "UTC-12")


def test_the_raw_label_is_preserved_by_parse_basis():
    """They resolve alike but they are not the same claim: AoE is semantic,
    UTC-12 may be a literal offset the contributor meant."""
    assert parse_basis("AoE") == ("AoE", "aoe")
    assert parse_basis("UTC-12") == ("UTC-12", "offset")


# --- PT is not an offset -------------------------------------------------


def test_pt_is_daylight_aware_and_differs_by_an_hour_across_the_year():
    """Ten instances use PT, including VLDB (CCF-A / CORE A*) with 12 rounds.

    The upstream project's own Python CLI raises ValueError on PT and swallows
    it, silently dropping every one of them.
    """
    winter = instant("2026-01-15 23:59:59", "PT")  # PST, UTC-8
    summer = instant("2026-07-15 23:59:59", "PT")  # PDT, UTC-7
    assert winter == "2026-01-16T07:59:59Z"
    assert summer == "2026-07-16T06:59:59Z"


def test_pt_dst_boundaries_match_the_second_sunday_in_march_rule():
    before = instant("2026-03-07 12:00:00", "PT")  # still PST
    after = instant("2026-03-09 12:00:00", "PT")  # PDT began Mar 8 2026
    assert before == "2026-03-07T20:00:00Z"
    assert after == "2026-03-09T19:00:00Z"


# --- offsets -------------------------------------------------------------


@pytest.mark.parametrize(
    ("basis", "expected"),
    [
        ("UTC", "2026-06-15T23:59:59Z"),
        ("UTC+0", "2026-06-15T23:59:59Z"),
        ("UTC-8", "2026-06-16T07:59:59Z"),
        ("UTC+8", "2026-06-15T15:59:59Z"),
        ("UTC-4", "2026-06-16T03:59:59Z"),
        ("UTC+1", "2026-06-15T22:59:59Z"),
    ],
)
def test_utc_offsets_resolve(basis, expected):
    assert instant("2026-06-15 23:59:59", basis) == expected


# --- refusing to guess ---------------------------------------------------


def test_an_unknown_basis_raises_rather_than_defaulting_to_utc():
    """Never infer a timezone silently. A wrong default is invisible and wrong
    by up to a day; an exception is visible and fixable."""
    with pytest.raises(TimezoneBasisError):
        parse_basis("Narnia Standard Time")
    with pytest.raises(TimezoneBasisError):
        parse_basis("")


def test_an_implausible_offset_is_rejected():
    with pytest.raises(TimezoneBasisError):
        parse_basis("UTC+37")


# --- placeholders --------------------------------------------------------


@pytest.mark.parametrize("value", ["TBD", "TBA", "tbd", "", "N/A", "none"])
def test_placeholder_deadlines_do_not_become_instants(value):
    """Three deadlines in the structured corpus are the literal string TBD.

    A placeholder that parsed to a date would be a fabricated deadline.
    """
    assert resolve_instant(value, "AoE") is None
    assert parse_local(value) is None


def test_an_unquoted_yaml_datetime_is_accepted_rather_than_raising():
    """Every deadline upstream is quoted, so YAML yields str. One unquoted
    contributor PR flips a value to datetime and strptime would raise."""
    assert instant(datetime(2026, 1, 15, 23, 59, 59), "AoE") == "2026-01-16T11:59:59Z"


# --- futureness ----------------------------------------------------------


def test_is_future_compares_instants_not_dates():
    now = datetime(2026, 1, 16, 10, 0, 0, tzinfo=UTC)
    # 11:59:59Z on the 16th is still ahead of 10:00Z on the 16th, even though the
    # deadline is "dated the 15th".
    assert is_future("2026-01-16T11:59:59Z", now) is True
    assert is_future("2026-01-16T09:59:59Z", now) is False


def test_a_null_instant_is_not_future():
    """An undated deadline cannot be actionable. Treating it as open would put
    TBD rounds at the top of a list sorted by urgency."""
    assert is_future(None, datetime(2026, 1, 1, tzinfo=UTC)) is False
    assert is_future("", datetime(2026, 1, 1, tzinfo=UTC)) is False
