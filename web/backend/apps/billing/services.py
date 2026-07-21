"""Workspace provisioning + subscription activation.

Single source of truth for the org + billing rows created at signup, and for turning an
inactive org plan into an active, seat-priced one. The registration view (and, ideally,
``seed_demo``) funnel through here so org-creation logic never drifts.

**Structure is free (L1).** A ``lab`` / ``department`` account is created with an
**INACTIVE** subscription and a ``PENDING`` founder seat — the org exists and can add
people and labs, but grants nothing until a PI/head explicitly *activates* the plan.
Activation opens the billing period and seats covered members ACTIVE (a lab across its
members; a department across its effective membership — direct members ∪ every member
of every lab under it, L2). Personal accounts stay ACTIVE (Free is the baseline).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from django.contrib.auth.models import User
from django.db import transaction
from django.utils.text import slugify

from apps.accounts.models import (
    Department,
    DeptMembership,
    Lab,
    LabMembership,
)

from . import period
from .models import Seat, SeatEvent, Subscription, Tier
from .seats import (
    _active_subscription_for_department,
    _active_subscription_for_lab,
    _ensure_seat,
    schedule_seat_removal,
)

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
def create_lab_workspace(user: User, name: str) -> ProvisionResult:
    """Create one lab with its founder as OWNER + PI lead, plus an INACTIVE plan.

    Shared by signup (``provision_workspace``) and the "create a lab after my account
    exists" endpoint so the org + billing rows never drift. The plan starts INACTIVE and
    the founder's seat starts PENDING (lab-paid); both go live at
    :func:`activate_lab_subscription`. ``Lab.profile`` is created by the ``post_save``
    signal.
    """
    lab = Lab.objects.create(name=name, slug=_unique_lab_slug(name))
    LabMembership.objects.create(
        user=user,
        lab=lab,
        role=LabMembership.Role.OWNER,
        is_lead=True,
    )
    sub = Subscription.objects.create(
        tier=Tier.LAB, scope_lab=lab, status=Subscription.Status.INACTIVE
    )
    seat = Seat.objects.create(
        subscription=sub, member=user, payer_lab=lab, status=Seat.Status.PENDING
    )
    return ProvisionResult(subscription=sub, seat=seat, lab=lab)


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

    ``personal`` creates an ACTIVE user-scoped subscription + self-paid seat (Free is
    the baseline). ``lab`` and ``department`` create the org row, a founding membership
    (lab founder is OWNER + PI lead; department founder is OWNER), an **INACTIVE** plan,
    and a **PENDING** founder seat (org-paid) that activation later turns ACTIVE.
    """
    if account_type == "personal":
        sub = Subscription.objects.create(tier=personal_tier, scope_user=user)
        seat = Seat.objects.create(subscription=sub, member=user, payer_user=user)
        return ProvisionResult(subscription=sub, seat=seat)

    if account_type == "lab":
        return create_lab_workspace(user, org_name)

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
        sub = Subscription.objects.create(
            tier=Tier.CANOPY,
            scope_department=dept,
            status=Subscription.Status.INACTIVE,
        )
        seat = Seat.objects.create(
            subscription=sub,
            member=user,
            payer_department=dept,
            status=Seat.Status.PENDING,
        )
        return ProvisionResult(subscription=sub, seat=seat, department=dept)

    raise ValueError(f"Unknown account_type: {account_type!r}")


# --------------------------------------------------------------------------- #
# Activation — flip an inactive org plan on and seat its covered members.
# --------------------------------------------------------------------------- #


def lab_subscription(lab) -> Subscription | None:
    """The lab's plan regardless of status (the newest scope_lab subscription)."""
    return Subscription.objects.filter(scope_lab=lab).order_by("-created_at").first()


def department_subscription(department) -> Subscription | None:
    """The department's plan regardless of status."""
    return (
        Subscription.objects.filter(scope_department=department)
        .order_by("-created_at")
        .first()
    )


@transaction.atomic
def activate_lab_subscription(lab, *, on: date | None = None) -> Subscription:
    """Activate a lab's plan and seat every current lab member ACTIVE (lab-paid).

    Raises :class:`ValueError` if the lab has no plan, or
    :class:`~apps.billing.seats.SeatCeilingExceeded` if the roster is over the tier
    ceiling. Idempotent: re-activating leaves the period untouched and re-seats members.
    """
    sub = lab_subscription(lab)
    if sub is None:
        raise ValueError("Lab has no subscription to activate.")
    period.activate(sub, on=on)
    for membership in LabMembership.objects.filter(lab=lab).select_related("user"):
        _ensure_seat(
            sub,
            membership.user,
            status=Seat.Status.ACTIVE,
            payer_type="lab",
            payer_obj=lab,
            event_kind=SeatEvent.Kind.ACTIVATED,
        )
    return sub


@transaction.atomic
def activate_department_subscription(
    department, *, on: date | None = None
) -> Subscription:
    """Activate a department's plan and seat its **effective** membership ACTIVE (L2).

    Effective membership is direct department members ∪ every member of every lab under
    the department (``effective_member_ids``), so a lab-under-department member is
    auto-entitled — the department-paid seat is what makes rule 2 real.
    """
    # Local import avoids an accounts↔billing import cycle at module load.
    from apps.accounts.services import effective_member_ids

    sub = department_subscription(department)
    if sub is None:
        raise ValueError("Department has no subscription to activate.")
    period.activate(sub, on=on)
    member_ids = effective_member_ids(department)
    for user in User.objects.filter(id__in=member_ids):
        _ensure_seat(
            sub,
            user,
            status=Seat.Status.ACTIVE,
            payer_type="department",
            payer_obj=department,
            event_kind=SeatEvent.Kind.ACTIVATED,
        )
    return sub


@transaction.atomic
def attach_lab_to_department(lab, department) -> Lab:
    """Attach a lab to a department, re-seating its members onto the dept plan (B2).

    If the department plan is active, every lab member is seated department-paid and
    their now-redundant lab seat (if the lab had an active plan) is scheduled to end —
    one paying scope per member. A no-op on seats when the department is inactive.
    """
    lab.department = department
    lab.save(update_fields=["department", "updated_at"])
    dept_sub = _active_subscription_for_department(department)
    if dept_sub is None:
        return lab
    lab_sub = _active_subscription_for_lab(lab)
    for membership in LabMembership.objects.filter(lab=lab).select_related("user"):
        _ensure_seat(
            dept_sub,
            membership.user,
            status=Seat.Status.ACTIVE,
            payer_type="department",
            payer_obj=department,
            event_kind=SeatEvent.Kind.ACTIVATED,
        )
        if lab_sub is not None:
            schedule_seat_removal(lab_sub, membership.user)
    return lab
