"""Seat lifecycle — keep billing seats in step with lab / department membership.

Entitlement resolution reads *active seats*, so a membership without a seat silently
resolves to Free. A ``LabMembership`` on an **active** Lab subscription is entitlement
(architecture A6): membership implies an ACTIVE, lab-paid seat. Under decision **L2** a
department join on an **active** Canopy subscription now also seats ACTIVE (department-
paid): the whole effective membership is auto-entitled once the department is active,
so there is no longer a per-person PENDING gate. While an org plan is still INACTIVE it
has no active subscription, so nothing is seated until activation.

Removal is **deferred, never destructive** (decision L3 / B3): a removed member keeps
their ACTIVE seat — with an ``ends_at`` cutoff — through the end of the current billing
period, and the daily ``run_billing_tick`` flips it to REVOKED then, with no credit. A
removal on a plan with no open period revokes immediately. Every add / activation /
removal writes a :class:`~apps.billing.models.SeatEvent` ledger row.
"""

from __future__ import annotations

from datetime import date

from django.contrib.auth.models import User

from .entitlements import active_seat_count, member_cap, within_member_cap
from .models import Seat, SeatEvent, Subscription
from .period import today
from .pricing import prorate_add


class SeatCeilingExceeded(Exception):
    """Raised when seating a member would exceed the tier's member ceiling."""


def _active_subscription_for_lab(lab) -> Subscription | None:
    return (
        Subscription.objects.filter(scope_lab=lab, status=Subscription.Status.ACTIVE)
        .order_by("-created_at")
        .first()
    )


def _active_subscription_for_department(department) -> Subscription | None:
    return (
        Subscription.objects.filter(
            scope_department=department, status=Subscription.Status.ACTIVE
        )
        .order_by("-created_at")
        .first()
    )


def _log_seat_event(seat: Seat, kind: str, *, now: date | None = None) -> None:
    """Append a ledger row for a seat becoming active. Adds are prorated (L3);
    activations are the full-period cohort (their cost is the activation quote)."""
    ref = now or today()
    sub = seat.subscription
    prorated = 0
    if (
        kind == SeatEvent.Kind.ADDED
        and sub.status == Subscription.Status.ACTIVE
        and sub.current_period_start
        and sub.current_period_end
    ):
        prorated = prorate_add(
            sub.tier,
            added_on=ref,
            period_start=sub.current_period_start,
            period_end=sub.current_period_end,
        )
    SeatEvent.objects.create(
        seat=seat, kind=kind, effective_date=ref, prorated_cents=prorated
    )


def _ensure_seat(
    subscription: Subscription,
    user: User,
    *,
    status: str,
    payer_type: str,
    payer_obj,
    event_kind: str | None = None,
    now: date | None = None,
) -> Seat:
    """Idempotently ensure ``user`` holds a seat with ``status`` on the subscription.

    A pre-existing seat has its *status* moved (its payer is never clobbered — a self-
    paying founder stays self-paid) and, when (re)activated, any pending-removal
    ``ends_at`` is cleared. The ceiling is checked only when this adds a *new* active
    seat; a newly-active seat writes a ledger row.
    """
    existing = Seat.objects.filter(subscription=subscription, member=user).first()
    becomes_active = status == Seat.Status.ACTIVE
    was_active = existing is not None and existing.status == Seat.Status.ACTIVE
    if becomes_active and not was_active:
        projected = active_seat_count(subscription) + 1
        if not within_member_cap(projected, subscription.tier):
            raise SeatCeilingExceeded(
                f"{subscription.get_tier_display()} allows at most "
                f"{member_cap(subscription.tier)} seats."
            )
    if existing is not None:
        fields: list[str] = []
        if existing.status != status:
            existing.status = status
            fields.append("status")
        if becomes_active and existing.ends_at is not None:
            existing.ends_at = None  # re-adding un-schedules a pending removal
            fields.append("ends_at")
        if fields:
            fields.append("updated_at")
            existing.save(update_fields=fields)
        if becomes_active and not was_active:
            _log_seat_event(existing, event_kind or SeatEvent.Kind.ADDED, now=now)
        return existing
    payer_fields = {
        "lab": {"payer_lab": payer_obj},
        "department": {"payer_department": payer_obj},
        "self": {"payer_user": user},
    }[payer_type]
    seat = Seat.objects.create(
        subscription=subscription, member=user, status=status, **payer_fields
    )
    if becomes_active:
        _log_seat_event(seat, event_kind or SeatEvent.Kind.ADDED, now=now)
    return seat


def grant_seat_for_lab_member(
    user: User, lab, *, now: date | None = None
) -> Seat | None:
    """Ensure ``user`` holds an ACTIVE, lab-paid seat on ``lab``'s subscription.

    Returns the seat, or ``None`` when the lab has no active subscription (an inactive
    or Free lab has nothing to seat). Idempotent; re-activates a REVOKED seat and clears
    a pending-removal cutoff. Raises :class:`SeatCeilingExceeded` past the tier ceiling.
    """
    subscription = _active_subscription_for_lab(lab)
    if subscription is None:
        return None
    return _ensure_seat(
        subscription, user, status=Seat.Status.ACTIVE, payer_type="lab",
        payer_obj=lab, now=now,
    )


def grant_seat_for_dept_member(
    user: User, department, *, now: date | None = None
) -> Seat | None:
    """Ensure ``user`` holds an ACTIVE, department-paid seat (L2).

    A department seats its effective members ACTIVE once its plan is active (no PENDING
    gate). Returns ``None`` when the department has no active subscription.
    """
    subscription = _active_subscription_for_department(department)
    if subscription is None:
        return None
    return _ensure_seat(
        subscription, user, status=Seat.Status.ACTIVE, payer_type="department",
        payer_obj=department, now=now,
    )


def schedule_seat_removal(
    subscription: Subscription | None, user: User, *, now: date | None = None
) -> Seat | None:
    """Defer removal of ``user``'s seat to the end of the current period (L3).

    The seat stays ACTIVE (entitled + billed) with ``ends_at`` at the period end; the
    daily tick revokes it then, with no credit. On a plan with no open period there is
    nothing billed, so the seat is revoked immediately. Never hard-deletes.
    """
    if subscription is None:
        return None
    seat = Seat.objects.filter(subscription=subscription, member=user).first()
    if seat is None or seat.status == Seat.Status.REVOKED:
        return seat
    ref = now or today()
    end = subscription.current_period_end
    if subscription.status == Subscription.Status.ACTIVE and end and end > ref:
        seat.ends_at = end
        seat.save(update_fields=["ends_at", "updated_at"])
        SeatEvent.objects.create(
            seat=seat, kind=SeatEvent.Kind.REMOVED, effective_date=end, prorated_cents=0
        )
    else:
        seat.status = Seat.Status.REVOKED
        seat.save(update_fields=["status", "updated_at"])
        SeatEvent.objects.create(
            seat=seat, kind=SeatEvent.Kind.REMOVED, effective_date=ref, prorated_cents=0
        )
    return seat


def revoke_seat_for_lab_member(
    user: User, lab, *, now: date | None = None
) -> Seat | None:
    """Schedule removal of ``user``'s seat on ``lab``'s subscription (deferred, L3)."""
    return schedule_seat_removal(_active_subscription_for_lab(lab), user, now=now)


def revoke_seat_for_dept_member(
    user: User, department, *, now: date | None = None
) -> Seat | None:
    """Defer removal of ``user``'s seat on ``department``'s subscription (L3)."""
    return schedule_seat_removal(
        _active_subscription_for_department(department), user, now=now
    )
