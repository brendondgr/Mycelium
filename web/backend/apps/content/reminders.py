"""Reminder services: create/seal a subscription, snapshot resync, copy, recipients.

The scheduling model is **compute-on-read** (see :mod:`apps.content.reminders_tick`):
nothing here materializes a fire schedule. Offsets are stored; the fire date is
derived from the *current* ``due_date`` with calendar math every tick. Two behaviors
fall out of embedding ``due_date`` in the idempotency key:

* **Seal-on-create** — offsets already in the past when the subscription is created
  are sealed as ``skipped(backdated_on_create)``, so subscribing late sends nothing.
* **Move re-opens** — when the deadline moves the key changes, the old seal no longer
  matches, and the offset fires again on the next tick with the *current* days-left.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import LabMembership
from apps.accounts.permissions import (
    user_can_edit_lab_profile,
    user_has_lab_access,
)
from apps.content.models import (
    ContentDeadline,
    ContentItem,
    ReminderFire,
    ReminderMention,
    ReminderOffset,
    ReminderSubscription,
    SavedOpportunity,
)
from apps.content.reminder_access import (
    lab_reminder_access,
    personal_reminder_access,
)

# Free-form bound (D-13): a subscription may carry at most this many offsets.
MAX_OFFSETS_PER_SUBSCRIPTION = 5

_KIND_LABEL = {
    SavedOpportunity.DeadlineKind.APPLICATION: "Application",
    SavedOpportunity.DeadlineKind.ABSTRACT: "Abstract",
    SavedOpportunity.DeadlineKind.MANUSCRIPT: "Manuscript",
    SavedOpportunity.DeadlineKind.EVENT: "Event",
    SavedOpportunity.DeadlineKind.OTHER: "Deadline",
}


class ReminderError(ValueError):
    """A subscription could not be created (dateless deadline, too many offsets…)."""


class ReminderAccessError(ReminderError):
    """The actor is not entitled to reminders (no paid plan, or Discord unlinked).

    A distinct subclass so the API can answer **403** rather than 400: this is not a
    malformed request, it is a capability the account does not currently have.
    ``reason`` carries the machine-readable slug from
    :mod:`apps.content.reminder_access` so the client can point at the right fix.
    """

    def __init__(self, access) -> None:
        super().__init__(access.detail)
        self.reason = access.reason
        self.access = access


def offset_fire_date(due: date, amount: int, unit: str) -> date:
    """The date an ``(amount, unit)`` offset fires: ``due`` minus that many units.

    Calendar-correct: ``relativedelta`` clamps impossible dates (31 Mar − 1 month →
    28/29 Feb) and treats "2 months" as the same day-of-month, never 60 days.
    """
    return due - relativedelta(**{f"{unit}s": amount})


def idempotency_key(subscription_id, due: date, amount: int, unit: str) -> str:
    """The fired-ledger key. Embedding ``due`` is the whole trick — a moved
    deadline changes the key and re-opens the offset; a stable one keeps the seal."""
    return f"{subscription_id}:{due:%Y-%m-%d}:{amount}{unit}"


def reminder_copy(subscription: ReminderSubscription, due: date, days_remaining: int):
    """(title, body) for a fire. The body always states **actual** days remaining —
    never the offset that triggered it ("14 days left", not "your 2-month reminder")."""
    kind_label = _KIND_LABEL.get(subscription.deadline_kind, "Deadline")
    when = f"{due:%b %d}"
    if days_remaining <= 0:
        left = "due today"
    elif days_remaining == 1:
        left = "1 day left"
    else:
        left = f"{days_remaining} days left"
    return subscription.title, f"{kind_label} due {when} — {left}"


def recipients(subscription: ReminderSubscription) -> list:
    """The users an in-app fire notifies: the person, or every lab member."""
    if subscription.target_user_id:
        return [subscription.target_user]
    memberships = LabMembership.objects.filter(
        lab_id=subscription.target_lab_id
    ).select_related("user")
    return [m.user for m in memberships]


def resync_snapshot(subscription: ReminderSubscription) -> None:
    """Refresh the snapshot ``due_date``/``confidence`` from the live projection.

    While the item is alive the ``ContentDeadline`` row is the source of truth; once
    the item is pruned (``content`` is NULL) the snapshot is all there is and is left
    untouched. If the item is alive but the kind's row vanished, the deadline is gone
    → null the snapshot so the tick marks the subscription stale.
    """
    if not subscription.content_id:
        return
    row = ContentDeadline.objects.filter(
        content_id=subscription.content_id, kind=subscription.deadline_kind
    ).first()
    fields: list[str] = []
    if row is None:
        if subscription.due_date is not None:
            subscription.due_date = None
            fields.append("due_date")
    else:
        if subscription.due_date != row.due_date:
            subscription.due_date = row.due_date
            fields.append("due_date")
        if subscription.confidence != row.confidence:
            subscription.confidence = row.confidence
            fields.append("confidence")
    if fields:
        subscription.save(update_fields=[*fields, "updated_at"])


def seal_backdated_offsets(subscription: ReminderSubscription, today: date) -> int:
    """Seal offsets whose fire date is already in the past at create time.

    Returns the number sealed. Only *strictly* past offsets are sealed — one whose
    fire date is exactly today stays open and fires on today's (or the next) tick.
    """
    due = subscription.due_date
    if due is None:
        return 0
    sealed = 0
    for offset in subscription.offsets.all():
        if offset_fire_date(due, offset.amount, offset.unit) < today:
            key = idempotency_key(subscription.id, due, offset.amount, offset.unit)
            _, created = ReminderFire.objects.get_or_create(
                idempotency_key=key,
                defaults={
                    "subscription": subscription,
                    "fired_on": today,
                    "channel": ReminderFire.Channel.IN_APP,
                    "state": ReminderFire.Result.SKIPPED,
                    "skip_reason": "backdated_on_create",
                },
            )
            sealed += int(created)
    return sealed


@transaction.atomic
def create_subscription(
    *,
    deadline_kind: str,
    area: str,
    title: str,
    due_date: date | None,
    offsets: list[tuple[int, str]],
    target_user=None,
    target_lab=None,
    content: ContentItem | None = None,
    url: str = "",
    confidence: str = ContentDeadline.Confidence.CONFIRMED,
    mentions=(),
    channel_id_override: str = "",
    created_by=None,
    today: date | None = None,
) -> ReminderSubscription:
    """Create a subscription + its offsets/mentions and seal backdated offsets.

    Rejects a dateless deadline (rolling / unknown) — the affordance is disabled for
    those in the UI, and the service is the backstop. Enforces exactly-one target and
    the per-subscription offset cap (D-13).

    Entitlement (a paid plan + synced Discord, see :mod:`apps.content.reminder_access`)
    is checked here for the same reason the lab-manager rule is, and under the same
    condition: only when ``created_by`` is set. A ``created_by`` of ``None`` marks a
    system-initiated create — a backfill, a copy, a test fixture — which has no human
    whose plan could be read, and which is not the surface being gated.
    """
    if (target_user is None) == (target_lab is None):
        raise ReminderError("exactly one of target_user / target_lab is required")
    if due_date is None:
        raise ReminderError("cannot set a reminder on a deadline with no date")
    if target_lab is not None:
        # Only a lab PI (lead) or owner/admin may create a lab reminder; every
        # mention target must be a lab member (else they could ping arbitrary
        # Mycelium users via Mylo).
        if created_by is not None and not user_can_edit_lab_profile(
            created_by, target_lab
        ):
            raise ReminderError("only a lab PI or admin can create a lab reminder")
        for member in mentions:
            if not user_has_lab_access(member, target_lab):
                raise ReminderError("mention target must be a lab member")
    if created_by is not None:
        access = (
            lab_reminder_access(target_lab)
            if target_lab is not None
            else personal_reminder_access(target_user)
        )
        if not access.allowed:
            raise ReminderAccessError(access)
    unique_offsets = list(dict.fromkeys(offsets))  # dedupe, preserve order
    if not unique_offsets:
        raise ReminderError("at least one offset is required")
    if len(unique_offsets) > MAX_OFFSETS_PER_SUBSCRIPTION:
        raise ReminderError(
            f"at most {MAX_OFFSETS_PER_SUBSCRIPTION} offsets per reminder"
        )

    subscription = ReminderSubscription.objects.create(
        target_user=target_user,
        target_lab=target_lab,
        content=content,
        deadline_kind=deadline_kind,
        area=area,
        title=title,
        url=url,
        due_date=due_date,
        confidence=confidence,
        channel_id_override=channel_id_override,
        created_by=created_by,
    )
    ReminderOffset.objects.bulk_create(
        ReminderOffset(subscription=subscription, amount=amount, unit=unit)
        for amount, unit in unique_offsets
    )
    for member in mentions:
        ReminderMention.objects.get_or_create(subscription=subscription, member=member)

    seal_backdated_offsets(subscription, today or timezone.now().date())
    return subscription


@dataclass
class DeliveryResult:
    """What one in-app fire produced."""

    delivered: bool
    notified: int = 0


def reference_today() -> date:
    """The wall-clock date the prune → stale hook reads.

    A named seam, not a convenience: :func:`stale_reminders_for_deleted_content` runs
    from a ``pre_delete`` signal, which cannot take an extra argument, so a test has
    no way to pass a reference date in. Monkeypatching this function is how a test
    pins the clock — see ``test_reminders_prune_ordering.py``.
    """
    return timezone.localdate()


def stale_reminders_for_deleted_content(content, *, today: date | None = None) -> int:
    """Resync every live reminder on a vanishing item; stale the ones now past.

    Called from the ``pre_delete`` backstop in :mod:`apps.content.signals` (R2). The
    danger it guards: a deadline moves *earlier* into the past, the item is pruned,
    and the reminder is left holding a snapshot with the old, later date that it would
    cheerfully fire on. A reminder whose deadline is genuinely still upcoming survives
    on its snapshot and keeps firing — the item merely disappeared from the source.

    Returns how many subscriptions were marked stale.
    """
    today = today or reference_today()
    staled = 0
    subs = ReminderSubscription.objects.filter(
        content=content, state=ReminderSubscription.State.ACTIVE
    )
    for sub in subs:
        resync_snapshot(sub)
        if sub.due_date is None or sub.due_date < today:
            sub.state = ReminderSubscription.State.STALE
            sub.save(update_fields=["state", "updated_at"])
            staled += 1
    return staled
