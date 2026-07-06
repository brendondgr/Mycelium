""""New" tagging + one-week pinning for high-fit opportunities.

A newly-posted grant/conference that is a strong fit for a user should jump to the
top of their list and carry a "New — worth a look" tag for its first week, so it
isn't buried under older content. This computes that per user, per run:

* **Recently first-seen** — the item's immutable ``metadata.first_seen`` (written
  once at ingest, never reset on refresh) is within ``new_window_days`` of today.
* **High fit** — the item's percent match is at or above the ``percentile`` (default
  80th) of this user's model-scored matches for the area.

An item that is both gets ``is_new=True`` and a ``pinned_until`` one week after it
was first seen. The read layer pins (and shows the tag) while ``pinned_until`` is
still in the future — because ``first_seen`` never moves, the pin window is stable
across nightly re-runs and the tag naturally expires after a week.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, timedelta

from django.utils import timezone

from .models import ContentItem

DEFAULT_NEW_WINDOW_DAYS = 7
DEFAULT_PIN_DAYS = 7
DEFAULT_PERCENTILE = 80.0


def _parse_iso_date(value: str | None) -> date | None:
    """Date part of an ISO datetime/date string, or ``None`` if unparseable."""
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _percentile(values: Sequence[float], pct: float) -> float | None:
    """Linear-interpolated percentile of ``values`` (``None`` when empty)."""
    xs = sorted(values)
    if not xs:
        return None
    if len(xs) == 1:
        return xs[0]
    rank = (len(xs) - 1) * (pct / 100.0)
    lo = int(rank)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (rank - lo)


def compute_pins(
    suggestions: Sequence[dict],
    items_by_id: Mapping[str, ContentItem],
    *,
    today: str | None = None,
    new_window_days: int = DEFAULT_NEW_WINDOW_DAYS,
    pin_days: int = DEFAULT_PIN_DAYS,
    percentile: float = DEFAULT_PERCENTILE,
) -> dict[str, dict]:
    """Map ``content_id -> {"is_new", "pinned_until", "first_seen"}`` for a run.

    ``suggestions`` are this user's ranked opportunity suggestions (each with a
    ``content_id`` and possibly a ``match_percent``); ``items_by_id`` resolves the
    ``ContentItem`` for its ``first_seen``.
    """
    today_d = date.fromisoformat(today) if today else timezone.now().date()
    window_start = today_d - timedelta(days=new_window_days)

    matches = [
        s["match_percent"]
        for s in suggestions
        if s.get("match_percent") is not None
    ]
    threshold = _percentile(matches, percentile)

    out: dict[str, dict] = {}
    for suggestion in suggestions:
        cid = suggestion["content_id"]
        item = items_by_id.get(cid)
        meta = (item.metadata or {}) if item is not None else {}
        first_seen = meta.get("first_seen", "")
        first_seen_date = _parse_iso_date(first_seen)

        recently_new = first_seen_date is not None and first_seen_date >= window_start
        match_percent = suggestion.get("match_percent")
        high_fit = (
            threshold is not None
            and match_percent is not None
            and match_percent >= threshold
        )
        is_new = recently_new and high_fit
        pinned_until = None
        if is_new and first_seen_date is not None:
            pinned_until = (first_seen_date + timedelta(days=pin_days)).isoformat()

        out[cid] = {
            "is_new": is_new,
            "pinned_until": pinned_until,
            "first_seen": first_seen,
        }
    return out
