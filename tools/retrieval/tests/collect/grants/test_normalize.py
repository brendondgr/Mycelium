"""Normalization: the failure modes the briefing names explicitly."""

from __future__ import annotations

from datetime import date

import pytest

from tools.retrieval.collect.grants.normalize import (
    clean_dates,
    clean_text,
    html_to_text,
    is_past,
    join_description,
    last_due,
    normalize_opportunity_number,
    select_next_due,
    soonest_future,
    to_amount,
    to_amount_range,
    to_int,
    to_iso_date,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-11-17", "2026-11-17"),
        ("11/17/2026", "2026-11-17"),
        ("Nov 17, 2026 12:00:00 AM EST", "2026-11-17"),
        ("2026-11-17-00-00-00", "2026-11-17"),
        ("2027-04-06T00:00:00.000+0000", "2027-04-06"),  # EU portal
        ("Fri, 14 Aug 2026 02:33:00 EST", "2026-08-14"),  # RSS pubDate
        ("August 17, 2026", "2026-08-17"),
        ("01-05-2025", "2025-01-05"),  # NIH OpenDate: dashes but not ISO
    ],
)
def test_dates_from_every_source_format(raw, expected):
    assert to_iso_date(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "none", "N/A", "Multiple dates, see announcement."])
def test_unparseable_dates_are_none_not_guesses(raw):
    assert to_iso_date(raw) is None


def test_null_close_date_is_not_past():
    # The rolling-opportunity rule: null means open indefinitely, never "discard".
    assert is_past(None, date(2026, 8, 15)) is False


def test_soonest_future_picks_the_next_unpassed_round():
    dates = ["2025-01-01", "2027-05-01", "2026-09-01"]
    assert soonest_future(dates, date(2026, 8, 15)) == "2026-09-01"


def test_soonest_future_is_none_when_every_round_has_passed():
    assert soonest_future(["2020-01-01"], date(2026, 8, 15)) is None


# --- which round to show -------------------------------------------------
#
# The regression these guard is the one bug two adapters had in opposite
# directions: the EU portal displayed the first entry of a deadline list and NIH
# displayed the last.

TODAY = date(2026, 8, 16)

#: The real ESC-HUMAID-2021-QUAL-LABEL-FP schedule, which advertised a 2021
#: deadline while its next round was five weeks away.
EU_ROUNDS = [
    "2021-09-21", "2022-03-23", "2022-09-21", "2023-03-15",
    "2023-09-20", "2024-09-23", "2025-09-22", "2026-09-21",
]


def test_next_due_is_the_next_future_round_not_the_first():
    assert select_next_due(EU_ROUNDS, TODAY) == "2026-09-21"


def test_next_due_is_the_next_future_round_not_the_last():
    """The NIH shape: a cycle whose final receipt date is years out."""
    cycle = ["2026-10-05", "2027-02-05", "2027-06-05", "2028-01-07"]
    assert select_next_due(cycle, TODAY) == "2026-10-05"


def test_last_due_is_the_final_round_whichever_way_the_list_arrives():
    assert last_due(EU_ROUNDS) == "2026-09-21"
    assert last_due(list(reversed(EU_ROUNDS))) == "2026-09-21"


def test_next_due_falls_back_to_the_latest_when_all_rounds_have_passed():
    """Not None: showing the most recent date beats claiming something older is upcoming."""
    assert select_next_due(["2026-02-05", "2026-06-05"], TODAY) == "2026-06-05"


def test_next_due_of_nothing_is_none():
    assert select_next_due([], TODAY) is None
    assert select_next_due([None, ""], TODAY) is None


def test_a_round_due_today_has_not_passed():
    """A deadline is live until the day ends, not from the moment the day starts."""
    assert select_next_due(["2026-08-16", "2027-01-01"], TODAY) == "2026-08-16"


def test_clean_dates_drops_unparseable_entries_rather_than_guessing():
    assert clean_dates(["2026-01-01", "not a date", None, "2025-06-01"]) == [
        "2025-06-01",
        "2026-01-01",
    ]


def test_clean_dates_deduplicates():
    assert clean_dates(["2026-01-01", "2026-01-01"]) == ["2026-01-01"]


# --- amounts -------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("$250,000", 250_000.0),
        ("250000", 250_000.0),
        (250000, 250_000.0),
        ("$1.5 million", 1_500_000.0),
        ("none", None),  # Grants.gov writes this literal string constantly
        ("", None),
        (None, None),
        ("0", None),
    ],
)
def test_amount_coercion(raw, expected):
    assert to_amount(raw) == expected


def test_a_pasted_budget_paragraph_never_becomes_a_number():
    prose = (
        "The total program funding depends on the availability of funds and the "
        "receipt of a sufficient number of meritorious applications; NIH intends "
        "to commit $3,000,000 in FY2027 and $4,000,000 in FY2028 to this program."
    )
    # Two competing figures inside prose is exactly the case where guessing is
    # worse than dropping the field.
    assert to_amount(prose) is None


def test_a_paragraph_with_one_unambiguous_figure_yields_it():
    prose = "Awards are expected to be approximately $500,000 in total costs per year, " + "x" * 60
    assert to_amount(prose) == 500_000.0


def test_text_range_splits_into_floor_and_ceiling():
    assert to_amount_range("$50,000 to $250,000") == (50_000.0, 250_000.0)


def test_expected_awards_parses_out_of_prose():
    assert to_int("approximately 5 awards") == 5
    assert to_int("none") is None


# --- text ----------------------------------------------------------------


def test_html_keeps_paragraph_and_list_structure():
    text = html_to_text("<p>Goal one.</p><ul><li>First</li><li>Second</li></ul><p>Goal two.</p>")
    assert "Goal one." in text
    assert "- First" in text
    assert "- Second" in text
    # Collapsing to a single line measurably degrades the payload; it must not happen.
    assert "\n" in text


def test_html_drops_scripts_and_unescapes_entities():
    assert html_to_text("<script>evil()</script><p>A &amp; B</p>") == "A & B"


def test_join_description_concatenates_and_dedupes():
    assert join_description("<p>One</p>", "<p>One</p>", "<p>Two</p>") == "One\n\nTwo"


def test_clean_text_collapses_whitespace():
    assert clean_text("  a \n  b  ") == "a b"


# --- identifiers ---------------------------------------------------------


def test_opportunity_number_normalizes_case_space_and_punctuation():
    variants = ["PAR-25-274", "par 25 274", "  PAR–25–274 ".replace("–", "-"), "Par.25.274"]
    normalized = {normalize_opportunity_number(value) for value in variants}
    assert normalized == {"PAR25274"}


def test_distinct_numbers_stay_distinct():
    assert normalize_opportunity_number("PAR-25-274") != normalize_opportunity_number("PA-25-274")
