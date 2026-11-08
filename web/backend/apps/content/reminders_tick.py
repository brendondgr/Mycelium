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
from tools.retrieval.models import Notification, ReminderFire, ReminderSubscription

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
    snoozed: int = 0
    notifications: int = 0

    def as_dict(self) -> dict:
        return {
            "scanned": self.scanned,
            "fired": self.fired,
            "staled": self.staled,
            "fired_out": self.fired_out,
            "snoozed": self.snoozed,
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

        # Snoozed: skip without sealing anything, so the offsets stay open. When the
        # date passes they trigger together and the one-message-per-day collapse
        # sends a single reminder with the true days remaining — deferred, not lost.
        if sub.snoozed_until and local_today < sub.snoozed_until:
            result.snoozed += 1
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
    queued: bool = False
    outbox_key: str = ""


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
    """Deliver one fire: always in-app; personal reminders also DM (R3).

    The Discord half is now *queued*, so this makes no network call at all. That also
    closes a hole that predates the queue: the tick used to send, then write the seal,
    so a crash in between meant the next tick re-sent a message Discord had already
    accepted. Enqueue and seal are both local writes now, with nothing slow between
    them.
    """
    title, body = reminder_copy(sub, due, days_remaining)
    notified = _deliver_in_app(sub, title, body)

    channel = ReminderFire.Channel.IN_APP
    error_code = None
    # One key per (subscription, deadline date) — the same shape as the in-app
    # dedupe, so several offsets triggering on one day queue one message, not three.
    dedupe_key = f"reminder:{sub.id}:{due:%Y-%m-%d}"

    if sub.target_user_id:  # personal → queue a Discord DM on top of in-app
        from apps.content.reminders_discord import send_personal_dm

        outcome = send_personal_dm(sub, title, body, dedupe_key=dedupe_key)
        if outcome.ok:
            channel = ReminderFire.Channel.DISCORD_DM
    else:  # lab → post to the announcement channel with resolved member pings (R5)
        from apps.content.reminders_discord import send_lab_channel

        outcome = send_lab_channel(sub, title, body, dedupe_key=dedupe_key)
        _sync_unlinked_flag(sub, outcome.has_unlinked)
        if outcome.ok:
            channel = ReminderFire.Channel.DISCORD_CHANNEL
    if not outcome.ok and outcome.error_code is not None:
        error_code = outcome.error_code

    return _Delivery(
        notified,
        channel,
        error_code=error_code,
        queued=outcome.queued,
        outbox_key=outcome.outbox_key,
    )


def _sync_unlinked_flag(sub, has_unlinked) -> None:
    if has_unlinked is not None and sub.has_unlinked_targets != has_unlinked:
        sub.has_unlinked_targets = has_unlinked
        sub.save(update_fields=["has_unlinked_targets", "updated_at"])


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
    """Seal every triggering offset with a ``ReminderFire`` row (all in one fire).

    The seal is what stops a re-fire, and it is now written with nothing slow in
    front of it — the Discord message is already queued, so "we decided to send this"
    and "we recorded that we decided" cannot come apart.

    ``QUEUED`` is deliberate rather than an optimistic ``SENT``: the message is in the
    outbox, not in Discord. Whether it actually arrived is the outbox row's record,
    reachable by ``outbox_key``, and claiming otherwise here would be the same
    dishonesty that made a failed send look like a delivered one.
    """
    if delivery.queued:
        state = ReminderFire.Result.QUEUED
    elif delivery.notified > 0:
        state = ReminderFire.Result.SENT
    else:
        state = ReminderFire.Result.FAILED
    realised = state in (ReminderFire.Result.SENT, ReminderFire.Result.QUEUED)
    for key in keys:
        ReminderFire.objects.get_or_create(
            idempotency_key=key,
            defaults={
                "subscription": sub,
                "fired_on": today,
                "days_remaining": days_remaining,
                "channel": delivery.channel,
                "state": state,
                "outbox_key": delivery.outbox_key,
                "error_code": delivery.error_code,
                "sent_at": now if realised else None,
            },
        )


def _set_state(sub, state) -> None:
    if sub.state != state:
        sub.state = state
        sub.save(update_fields=["state", "updated_at"])
