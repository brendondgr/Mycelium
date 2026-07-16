"""Content-app signals: prune → stale for reminder subscriptions (R2).

Belt-and-braces alongside the daily job ordering (ingest → rebuild → tick → prune).
The ordering means the tick normally sees a moved deadline live before prune can
delete the item; this hook is the backstop for any path that deletes a
``ContentItem`` out from under a live reminder (prune, admin, a future refactor).

The danger §3.2 warns about: a deadline moves *earlier* into the past, the item is
pruned, and the reminder is left holding a snapshot with the **old, later** date that
it would cheerfully fire on. On delete we resync each active reminder's snapshot from
the still-alive projection one last time and mark it **stale** only when its deadline
is no longer in the future (past or gone) — a reminder whose deadline is genuinely
still upcoming survives on its snapshot and keeps firing (the item merely disappeared
from the source).
"""

from __future__ import annotations

from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.utils import timezone

from apps.content.models import ContentItem, ReminderSubscription
from apps.content.reminders import resync_snapshot


@receiver(pre_delete, sender=ContentItem)
def mark_reminders_stale_on_content_delete(sender, instance, **kwargs) -> None:
    # pre_delete fires before the SET_NULL cascade, so ``content`` still points here
    # and the item's ContentDeadline rows are still readable for one last resync.
    today = timezone.now().date()
    subs = ReminderSubscription.objects.filter(
        content=instance, state=ReminderSubscription.State.ACTIVE
    )
    for sub in subs:
        resync_snapshot(sub)
        if sub.due_date is None or sub.due_date < today:
            sub.state = ReminderSubscription.State.STALE
            sub.save(update_fields=["state", "updated_at"])
