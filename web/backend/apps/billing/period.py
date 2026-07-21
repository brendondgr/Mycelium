"""Billing-period lifecycle for lab & department subscriptions.

An org plan is created INACTIVE with no period. Activation opens the first monthly
window; a daily tick (``run_billing_tick``) rolls the window forward and revokes seats
whose deferred-removal cutoff has passed. Pure, date-granular, idempotent — no charging
happens here (payment processing is out of scope).
"""

from __future__ import annotations

import calendar
from datetime import date

from django.db import transaction
from django.utils import timezone

from .models import Seat, SeatEvent, Subscription


def add_one_month(d: date) -> date:
    """The same day one month later, clamped to the last valid day of that month."""
    year = d.year + (d.month // 12)
    month = d.month % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def today() -> date:
    """The current local date — the single clock the billing lifecycle reads."""
    return timezone.localdate()


@transaction.atomic
def activate(subscription: Subscription, *, on: date | None = None) -> Subscription:
    """Activate an inactive/draft plan: open its first monthly period.

    Re-activating an already-active plan that has a period leaves the window untouched
    (a double activate never shifts billing). ``activated_at`` is stamped only the first
    time. Seeding the covered seats is the activation *service*'s job (see
    ``billing.services``); this only opens the window.
    """
    start = on or today()
    if (
        subscription.status == Subscription.Status.ACTIVE
        and subscription.current_period_end is not None
    ):
        return subscription
    subscription.status = Subscription.Status.ACTIVE
    if subscription.activated_at is None:
        subscription.activated_at = timezone.now()
    subscription.current_period_start = start
    subscription.current_period_end = add_one_month(start)
    subscription.save(
        update_fields=[
            "status",
            "activated_at",
            "current_period_start",
            "current_period_end",
            "updated_at",
        ]
    )
    return subscription


def roll_periods(*, now: date | None = None) -> int:
    """Advance any ACTIVE plan whose current period has ended. Returns the rolled count.

    Handles a multi-month gap (e.g. a tick that did not run for a while) by advancing
    until the window contains ``now``.
    """
    ref = now or today()
    rolled = 0
    subs = Subscription.objects.filter(
        status=Subscription.Status.ACTIVE,
        current_period_end__isnull=False,
        current_period_end__lte=ref,
    )
    for sub in subs:
        start = sub.current_period_start or sub.current_period_end
        end = sub.current_period_end
        while end <= ref:
            start = end
            end = add_one_month(end)
        sub.current_period_start = start
        sub.current_period_end = end
        sub.save(
            update_fields=["current_period_start", "current_period_end", "updated_at"]
        )
        rolled += 1
    return rolled


def end_lapsed_seats(*, now: date | None = None) -> int:
    """Revoke ACTIVE seats whose deferred-removal cutoff has passed. Returns the count.

    This is where a mid-cycle removal actually takes effect: the seat stayed ACTIVE
    (entitled + billed) through ``ends_at``; now it flips to REVOKED with an ``expired``
    ledger row and no credit (decision L3).
    """
    ref = now or today()
    count = 0
    lapsed = Seat.objects.filter(
        status=Seat.Status.ACTIVE,
        ends_at__isnull=False,
        ends_at__lte=ref,
    )
    for seat in lapsed:
        seat.status = Seat.Status.REVOKED
        seat.save(update_fields=["status", "updated_at"])
        SeatEvent.objects.create(
            seat=seat,
            kind=SeatEvent.Kind.EXPIRED,
            effective_date=ref,
            prorated_cents=0,
        )
        count += 1
    return count
