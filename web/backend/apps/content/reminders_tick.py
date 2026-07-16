"""The daily reminder tick — compute-on-read, seal-on-fire, one message per day.

Runs once a day, ordered **after** ingest + ``ContentDeadline`` rebuild and
**before** prune (R2), so it always reads live deadlines. For each active
subscription it (1) resyncs the snapshot from the projection, (2) marks it stale if
there is no date, (3) marks it fired-out if the deadline has passed, (4) collects the
offsets whose fire date has arrived and are not yet sealed, (5) fires **one** message
carrying the *actual* days remaining, and (6) seals every triggering offset. The
one-message-per-subscription-per-day cap means a deadline jumping forward past three
offsets sends one message, not three.

R1 delivery is **in-app only** (writes :class:`Notification` rows). Discord DM (R3)
and lab channel (R5) delivery slot into ``_deliver`` without changing this control
flow.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.utils import timezone

from apps.content.models import Notification, ReminderFire, ReminderSubscription
from apps.content.reminders import (
    idempotency_key,
    offset_fire_date,
    recipients,
    reminder_copy,
    resync_snapshot,
)


@dataclass
class TickResult:
    """A tally of one tick run."""

    scanned: int = 0
    fired: int = 0
    staled: int = 0
    fired_out: int = 0
    notifications: int = 0

    def as_dict(self) -> dict:
        return {
            "scanned": self.scanned,
            "fired": self.fired,
            "staled": self.staled,
            "fired_out": self.fired_out,
            "notifications": self.notifications,
        }


def run_tick(today=None, *, now=None) -> TickResult:
    """Fire due reminders once each. ``today`` defaults to the current date."""
    today = today or timezone.now().date()
    now = now or timezone.now()
    result = TickResult()

    subs = ReminderSubscription.objects.filter(
        state=ReminderSubscription.State.ACTIVE
    ).prefetch_related("offsets")

    for sub in subs:
        result.scanned += 1
        resync_snapshot(sub)
        due = sub.due_date

        if due is None:
            _set_state(sub, ReminderSubscription.State.STALE)
            result.staled += 1
            continue
        if today > due:
            _set_state(sub, ReminderSubscription.State.FIRED_OUT)
            result.fired_out += 1
            continue

        keys = _triggered_keys(sub, due, today)
        if not keys:
            continue

        days_remaining = (due - today).days
        notified = _deliver(sub, due, days_remaining, now)
        _seal(sub, today, days_remaining, keys, now, delivered=notified > 0)
        result.fired += 1
        result.notifications += notified

    return result


def _triggered_keys(sub, due, today) -> list[str]:
    """Idempotency keys of offsets whose fire date has arrived and are unsealed."""
    out: list[str] = []
    for offset in sub.offsets.all():
        if today >= offset_fire_date(due, offset.amount, offset.unit):
            key = idempotency_key(sub.id, due, offset.amount, offset.unit)
            if not ReminderFire.objects.filter(idempotency_key=key).exists():
                out.append(key)
    return out


def _deliver(sub, due, days_remaining, now) -> int:
    """R1 in-app delivery: one :class:`Notification` per recipient (idempotent)."""
    title, body = reminder_copy(sub, due, days_remaining)
    notified = 0
    for user in recipients(sub):
        dedupe = f"reminder:{sub.id}:{due:%Y-%m-%d}:{user.id}"
        _, created = Notification.objects.get_or_create(
            dedupe_key=dedupe,
            defaults={
                "user": user,
                "kind": Notification.Kind.REMINDER,
                "content": sub.content,
                "title": title,
                "body": body,
                "url": sub.url,
            },
        )
        notified += int(created)
    return notified


def _seal(sub, today, days_remaining, keys, now, *, delivered: bool) -> None:
    """Seal every triggering offset with a ``ReminderFire`` row (all in one fire)."""
    state = ReminderFire.Result.SENT if delivered else ReminderFire.Result.FAILED
    for key in keys:
        ReminderFire.objects.get_or_create(
            idempotency_key=key,
            defaults={
                "subscription": sub,
                "fired_on": today,
                "days_remaining": days_remaining,
                "channel": ReminderFire.Channel.IN_APP,
                "state": state,
                "sent_at": now if delivered else None,
            },
        )


def _set_state(sub, state) -> None:
    if sub.state != state:
        sub.state = state
        sub.save(update_fields=["state", "updated_at"])
