""""New" tagging + one-week pinning for freshly-seen recommendations.

A newly-seen item (a grant, conference, fellowship, or paper) that surfaced for a
user should jump to the top of their list and carry a "New" tag for its first
week, so it isn't buried under older content. Everything in a feed has already
cleared the interest/match threshold, so being *in* the feed already means "worth
recommending"; this only decides which of those are **new** and pin them.

An item is new when it was first seen within ``new_window_days`` of today:

* **Opportunities** (grants/conferences/fellowships) use the immutable
  ``metadata.first_seen`` written once at ingest and never reset on refresh.
* **Papers** have no ``first_seen`` field, so we fall back to the ingest date
  (``ContentItem.created_at``, set once on first insert and never rewritten by
  re-scrapes) — the day the paper entered the store.

A new item gets ``is_new=True`` and a ``pinned_until`` one week after it was first
seen. The read layer pins (and shows the tag) while ``pinned_until`` is still in
the future — because the first-seen date never moves, the pin window is stable
across nightly re-runs and the item naturally drops back into plain
percent-match order once it is more than a week old.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, timedelta

from django.utils import timezone

from .models import ContentItem

DEFAULT_NEW_WINDOW_DAYS = 7
DEFAULT_PIN_DAYS = 7


def _parse_iso_date(value: str | None) -> date | None:
    """Date part of an ISO datetime/date string, or ``None`` if unparseable."""
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _first_seen(item: ContentItem | None) -> tuple[date | None, str]:
    """When an item was first seen: ``(date, iso-string)``.

    Prefers the immutable ``metadata.first_seen`` (opportunities); falls back to
    the ingest date ``created_at`` (papers, which carry no ``first_seen``). Returns
    ``(None, "")`` when neither is available.
    """
    if item is None:
        return None, ""
    meta = item.metadata or {}
    raw = meta.get("first_seen")
    parsed = _parse_iso_date(raw)
    if parsed is not None:
        return parsed, str(raw)
    created = getattr(item, "created_at", None)
    if created is not None:
        day = timezone.localdate(created)
        return day, day.isoformat()
    return None, ""


def compute_pins(
    suggestions: Sequence[dict],
    items_by_id: Mapping[str, ContentItem],
    *,
    today: str | None = None,
    new_window_days: int = DEFAULT_NEW_WINDOW_DAYS,
    pin_days: int = DEFAULT_PIN_DAYS,
) -> dict[str, dict]:
    """Map ``content_id -> {"is_new", "pinned_until", "first_seen"}`` for a run.

    ``suggestions`` are this target's surfaced items for the area (each with a
    ``content_id``); ``items_by_id`` resolves the ``ContentItem`` for its
    first-seen date. Every item first seen within ``new_window_days`` is flagged
    new and pinned for a week — no fit gate, since the feed is already
    interest-thresholded, so "new in the feed" is exactly what we highlight.
    """
    today_d = date.fromisoformat(today) if today else timezone.now().date()
    window_start = today_d - timedelta(days=new_window_days)

    out: dict[str, dict] = {}
    for suggestion in suggestions:
        cid = suggestion["content_id"]
        first_seen_date, first_seen = _first_seen(items_by_id.get(cid))

        is_new = first_seen_date is not None and first_seen_date >= window_start
        pinned_until = None
        if is_new and first_seen_date is not None:
            pinned_until = (first_seen_date + timedelta(days=pin_days)).isoformat()

        out[cid] = {
            "is_new": is_new,
            "pinned_until": pinned_until,
            "first_seen": first_seen,
        }
    return out
