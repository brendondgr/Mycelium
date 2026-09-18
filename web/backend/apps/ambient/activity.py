"""The per-source, per-day counters — a count, never a name.

Kept apart from :mod:`.service` so that anything which discards a message —
the gateway's door on arrival, the read boundary at night — can say so in the
same place, the same way.
"""

from __future__ import annotations

from django.db.models import F
from django.utils import timezone

from .models import SourceActivity


def bump(source, field_name: str, *, heard: bool = True, by: int = 1) -> None:
    """Add ``by`` to a counter for today, creating the row if it is the first."""
    if by <= 0:
        return
    today = timezone.localdate()
    activity, _ = SourceActivity.objects.get_or_create(source=source, day=today)
    updates = {field_name: F(field_name) + by}
    if heard:
        updates["heard"] = F("heard") + by
    SourceActivity.objects.filter(pk=activity.pk).update(**updates)
