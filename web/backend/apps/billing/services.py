"""Workspace provisioning: turn a freshly created user into a working account.

Single source of truth for the org + billing rows created at signup. The
registration view (and, ideally, ``seed_demo``) funnel through here so
org-creation logic never drifts between them.

Every account type creates a :class:`~apps.billing.models.Subscription` plus one
founding :class:`~apps.billing.models.Seat`, so each account has an explicit seat
from day one — a clean basis for later seat counting and Stripe. The caller owns
the ``User``; this service only builds the workspace around it.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.contrib.auth.models import User
from django.db import transaction
from django.utils.text import slugify

from apps.accounts.models import (
    Department,
    DeptMembership,
    Lab,
    LabMembership,
)

from .models import Seat, Subscription, Tier

ACCOUNT_TYPES = ("personal", "lab", "department")


@dataclass(frozen=True)
class ProvisionResult:
    """The rows created for one new account."""

    subscription: Subscription
    seat: Seat
    lab: Lab | None = None
    department: Department | None = None


def _unique_lab_slug(name: str) -> str:
    """A slug derived from the lab name, made unique with a numeric suffix.

    ``Lab.slug`` is ``max_length=80``; the base is capped well under that so the
    ``-N`` disambiguator always fits.
    """
    base = slugify(name)[:70] or "lab"
    slug, n = base, 1
    while Lab.objects.filter(slug=slug).exists():
        n += 1
        slug = f"{base}-{n}"
    return slug


@transaction.atomic
def provision_workspace(
    user: User,
    account_type: str,
    *,
    org_name: str = "",
    institution: str = "",
    personal_tier: str = Tier.FREE,
) -> ProvisionResult:
    """Create the org + billing rows for a new account.

    ``personal`` creates only the user-scoped subscription + self-paid seat;
    ``lab`` and ``department`` also create the org row and a founding membership
    (lab founder is OWNER + PI lead; department founder is OWNER). The founder
    pays for their own seat in every case (``payer_user``).
    """
    if account_type == "personal":
        sub = Subscription.objects.create(tier=personal_tier, scope_user=user)
        seat = Seat.objects.create(subscription=sub, member=user, payer_user=user)
        return ProvisionResult(subscription=sub, seat=seat)

    if account_type == "lab":
        lab = Lab.objects.create(name=org_name, slug=_unique_lab_slug(org_name))
        LabMembership.objects.create(
            user=user,
            lab=lab,
            role=LabMembership.Role.OWNER,
            is_lead=True,
        )
        sub = Subscription.objects.create(tier=Tier.LAB, scope_lab=lab)
        seat = Seat.objects.create(subscription=sub, member=user, payer_user=user)
        return ProvisionResult(subscription=sub, seat=seat, lab=lab)

    if account_type == "department":
        dept = Department.objects.create(
            owner=user,
            name=org_name,
            institution=institution,
        )
        DeptMembership.objects.create(
            user=user,
            department=dept,
            role=DeptMembership.Role.OWNER,
        )
        sub = Subscription.objects.create(tier=Tier.CANOPY, scope_department=dept)
        seat = Seat.objects.create(subscription=sub, member=user, payer_user=user)
        return ProvisionResult(subscription=sub, seat=seat, department=dept)

    raise ValueError(f"Unknown account_type: {account_type!r}")
