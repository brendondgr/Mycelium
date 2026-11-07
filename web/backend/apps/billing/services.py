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

from django.conf import settings
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
from .tiers import tier_allowed_for_scope, validate_tier_for_scope

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
def create_department_workspace(
    user: User, name: str, *, institution: str = ""
) -> ProvisionResult:
    """Create one department with its founder as OWNER, plus an INACTIVE plan.

    The department sibling of :func:`create_lab_workspace`, and shared the same way:
    the "create a department after my account exists" endpoint and the legacy
    ``provision_workspace`` branch both land here so the org + billing rows never
    drift. ``Department.profile`` is created by the ``post_save`` signal.
    """
    dept = Department.objects.create(
        owner=user,
        name=name,
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


def signup_grant_tier() -> str:
    """The personal tier a successful sign-up is provisioned on.

    Getting past the instance's sign-up gate is treated as the entitlement:
    rather than land every new account on Free and make them ask for an upgrade,
    it grants ``settings.SIGNUP_GRANT_TIER`` (``billing.signup_tier`` in
    mycelium.toml). It only decides anything while billing is on.

    Falls back to Free when the configured value is not a tier sold to a personal
    scope, because a typo in an env var must not 500 the sign-up endpoint — and
    :func:`provision_workspace` would raise ``TierScopeError`` on, say, "lab".
    """
    tier = str(getattr(settings, "SIGNUP_GRANT_TIER", "") or "").strip().lower()
    return tier if tier_allowed_for_scope("user", tier) else Tier.FREE


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
        # A personal account can only ever be sold a personal tier. Signup never asks
        # for one, but this is a public entry point — a Lab tier here would hand team
        # features to an account with no roster to price them against.
        validate_tier_for_scope("user", personal_tier)
        sub = Subscription.objects.create(tier=personal_tier, scope_user=user)
        seat = Seat.objects.create(subscription=sub, member=user, payer_user=user)
        return ProvisionResult(subscription=sub, seat=seat)

    if account_type == "lab":
        return create_lab_workspace(user, org_name)

    if account_type == "department":
        return create_department_workspace(user, org_name, institution=institution)

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
    validate_tier_for_scope("lab", sub.tier)
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
    """Activate a department's plan and seat its **plan** membership ACTIVE (L2).

    Plan membership is direct department members ∪ every member of every lab the head
    has **included** in the plan (``plan_member_ids``), so an included lab's member is
    auto-entitled department-paid — the seat is what makes rule 2 real. A lab under the
    department that has not been opted in is not seated here (its members keep their
    lab's own plan, or Free).
    """
    # Local import avoids an accounts↔billing import cycle at module load.
    from apps.accounts.services import plan_member_ids

    sub = department_subscription(department)
    if sub is None:
        raise ValueError("Department has no subscription to activate.")
    validate_tier_for_scope("department", sub.tier)
    period.activate(sub, on=on)
    member_ids = plan_member_ids(department)
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
    """Attach a lab to a department (B2).

    Attaching only sets the department FK; it does **not** put the lab on the plan.
    Inclusion is opt-in — the department head includes the lab explicitly via
    :func:`set_lab_plan_inclusion`, which is what seats its members department-paid.
    A freshly-attached lab therefore starts opt-out and its members keep whatever
    they had (their lab's own plan, or Free).
    """
    lab.department = department
    lab.save(update_fields=["department", "updated_at"])
    return lab


@transaction.atomic
def set_lab_plan_inclusion(lab, included: bool) -> Lab:
    """Include or exclude a lab in its department's plan, re-seating its members (B2).

    On **include** (plan active): each lab member is seated ACTIVE department-paid and
    their now-redundant lab seat (if the lab has its own active plan) is scheduled to
    end — one paying scope per member. On **exclude**: the department seat is scheduled
    to end (deferred, L3 — it stays ACTIVE and billed through the current period, no
    credit) for every member no longer covered by the plan (``plan_member_ids``,
    recomputed with the flag now off). Removal is deferred rather than re-seating the
    member lab-paid inline, so a member is never on two paid seats at once (B2); the
    lab-paid fallback is picked up by the normal seat sync once the dept seat lapses,
    exactly as detaching a lab behaves. A no-op on seats while the department plan is
    inactive (the flag is stored and takes effect at activation, which seats
    ``plan_member_ids``).
    """
    from apps.accounts.services import plan_member_ids

    if lab.department_id is None:
        raise ValueError("Lab is not in a department.")
    if lab.department_plan_included == included:
        return lab
    lab.department_plan_included = included
    lab.save(update_fields=["department_plan_included", "updated_at"])

    department = lab.department
    dept_sub = _active_subscription_for_department(department)
    if dept_sub is None:
        return lab
    lab_sub = _active_subscription_for_lab(lab)
    memberships = list(
        LabMembership.objects.filter(lab=lab).select_related("user")
    )
    if included:
        for membership in memberships:
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
    else:
        remaining = plan_member_ids(department)  # recomputed with the flag off
        for membership in memberships:
            if membership.user_id in remaining:
                continue  # still covered (direct member, or another included lab)
            schedule_seat_removal(dept_sub, membership.user)
    return lab
