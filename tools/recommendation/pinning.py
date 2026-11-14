""""New" tagging + one-week pinning for freshly-seen recommendations.

A newly-seen item (a grant, conference, fellowship, or paper) that surfaced for a
user carries a "New" tag for its first week and, when the run judged it worth
reading (verdict ``read`` or ``skim``), leads their list so it isn't buried under
older content. Being in a feed is not by itself a judgement of fit — an item
ranked 84th is in it too — so the pin lifts only judged fits
(:mod:`tools.delivery.feed_order`); this module decides which items are **new**.

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

**Updated is not New.** Conferences and grants are commonly extracted from pages
hosting many events, and such a page gaining a deadline (or moving one) is a
reason to look at a listing again — but the listing is not new, and calling it
new would be a lie about what changed. ``tools.retrieval.collect.ingest`` stamps
``metadata["refreshed_at"]`` only when something *actionable* moved, and an item
inside that window is pinned exactly like a new one but reported as
``is_updated`` so the card can say which it is. This does not touch what "new"
means to the report: that is slate entry (``tools.recommendation.top_feed``), decided by
the nightly whole-corpus re-rank, and nothing here changes it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, timedelta

from django.utils import timezone

from tools.retrieval.models import ContentItem

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


def first_seen_date(item: ContentItem | None) -> date | None:
    """Public wrapper: the date part of :func:`_first_seen`, or ``None``.

    Lets other modules (the carry-forward LLM-slot selection in
    :mod:`.digest_selection`) reuse the exact same "when was this first seen"
    reckoning pinning uses, without reaching into the private helper.
    """
    day, _iso = _first_seen(item)
    return day


def compute_pins(
    suggestions: Sequence[dict],
    items_by_id: Mapping[str, ContentItem],
    *,
    today: str | None = None,
    new_window_days: int = DEFAULT_NEW_WINDOW_DAYS,
    pin_days: int = DEFAULT_PIN_DAYS,
) -> dict[str, dict]:
    """Map ``content_id -> {is_new, is_updated, pinned_until, first_seen}``.

    ``suggestions`` are this target's surfaced items for the area (each with a
    ``content_id``); ``items_by_id`` resolves the ``ContentItem`` for its
    first-seen date. Every item first seen within ``new_window_days`` is flagged
    new and pinned for a week — no fit gate, since the feed is already
    interest-thresholded, so "new in the feed" is exactly what we highlight.

    An item that is not new but whose *source page* moved something actionable
    inside the same window is pinned on the same terms and flagged
    ``is_updated``. New wins when both hold: an item first seen three days ago
    whose deadline then moved is still, to the reader, new.
    """
    today_d = date.fromisoformat(today) if today else timezone.now().date()
    window_start = today_d - timedelta(days=new_window_days)

    out: dict[str, dict] = {}
    for suggestion in suggestions:
        cid = suggestion["content_id"]
        item = items_by_id.get(cid)
        first_seen_date, first_seen = _first_seen(item)

        is_new = first_seen_date is not None and first_seen_date >= window_start
        refreshed = (
            _parse_iso_date((item.metadata or {}).get("refreshed_at"))
            if item
            else None
        )
        is_updated = (
            not is_new and refreshed is not None and refreshed >= window_start
        )

        pinned_until = None
        anchor = first_seen_date if is_new else refreshed if is_updated else None
        if anchor is not None:
            pinned_until = (anchor + timedelta(days=pin_days)).isoformat()

        out[cid] = {
            "is_new": is_new,
            "is_updated": is_updated,
            "pinned_until": pinned_until,
            "first_seen": first_seen,
        }
    return out
