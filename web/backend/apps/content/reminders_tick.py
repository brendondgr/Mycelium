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
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.utils import timezone

from apps.content.models import Notification, ReminderFire, ReminderSubscription
from apps.content.reminders import (
    idempotency_key,
    offset_fire_date,
    recipients,
    reminder_copy,
    resync_snapshot,
)

# Personal reminders have no per-user zone yet; default to Eastern like labs do.
DEFAULT_TIMEZONE = "America/New_York"


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
    """Fire due reminders once each.

    ``today`` forces a single reference date for every subscription (tests); when it
    is ``None`` each subscription's local "today" is computed from ``now`` in the
    recipient's zone (the lab's zone for lab reminders, Eastern for personal), so
    days-remaining and fire eligibility are correct across a DST boundary.
    """
    now = now or timezone.now()
    result = TickResult()

    subs = (
        ReminderSubscription.objects.filter(state=ReminderSubscription.State.ACTIVE)
        .select_related("target_lab")
        .prefetch_related("offsets")
    )

    for sub in subs:
        result.scanned += 1
        resync_snapshot(sub)
        local_today = today or _local_today(sub, now)
        due = sub.due_date

        if due is None:
            _set_state(sub, ReminderSubscription.State.STALE)
            result.staled += 1
            continue
        if local_today > due:
            _set_state(sub, ReminderSubscription.State.FIRED_OUT)
            result.fired_out += 1
            continue

        keys = _triggered_keys(sub, due, local_today)
        if not keys:
            continue

        days_remaining = (due - local_today).days
        delivery = _deliver(sub, due, days_remaining)
        _seal(sub, local_today, days_remaining, keys, now, delivery)
        result.fired += 1
        result.notifications += delivery.notified

    return result


def _local_today(sub, now):
    """The subscription's local date: the lab's zone, or Eastern for personal."""
    tzname = sub.target_lab.timezone if sub.target_lab_id else DEFAULT_TIMEZONE
    try:
        tz = ZoneInfo(tzname or DEFAULT_TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError):
        tz = ZoneInfo(DEFAULT_TIMEZONE)
    return now.astimezone(tz).date()


@dataclass
class _Delivery:
    """What one fire produced across in-app + Discord."""

    notified: int
    channel: str
    message_id: str = ""
    error_code: int | None = None


def _triggered_keys(sub, due, today) -> list[str]:
    """Idempotency keys of offsets whose fire date has arrived and are unsealed."""
    out: list[str] = []
    for offset in sub.offsets.all():
        if today >= offset_fire_date(due, offset.amount, offset.unit):
            key = idempotency_key(sub.id, due, offset.amount, offset.unit)
            if not ReminderFire.objects.filter(idempotency_key=key).exists():
                out.append(key)
    return out


def _deliver(sub, due, days_remaining) -> _Delivery:
    """Deliver one fire: always in-app; personal reminders also DM (R3)."""
    title, body = reminder_copy(sub, due, days_remaining)
    notified = _deliver_in_app(sub, title, body)

    channel = ReminderFire.Channel.IN_APP
    message_id = ""
    error_code = None
    if sub.target_user_id:  # personal → attempt a Discord DM on top of in-app
        from apps.content.reminders_discord import send_personal_dm

        outcome = send_personal_dm(sub, title, body)
        if outcome.ok:
            channel = ReminderFire.Channel.DISCORD_DM
            message_id = outcome.message_id
        elif outcome.error_code is not None:
            error_code = outcome.error_code
    return _Delivery(notified, channel, message_id, error_code)


def _deliver_in_app(sub, title, body) -> int:
    """One :class:`Notification` per recipient (idempotent by dedupe key)."""
    notified = 0
    for user in recipients(sub):
        dedupe = f"reminder:{sub.id}:{sub.due_date:%Y-%m-%d}:{user.id}"
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


def _seal(sub, today, days_remaining, keys, now, delivery) -> None:
    """Seal every triggering offset with a ``ReminderFire`` row (all in one fire)."""
    sent = delivery.notified > 0 or bool(delivery.message_id)
    state = ReminderFire.Result.SENT if sent else ReminderFire.Result.FAILED
    for key in keys:
        ReminderFire.objects.get_or_create(
            idempotency_key=key,
            defaults={
                "subscription": sub,
                "fired_on": today,
                "days_remaining": days_remaining,
                "channel": delivery.channel,
                "state": state,
                "discord_message_id": delivery.message_id,
                "error_code": delivery.error_code,
                "sent_at": now if sent else None,
            },
        )


def _set_state(sub, state) -> None:
    if sub.state != state:
        sub.state = state
        sub.save(update_fields=["state", "updated_at"])
