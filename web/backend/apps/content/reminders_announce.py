"""DEADLINE_MOVED announcements (R6): tell live reminders when a deadline changed.

R0's rebuild stamps ``changed_at`` + ``previous_due_date`` / ``previous_confidence`` on
a ``ContentDeadline`` when its date moves or an anticipated deadline is confirmed. This
step finds recently-changed rows that have active subscriptions and sends a change
notice on the **same channel and mentions** as the reminder — one per subscription per
move — mirrored in-app as ``Notification(kind=deadline_moved)``. It never re-fires the
reminder itself; the tick owns that. The anticipated→confirmed case reads differently
("now confirmed"), the highest-value variant.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.utils import timezone

from apps.content.models import (
    ContentDeadline,
    Notification,
    ReminderSubscription,
)
from apps.content.reminders import _KIND_LABEL, recipients

# How far back a rebuild's changes stay announceable (the daily run stamps "now").
CHANGE_WINDOW = timedelta(days=1)

_Confidence = ContentDeadline.Confidence


@dataclass
class AnnounceResult:
    scanned: int = 0
    announced: int = 0

    def as_dict(self) -> dict:
        return {"scanned": self.scanned, "announced": self.announced}


def announce_deadline_changes(today=None, *, now=None) -> AnnounceResult:
    """Announce recently-moved deadlines to their live subscriptions."""
    now = now or timezone.now()
    today = today or now.date()
    result = AnnounceResult()

    changed = (
        ContentDeadline.objects.filter(
            changed_at__gte=now - CHANGE_WINDOW, due_date__isnull=False
        )
        .select_related("content")
        .order_by("changed_at")
    )
    for row in changed:
        subs = ReminderSubscription.objects.filter(
            content_id=row.content_id,
            deadline_kind=row.kind,
            state=ReminderSubscription.State.ACTIVE,
        ).select_related("target_lab")
        for sub in subs:
            result.scanned += 1
            if _announce_one(sub, row, today, now):
                result.announced += 1
    return result


def _announce_one(sub, row, today, now) -> bool:
    prefix = f"deadline_moved:{sub.id}:{row.due_date:%Y-%m-%d}"
    if Notification.objects.filter(dedupe_key__startswith=prefix).exists():
        return False  # already announced this move (one per subscription per move)

    days = (row.due_date - today).days
    title, body = _change_copy(sub, row, days)

    for user in recipients(sub):
        Notification.objects.get_or_create(
            dedupe_key=f"{prefix}:{user.id}",
            defaults={
                "user": user,
                "kind": Notification.Kind.DEADLINE_MOVED,
                "content": sub.content,
                "title": title,
                "body": body,
                "url": sub.url,
            },
        )

    # Same Discord surface as the reminder itself, with its own idempotency key.
    #
    # The Discord side previously borrowed the in-app dedupe above and could re-send
    # after a partial failure — the notification rows already existed, so the guard
    # returned early on some paths but not others. Its own key closes that: the outbox
    # unique constraint makes a repeat announcement a no-op rather than a second ping.
    dedupe_key = f"deadline_moved:{sub.id}:{row.due_date:%Y-%m-%d}"
    if sub.target_user_id:
        from apps.content.reminders_discord import send_personal_dm

        send_personal_dm(sub, title, body, dedupe_key=dedupe_key)
    else:
        from apps.content.reminders_discord import send_lab_channel

        outcome = send_lab_channel(sub, title, body, dedupe_key=dedupe_key)
        if outcome.has_unlinked is not None:
            _sync_unlinked(sub, outcome.has_unlinked)
    return True


def _change_copy(sub, row, days: int):
    kind_label = _KIND_LABEL.get(sub.deadline_kind, "Deadline")
    when = f"{row.due_date:%b %d}"
    if days <= 0:
        left = "due today"
    elif days == 1:
        left = "1 day left"
    else:
        left = f"{days} days left"

    confirmed = (
        row.confidence == _Confidence.CONFIRMED
        and row.previous_confidence == _Confidence.ANTICIPATED
    )
    date_moved = bool(row.previous_due_date and row.previous_due_date != row.due_date)

    if confirmed and not date_moved:
        body = f"{kind_label} deadline is now confirmed: {when} — {left}."
    elif date_moved:
        old_when = f"{row.previous_due_date:%b %d}"
        lead = "now confirmed and " if confirmed else ""
        body = f"{kind_label} deadline {lead}moved from {old_when} to {when} — {left}."
    else:
        body = f"{kind_label} deadline updated: {when} — {left}."
    return sub.title, body


def _sync_unlinked(sub, has_unlinked) -> None:
    if sub.has_unlinked_targets != has_unlinked:
        sub.has_unlinked_targets = has_unlinked
        sub.save(update_fields=["has_unlinked_targets", "updated_at"])
