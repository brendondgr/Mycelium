"""Pure transformations: dates to ISO 8601, amounts to numbers, HTML to text.

Stage 3 of the pipeline. No network, no I/O, no clock reads except where a caller
passes ``today`` in explicitly — so every function here is directly testable.

The date and text helpers are shared with the conferences collector and live in
:mod:`apps.scraper.collect.core.text`; they are re-exported here so the original import
path still works. What stays is the funding-specific half: money parsing and the
funder-assigned opportunity number.
"""

from __future__ import annotations

import re
from datetime import date

from apps.scraper.collect.core.text import (
    clean_text,
    compact_json,
    dedupe_preserving_order,
    html_to_text,
    is_past,
    join_description,
    normalize_title,
    soonest_future,
    to_iso_date,
)

__all__ = [
    "clean_dates",
    "clean_text",
    "compact_json",
    "dedupe_preserving_order",
    "html_to_text",
    "is_past",
    "join_description",
    "last_due",
    "normalize_opportunity_number",
    "normalize_title",
    "select_next_due",
    "soonest_future",
    "to_amount",
    "to_amount_range",
    "to_int",
    "to_iso_date",
]


# --- due dates -----------------------------------------------------------


def clean_dates(values: list[str | None]) -> list[str]:
    """Sorted, deduplicated, parseable ISO dates from a mixed list."""
    out: set[str] = set()
    for value in values:
        if not value:
            continue
        try:
            date.fromisoformat(value)
        except (ValueError, TypeError):
            continue
        out.add(value)
    return sorted(out)


def select_next_due(dates: list[str | None], today: date) -> str | None:
    """The round a reader should be shown, from every round we know about.

    This is the single rule two adapters previously disagreed about, each in a
    different direction. The EU portal stored the *first* entry of its deadline
    list, so a recurring call whose 2021 round had long passed advertised a 2021
    deadline while its next round was weeks away. NIH stored the *last* receipt
    date of the whole cycle, so a call with a round due in six weeks advertised
    one seventeen months out. One buries a live opportunity and the other hides
    urgency; both are the same mistake, which is picking a fixed end of a list
    instead of asking which round is next.

    When every round has passed the latest is returned rather than None. The
    record should have been pruned by then, and if it somehow was not, showing
    the most recent date is at least not a claim that something older is
    upcoming.
    """
    known = clean_dates(dates)
    if not known:
        return None
    return soonest_future(known, today) or known[-1]


def last_due(dates: list[str | None]) -> str | None:
    """The final round — the date after which the opportunity is truly finished.

    Distinct from :func:`select_next_due` on purpose. Pruning must key on this,
    because deleting a recurring opportunity the moment its nearest round passes
    would throw away every remaining cycle.
    """
    known = clean_dates(dates)
    return known[-1] if known else None


# --- amounts -------------------------------------------------------------

_MONEY = re.compile(r"\$?\s*([\d,]+(?:\.\d+)?)\s*(million|billion|m\b|k\b)?", re.IGNORECASE)
_MULTIPLIER = {"million": 1_000_000, "m": 1_000_000, "billion": 1_000_000_000, "k": 1_000}

#: Above this, a "figure" field is really a pasted budget paragraph. We refuse to
#: guess a number out of prose that long rather than carry garbage into a numeric
#: column (briefing section 7).
_PROSE_LENGTH = 120


def to_amount(value: object) -> float | None:
    """Coerce a funder's award field to a number, or None.

    Two documented failure modes are handled explicitly: literal ``"none"``
    strings (Grants.gov emits these constantly) and fields where a funder pasted
    an entire budget paragraph instead of a figure.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value) if value else None

    text = str(value).strip()
    if not text or text.lower() in {"none", "null", "n/a", "tbd", "0", "$0"}:
        return None

    if len(text) > _PROSE_LENGTH:
        # A paragraph. Take the largest dollar figure named in it if there is one
        # and it is unambiguous; otherwise drop the field entirely.
        figures = _all_amounts(text)
        return max(figures) if len(figures) == 1 else None

    figures = _all_amounts(text)
    if not figures:
        return None
    # A text range ("$50,000 to $250,000") in a single-value field: keep the low
    # end for a floor-ish field is not knowable here, so callers get the range via
    # to_amount_range. A lone value is the common case.
    return figures[0]


def to_amount_range(value: object) -> tuple[float | None, float | None]:
    """Split a text range like "$50,000 - $250,000" into (floor, ceiling)."""
    if value is None:
        return (None, None)
    text = str(value).strip()
    if len(text) > _PROSE_LENGTH:
        return (None, None)
    figures = _all_amounts(text)
    if len(figures) >= 2:
        return (min(figures), max(figures))
    if len(figures) == 1:
        return (figures[0], None)
    return (None, None)


def _all_amounts(text: str) -> list[float]:
    out: list[float] = []
    for match in _MONEY.finditer(text):
        digits = match.group(1).replace(",", "")
        if not digits or digits == ".":
            continue
        try:
            amount = float(digits)
        except ValueError:
            continue
        suffix = (match.group(2) or "").lower().rstrip(".")
        amount *= _MULTIPLIER.get(suffix, 1)
        if amount:
            out.append(amount)
    return out


def to_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value or None
    text = str(value).strip()
    match = re.search(r"\d+", text.replace(",", ""))
    if not match:
        return None
    parsed = int(match.group(0))
    return parsed or None


# --- identifiers ---------------------------------------------------------

_NUMBER_NOISE = re.compile(r"[^A-Z0-9]+")


def normalize_opportunity_number(value: object) -> str:
    """Canonicalize a funder-assigned number for cross-source comparison.

    Case, whitespace, and punctuation vary freely between how Grants.gov and NIH
    write the same identifier ("PAR-25-274" vs "par 25 274"), so all of it goes.
    """
    if value is None:
        return ""
    text = str(value).strip().upper()
    if not text:
        return ""
    return _NUMBER_NOISE.sub("", text)
