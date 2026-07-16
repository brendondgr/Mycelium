"""Seat lifecycle — keep billing seats in step with lab / department membership.

Entitlement resolution reads *active seats*, so a membership without a seat
silently resolves to Free — the live bug this module closes. A ``LabMembership``
on an active Lab subscription **is** entitlement (architecture A6): membership
implies a seat, granted ACTIVE and lab-paid. A department join is an explicit
admin act (mixed payers, no ceiling), so it seats as PENDING for an admin to
activate. Seats are **never hard-deleted** — removal flips status to REVOKED so
the audit trail survives.
"""

from __future__ import annotations

from django.contrib.auth.models import User

from .entitlements import active_seat_count, member_cap, within_member_cap
from .models import Seat, Subscription


class SeatCeilingExceeded(Exception):
    """Raised when seating a member would exceed the tier's member ceiling."""


def _active_subscription_for_lab(lab) -> Subscription | None:
    return (
        Subscription.objects.filter(
            scope_lab=lab, status=Subscription.Status.ACTIVE
        )
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


def _ensure_seat(
    subscription: Subscription,
    user: User,
    *,
    status: str,
    payer_type: str,
    payer_obj,
) -> Seat:
    """Idempotently ensure ``user`` holds a seat with ``status`` on the subscription.

    A pre-existing seat only has its *status* moved (its payer is never clobbered —
    a self-paying founder stays self-paid). A new seat records the given payer. The
    ceiling is checked only when this would add a *new* active seat.
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
        if existing.status != status:
            existing.status = status
            existing.save(update_fields=["status", "updated_at"])
        return existing
    payer_fields = {
        "lab": {"payer_lab": payer_obj},
        "department": {"payer_department": payer_obj},
        "self": {"payer_user": user},
    }[payer_type]
    return Seat.objects.create(
        subscription=subscription, member=user, status=status, **payer_fields
    )


def grant_seat_for_lab_member(user: User, lab) -> Seat | None:
    """Ensure ``user`` holds an ACTIVE, lab-paid seat on ``lab``'s subscription.

    Returns the seat, or ``None`` when the lab has no active subscription (a Free
    lab has nothing to seat). Idempotent; re-activates a previously REVOKED seat.
    Raises :class:`SeatCeilingExceeded` past the tier's member ceiling.
    """
    subscription = _active_subscription_for_lab(lab)
    if subscription is None:
        return None
    return _ensure_seat(
        subscription, user, status=Seat.Status.ACTIVE, payer_type="lab", payer_obj=lab
    )


def grant_seat_for_dept_member(user: User, department) -> Seat | None:
    """Ensure ``user`` holds a PENDING, department-paid seat (A6).

    Canopy has mixed payers and no member ceiling, so a department join creates a
    PENDING seat an admin later activates. Returns ``None`` with no active
    subscription.
    """
    subscription = _active_subscription_for_department(department)
    if subscription is None:
        return None
    return _ensure_seat(
        subscription,
        user,
        status=Seat.Status.PENDING,
        payer_type="department",
        payer_obj=department,
    )


def _revoke_seat(subscription: Subscription | None, user: User) -> Seat | None:
    if subscription is None:
        return None
    seat = Seat.objects.filter(subscription=subscription, member=user).first()
    if seat is None or seat.status == Seat.Status.REVOKED:
        return seat
    seat.status = Seat.Status.REVOKED
    seat.save(update_fields=["status", "updated_at"])
    return seat


def revoke_seat_for_lab_member(user: User, lab) -> Seat | None:
    """Flip ``user``'s seat on ``lab``'s subscription to REVOKED (never delete)."""
    return _revoke_seat(_active_subscription_for_lab(lab), user)


def revoke_seat_for_dept_member(user: User, department) -> Seat | None:
    """Flip ``user``'s seat on ``department``'s subscription to REVOKED."""
    return _revoke_seat(_active_subscription_for_department(department), user)
