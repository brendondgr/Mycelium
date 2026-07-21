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

    When the lapsing seat was **department-paid** (an excluded or detached lab, a
    department removal), the member falls back to their lab's own active plan instead
    of dropping to Free — so a lab that still carries its own plan keeps covering its
    people once the department stops. The fallback runs after the revoke so
    :func:`~apps.billing.seat_sync.paying_scope_for_lab` sees the final state.
    """
    from .seat_sync import fallback_lab_seats  # local: avoids a period↔seat_sync cycle

    ref = now or today()
    lapsed = list(
        Seat.objects.filter(
            status=Seat.Status.ACTIVE,
            ends_at__isnull=False,
            ends_at__lte=ref,
        ).select_related("member")
    )
    # Phase 1 — revoke every lapsed seat. Do this fully before any fallback so a
    # member's stale lab seat (deferred when they were moved to the department plan)
    # is revoked here rather than re-revoked after the fallback re-grants it.
    fallback_members = []
    for seat in lapsed:
        seat.status = Seat.Status.REVOKED
        seat.save(update_fields=["status", "updated_at"])
        SeatEvent.objects.create(
            seat=seat,
            kind=SeatEvent.Kind.EXPIRED,
            effective_date=ref,
            prorated_cents=0,
        )
        if seat.payer_department_id is not None:
            fallback_members.append(seat.member)
    # Phase 2 — a member whose department-paid seat lapsed falls back to their lab's
    # own active plan (if any), so a still-running lab plan keeps covering its people.
    for member in fallback_members:
        fallback_lab_seats(member)
    return len(lapsed)
