"""Content-app signals: prune → stale for reminder subscriptions (R2).

Belt-and-braces alongside the daily job ordering (ingest → rebuild → tick → prune).
The ordering means the tick normally sees a moved deadline live before prune can
delete the item; this hook is the backstop for any path that deletes a
``ContentItem`` out from under a live reminder (prune, admin, a future refactor).

The rule itself lives in ``reminders.stale_reminders_for_deleted_content`` so it is
reachable with an explicit reference date; a ``pre_delete`` receiver cannot take one.
"""

from __future__ import annotations

from django.db.models.signals import pre_delete
from django.dispatch import receiver
from tools.retrieval.models import ContentItem

from apps.content.reminders import stale_reminders_for_deleted_content


@receiver(pre_delete, sender=ContentItem)
def mark_reminders_stale_on_content_delete(sender, instance, **kwargs) -> None:
    # pre_delete fires before the SET_NULL cascade, so ``content`` still points here
    # and the item's ContentDeadline rows are still readable for one last resync.
    stale_reminders_for_deleted_content(instance)
