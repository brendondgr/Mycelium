"""One uniform status shape for a grant or conference + visibility filters.

Vendored from the ProQuest tool's ``recommend/schedule.py``. Wraps the conference
deadline analysis (:mod:`.deadlines`) and the grant application deadline into a
single per-record ``status`` dict, and provides the visibility filter the prune
and match steps apply:

* ``is_visible`` — hide opportunities already in the past (a conference whose event
  date has passed, a grant whose application deadline has passed). Future events are
  kept even if their submission window closed — you can still attend — and unknown
  dates are kept (can't prove they're past). This is exactly the prune rule.
"""

from __future__ import annotations

from .deadlines import conference_status


def opportunity_status(rec: dict, area: str, today: str) -> dict:
    """A uniform status dict for one record (conference or grant)."""
    if area == "conferences":
        return conference_status(rec, today)

    # Grants: the application deadline is the single actionable date.
    deadline = (rec.get("deadline_date") or "").strip()
    open_ = (deadline >= today) if deadline else None
    if deadline:
        status = "open" if open_ else "closed"
        summary = (
            f"Application due {deadline}"
            if open_
            else f"Application deadline passed ({deadline})"
        )
    else:
        status = "unknown"
        summary = "No application deadline listed"
    return {
        "apply_deadline": deadline or None,
        "next_deadline": deadline or None,
        "next_kind": "application" if deadline else None,
        "event_upcoming": open_,  # for grants the deadline *is* the actionable date
        "status": status,
        "summary": summary,
    }


def is_visible(status: dict, include_past: bool) -> bool:
    """Drop past events / expired grants unless ``include_past``.

    Keeps anything whose actionable date is upcoming, and anything with an unknown
    date (``event_upcoming is None``) — better to show than to wrongly hide. This
    is the exact rule the daily prune uses to decide what to delete.
    """
    if include_past:
        return True
    return status.get("event_upcoming") is not False
