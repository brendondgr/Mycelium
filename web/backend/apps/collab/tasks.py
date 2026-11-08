"""Scheduled work for collaboration matching."""

from __future__ import annotations

from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from .consent import prune_appearances
from .models import CollaborationSetting


def notify_renewals(now=None) -> int:
    """Tell people whose open-to-collaboration setting ends soon.

    A bell notification once per period, and a Mylo DM when their Discord is
    linked. It says when the setting ends and nothing else — never anything
    about who searched or how often they appeared.
    """
    from tools.delivery.models import Notification

    now = now or timezone.now()
    soon = now + timedelta(days=settings.COLLAB_RENEWAL_NOTICE_DAYS)
    due = CollaborationSetting.objects.filter(
        open=True,
        expires_at__gt=now,
        expires_at__lte=soon,
        renewal_notified_at__isnull=True,
    ).select_related("user")
    sent = 0
    for setting in due:
        ends = setting.expires_at.date().isoformat()
        title = "Your open-to-collaboration setting ends soon"
        body = (
            f"People who search for collaborators will stop finding you on {ends}. "
            "Renew it in Account → Collaboration to stay findable."
        )
        Notification.objects.get_or_create(
            dedupe_key=f"collab-renewal:{setting.user_id}:{ends}",
            defaults={
                "user": setting.user,
                "kind": Notification.Kind.COLLAB_RENEWAL,
                "title": title,
                "body": body,
            },
        )
        try:
            from apps.integrations.services.outbox import enqueue_dm

            enqueue_dm(
                dedupe_key=f"collab-renewal:{setting.user_id}:{ends}",
                kind="collab_renewal",
                user=setting.user,
                content=f"{title}. {body}",
            )
        except Exception:  # noqa: BLE001 - the bell already carries it
            pass
        setting.renewal_notified_at = now
        setting.save(update_fields=["renewal_notified_at", "updated_at"])
        sent += 1
    return sent


@shared_task(name="apps.collab.daily")
def daily() -> dict:
    from .evaluation import report_harm
    from .matcher import prune_logs

    return {
        # Before pruning, so the last day's searches are all still there.
        "harm": report_harm(),
        "renewals": notify_renewals(),
        "appearances_pruned": prune_appearances(),
        "search_logs_pruned": prune_logs(),
    }
