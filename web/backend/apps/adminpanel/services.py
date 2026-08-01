"""Admin write operations — assign a plan and set the quotas that hang off it.

Kept out of the views so the mutations (and their audit trail) live in one place.
Every write records an :class:`~apps.accounts.models.AuditEvent` naming the acting
admin, since these change someone else's entitlements.

Two targets, deliberately separate:

* **A user** — their *personal* (``scope_user``) subscription plus the watch-topic
  override. Seat-based org plans are never touched from here.
* **A lab** — its ``scope_lab`` subscription: tier, status, how (and whether) the plan
  ends, whether it is complimentary, and whether Mylo is part of it. Activation funnels
  through :func:`apps.billing.services.activate_lab_subscription` so the billing period
  and member seats are opened by the same code a PI's own activation uses.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from apps.accounts.services import record_audit_event
from apps.billing.addons import mylo_included, set_mylo_included
from apps.billing.models import Seat, Subscription, Tier
from apps.billing.seats import SeatCeilingExceeded
from apps.billing.services import activate_lab_subscription, lab_subscription
from apps.billing.tiers import TierScopeError, validate_tier_for_scope


def personal_subscription(user: User) -> Subscription | None:
    """The user's own (``scope_user``) subscription — the one the admin manages."""
    return (
        Subscription.objects.filter(scope_user=user)
        .order_by("-created_at")
        .first()
    )


def _ensure_personal_subscription(user: User, *, tier: str) -> Subscription:
    """Return the user's personal subscription, creating it (+ a self-paid seat)
    at ``tier`` if they somehow have none."""
    sub = personal_subscription(user)
    if sub is not None:
        return sub
    sub = Subscription.objects.create(tier=tier, scope_user=user)
    Seat.objects.get_or_create(
        subscription=sub,
        member=user,
        defaults={"payer_user": user, "status": Seat.Status.ACTIVE},
    )
    return sub


def assign_subscription(
    *,
    admin: User,
    user: User,
    tier: str | None = None,
    duration_days: int | None = None,
    expires_at=None,
    status: str | None = None,
    has_duration: bool = False,
    has_expires_at: bool = False,
) -> Subscription:
    """Set the tier / duration / status of a user's personal subscription.

    Duration is expressed either as ``duration_days`` (``expires_at`` = now + N
    days) or an explicit ``expires_at`` instant; ``None`` for either clears the
    expiry (open-ended). The ``has_*`` flags distinguish "field omitted" (leave
    expiry alone) from "field sent as null" (clear expiry). Expiry is enforced at
    read-time (see :mod:`apps.billing.entitlements`), so a lapsed grant reverts to
    Free on its own.
    """
    # A personal plan is only ever a personal tier; Mycelium Lab is bought on a lab,
    # where a roster exists to price it against (``apps.billing.tiers``).
    if tier is not None:
        validate_tier_for_scope("user", tier)
    sub = _ensure_personal_subscription(user, tier=tier or Tier.FREE)

    changed: list[str] = []
    if tier is not None:
        sub.tier = tier
        changed.append("tier")
    if status is not None:
        sub.status = status
        changed.append("status")
    if has_expires_at:
        sub.expires_at = expires_at
        changed.append("expires_at")
    elif has_duration:
        sub.expires_at = (
            None if duration_days is None
            else timezone.now() + timedelta(days=duration_days)
        )
        changed.append("expires_at")

    if changed:
        sub.save(update_fields=[*changed, "updated_at"])

    record_audit_event(
        actor=admin,
        action="admin.subscription.assign",
        target_type="user",
        target_id=str(user.pk),
        metadata={
            "tier": sub.tier,
            "status": sub.status,
            "expires_at": sub.expires_at.isoformat() if sub.expires_at else None,
        },
    )
    return sub


def set_watch_limit(*, admin: User, user: User, limit: int | None) -> None:
    """Set (or clear, with ``None``) the per-user watch-topic override."""
    profile = user.profile
    profile.watch_topic_limit = limit
    # Scope the write so the pre_save embed hook can't rewrite unrelated columns
    # (interests/embedding are untouched here).
    profile.save(update_fields=["watch_topic_limit", "updated_at"])
    record_audit_event(
        actor=admin,
        action="admin.watch_limit.set",
        target_type="user",
        target_id=str(user.pk),
        metadata={"watch_topic_limit": limit},
    )


@transaction.atomic
def apply_user_update(*, admin: User, user: User, data: dict) -> None:
    """Apply a validated admin PATCH: subscription fields and/or the watch limit.

    ``data`` is the serializer's ``validated_data`` — only keys the client sent are
    present, which is how "omitted" is told apart from "explicitly null".
    """
    subscription_keys = {"tier", "duration_days", "expires_at", "subscription_status"}
    if subscription_keys & data.keys():
        assign_subscription(
            admin=admin,
            user=user,
            tier=data.get("tier"),
            duration_days=data.get("duration_days"),
            expires_at=data.get("expires_at"),
            status=data.get("subscription_status"),
            has_duration="duration_days" in data,
            has_expires_at="expires_at" in data,
        )
    if "watch_topic_limit" in data:
        set_watch_limit(admin=admin, user=user, limit=data["watch_topic_limit"])


# --------------------------------------------------------------------------- #
# Labs
# --------------------------------------------------------------------------- #


def ensure_lab_subscription(lab) -> Subscription:
    """The lab's plan, creating an INACTIVE Lab-tier one if it somehow has none.

    Every lab minted through :mod:`apps.billing.services` already has one; this covers
    rows that predate that path so the admin surface never dead-ends on a missing plan.
    """
    sub = lab_subscription(lab)
    if sub is not None:
        return sub
    return Subscription.objects.create(
        tier=Tier.LAB, scope_lab=lab, status=Subscription.Status.INACTIVE
    )


@transaction.atomic
def apply_lab_update(*, admin: User, lab, data: dict) -> Subscription:
    """Apply a validated admin PATCH over one lab's plan.

    Order matters. The tier is written first so an activation in the same request seats
    members at the tier the admin just chose. Activation then runs through the shared
    :func:`~apps.billing.services.activate_lab_subscription`, which opens the billing
    period and seats every current member — the same path a PI's own "Activate plan"
    button takes, so an admin-granted plan is indistinguishable from a self-activated
    one downstream.

    ``data`` is the serializer's ``validated_data``: only keys the client sent are
    present, which is how "leave alone" is told from "set to null".
    """
    sub = ensure_lab_subscription(lab)

    if "tier" in data:
        validate_tier_for_scope("lab", data["tier"])
        sub.tier = data["tier"]
        sub.save(update_fields=["tier", "updated_at"])

    # Expiry: `expires_at` (an instant) and `duration_days` (now + N) are two ways to
    # say the same thing; either sent as null means "never ends".
    expiry_fields: list[str] = []
    if "expires_at" in data:
        sub.expires_at = data["expires_at"]
        expiry_fields.append("expires_at")
    elif "duration_days" in data:
        days = data["duration_days"]
        sub.expires_at = None if days is None else timezone.now() + timedelta(days=days)
        expiry_fields.append("expires_at")
    if "is_comped" in data:
        sub.is_comped = data["is_comped"]
        expiry_fields.append("is_comped")
    if expiry_fields:
        sub.save(update_fields=[*expiry_fields, "updated_at"])

    status = data.get("status")
    # Only a real transition into ACTIVE (or an ACTIVE plan that never opened a period)
    # runs the activation service. Re-running it on an already-live plan would re-seat
    # every member, and `_ensure_seat` clears a seat's pending-removal `ends_at` — so an
    # admin toggling something unrelated would silently un-schedule departures the
    # lab arranged. The form always sends the current status; that must be inert.
    needs_activation = status == Subscription.Status.ACTIVE and (
        sub.status != Subscription.Status.ACTIVE or sub.current_period_end is None
    )
    if needs_activation:
        activate_lab_subscription(lab)
        sub.refresh_from_db()
    elif status is not None and status != sub.status:
        sub.status = status
        sub.save(update_fields=["status", "updated_at"])

    if "mylo_included" in data:
        set_mylo_included(sub, data["mylo_included"])

    record_audit_event(
        actor=admin,
        action="admin.lab_subscription.assign",
        target_type="lab",
        target_id=str(lab.pk),
        metadata={
            "tier": sub.tier,
            "status": sub.status,
            "expires_at": sub.expires_at.isoformat() if sub.expires_at else None,
            "is_comped": sub.is_comped,
            "mylo_included": mylo_included(sub),
        },
    )
    return sub


__all__ = [
    "SeatCeilingExceeded",
    "TierScopeError",
    "apply_lab_update",
    "apply_user_update",
    "assign_subscription",
    "ensure_lab_subscription",
    "personal_subscription",
    "set_watch_limit",
]
