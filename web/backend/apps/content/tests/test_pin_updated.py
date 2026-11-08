""""Updated" pins a moved listing without calling it new.

The distinction is the point. A conference is usually extracted from a page
hosting many events; when that page gains an event, the old ones stay on it. So
"the source changed" is a real signal worth re-surfacing, and "this arrived" is a
different claim that would be false about the same row.
"""

from __future__ import annotations

import pytest
from tools.retrieval.models import ContentItem

from apps.content.pinning import compute_pins

pytestmark = pytest.mark.django_db

TODAY = "2026-08-17"
LONG_AGO = "2026-01-01T00:00:00+00:00"
RECENTLY = "2026-08-15T00:00:00+00:00"


def _item(**meta) -> ContentItem:
    return ContentItem.objects.create(
        type=ContentItem.Type.CONFERENCE,
        source="conf:ccf_deadlines",
        external_id=f"c-{len(meta)}-{meta.get('first_seen', '')}",
        metadata=meta,
    )


def _pins(item: ContentItem) -> dict:
    cid = str(item.id)
    return compute_pins([{"content_id": cid}], {cid: item}, today=TODAY)[cid]


def test_an_old_listing_whose_deadline_moved_is_updated_and_pinned():
    pin = _pins(_item(first_seen=LONG_AGO, refreshed_at=RECENTLY))
    assert pin["is_new"] is False
    assert pin["is_updated"] is True
    assert pin["pinned_until"] == "2026-08-22"  # a week from the refresh


def test_new_wins_when_both_could_apply():
    """An item first seen three days ago whose deadline then moved is still,
    to the reader, new — labelling it "updated" would bury the more useful fact."""
    pin = _pins(_item(first_seen="2026-08-14T00:00:00+00:00", refreshed_at=RECENTLY))
    assert pin["is_new"] is True
    assert pin["is_updated"] is False


def test_a_stale_refresh_stops_pinning():
    """The pin runs out on the refresh's own clock, so a months-old change does
    not sit at the top of the feed forever."""
    pin = _pins(_item(first_seen=LONG_AGO, refreshed_at=LONG_AGO))
    assert pin["is_updated"] is False
    assert pin["pinned_until"] is None


def test_an_unchanged_old_listing_is_neither():
    pin = _pins(_item(first_seen=LONG_AGO))
    assert (pin["is_new"], pin["is_updated"], pin["pinned_until"]) == (
        False,
        False,
        None,
    )
