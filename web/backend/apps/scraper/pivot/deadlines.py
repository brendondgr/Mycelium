"""Typed submission deadlines for conferences (abstract vs. manuscript/full paper).

Vendored (pure parts) from the ProQuest tool's ``conferences/deadlines.py``. Pivot
lists a conference's timeline as one ``deadlines`` string, e.g.::

    04 Apr 2025 (Abstract Submission Deadline); 10 Oct 2025 (Manuscript Deadline)

Across the corpus this uses exactly two labels, so a deterministic parse is exact.
This turns that string (plus ``event_dates``) into a structured, *time-relative*
view: what kind of submission is still due and by when, whether the event is still
upcoming, and a human summary. Pure — no models, DB, or network.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .normalize import normalize_date

# A dated, labeled timeline entry: "<date-token> (<Label>)". The date may be
# word-format ("04 Apr 2025") or already ISO ("2025-04-04", post-normalize).
_ENTRY_RE = re.compile(
    r"(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}|\d{4}-\d{2}-\d{2})\s*\(([^)]*)\)"
)
# A bare date token, for the single-date ``event_dates`` string.
_DATE_RE = re.compile(r"\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}|\d{4}-\d{2}-\d{2}")

# How each kind is phrased in the human summary.
_KIND_PHRASE = {"abstract": "abstract", "manuscript": "full paper"}


@dataclass(frozen=True)
class Deadline:
    kind: str  # "abstract" | "manuscript" | "other"
    date: str  # ISO YYYY-MM-DD ("" if the token was unparseable)
    label: str  # the original parenthetical label


def _classify(label: str) -> str:
    low = label.lower()
    if "abstract" in low:
        return "abstract"
    if "manuscript" in low or "full paper" in low or "full-paper" in low:
        return "manuscript"
    return "other"


def parse_deadlines(text: str) -> list[Deadline]:
    """Parse a ``deadlines`` string into a list of typed :class:`Deadline`."""
    out = []
    for token, label in _ENTRY_RE.findall(text or ""):
        out.append(
            Deadline(
                kind=_classify(label),
                date=normalize_date(token),
                label=label.strip(),
            )
        )
    return out


def first_event_date(event_dates: str) -> str:
    """The (single) event date as ISO, or "" if absent/unparseable."""
    m = _DATE_RE.search(event_dates or "")
    return normalize_date(m.group(0)) if m else ""


def _kind_deadline(deadlines, kind, today):
    """(soonest-future-or-latest-past date, is_open) for one submission kind."""
    dates = sorted(d.date for d in deadlines if d.kind == kind and d.date)
    if not dates:
        return None, False
    future = [d for d in dates if d >= today]
    if future:
        return future[0], True
    return dates[-1], False


def submission_status(deadlines, event_date: str, today: str) -> dict:
    """Time-relative submission view from parsed ``deadlines`` + the event date."""
    abstract_deadline, abstract_open = _kind_deadline(deadlines, "abstract", today)
    manuscript_deadline, manuscript_open = _kind_deadline(
        deadlines, "manuscript", today
    )

    requires = [
        k
        for k in ("abstract", "manuscript")
        if any(d.kind == k and d.date for d in deadlines)
    ]
    has_any = any(d.date for d in deadlines)

    future = sorted(
        (d.date, d.kind)
        for d in deadlines
        if d.date and d.date >= today and d.kind in ("abstract", "manuscript")
    )
    next_deadline, next_kind = future[0] if future else (None, None)

    if next_deadline:
        status = "open"
    elif has_any:
        status = "closed"
    else:
        status = "unknown"

    event_upcoming = (event_date >= today) if event_date else None

    if status == "open":
        parts = []
        if abstract_open:
            parts.append(f"abstract due {abstract_deadline}")
        if manuscript_open:
            parts.append(f"full paper due {manuscript_deadline}")
        summary = " · ".join(parts) if parts else "submissions open"
    elif status == "closed":
        summary = "submissions closed"
    else:
        summary = "no submission deadline listed"
    summary = summary[0].upper() + summary[1:]
    if event_date:
        summary += f" · event {event_date}"

    return {
        "abstract_deadline": abstract_deadline,
        "manuscript_deadline": manuscript_deadline,
        "abstract_open": abstract_open,
        "manuscript_open": manuscript_open,
        "requires": requires,
        "next_deadline": next_deadline,
        "next_kind": next_kind,
        "event_date": event_date,
        "event_upcoming": event_upcoming,
        "status": status,
        "summary": summary,
    }


def conference_status(rec: dict, today: str) -> dict:
    """Convenience wrapper: pull the fields off a conference record and analyze."""
    deadlines = parse_deadlines(rec.get("deadlines", ""))
    event_date = first_event_date(rec.get("event_dates", ""))
    return submission_status(deadlines, event_date, today)
