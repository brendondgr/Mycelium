"""Keep billing seats in step with membership — the single wiring behind rules 1 & 2.

Every membership-mutating path (invite-accept, the lab/department member endpoints,
attach-lab) calls these helpers; ``reconcile_seats`` is the bulk backfill backstop. This
is deliberately an explicit service rather than a global signal, so seat writes only
happen where the code means them to (seeding and tests never fire surprise grants).

Decision **B2 — one paying scope per member:** if a member's lab belongs to a department
with an active plan, the *department* seats them (department-paid) and the lab does not;
otherwise the lab's own active plan seats them (lab-paid). This avoids double-billing a
member who is both a lab member and (through that lab) a department member.
"""

from __future__ import annotations

from django.contrib.auth.models import User

from .models import Seat, Subscription
from .seats import (
    _active_subscription_for_department,
    _active_subscription_for_lab,
    grant_seat_for_dept_member,
    grant_seat_for_lab_member,
    schedule_seat_removal,
)


def paying_scope_for_lab(lab) -> tuple[str | None, Subscription | None]:
    """The subscription that should pay for this lab's members (B2).

    Returns ``("department", sub)`` when the lab is **included** in a department with
    an active plan, else ``("lab", sub)`` for the lab's own active plan, else
    ``(None, None)``. Department inclusion is opt-in: a lab under a department whose
    head has not included it (``department_plan_included`` False) is not paid for by
    the department, so its members fall back to the lab's own plan (or nothing).
    """
    dept = getattr(lab, "department", None)
    if dept is not None and getattr(lab, "department_plan_included", False):
        dept_sub = _active_subscription_for_department(dept)
        if dept_sub is not None:
            return "department", dept_sub
    lab_sub = _active_subscription_for_lab(lab)
    if lab_sub is not None:
        return "lab", lab_sub
    return None, None


def sync_lab_member(user: User, lab) -> Seat | None:
    """Seat a lab member on the correct active paying scope (B2).

    Idempotent; a no-op returning ``None`` when neither the lab nor its department is
    active (structure without a plan grants nothing).
    """
    kind, _sub = paying_scope_for_lab(lab)
    if kind == "department":
        return grant_seat_for_dept_member(user, lab.department)
    if kind == "lab":
        return grant_seat_for_lab_member(user, lab)
    return None


def sync_dept_member(user: User, department) -> Seat | None:
    """Seat a direct department member on the department's active plan (rule 2)."""
    return grant_seat_for_dept_member(user, department)


def fallback_lab_seats(user: User) -> None:
    """Re-seat ``user`` on their labs' correct paying scope after a seat lapses.

    When a member's department-paid seat is revoked (an excluded or detached lab, a
    department removal), they should not silently drop to Free while a lab they are
    still in carries its own active plan — they belong on that lab-paid seat. This
    re-runs :func:`sync_lab_member` for every lab the user is in, which grants the
    lab-paid seat wherever :func:`paying_scope_for_lab` now resolves to the lab. It
    cannot revive the just-revoked department seat: a member whose department seat
    lapsed is, by construction, no longer covered by that department through any of
    their labs, so none of those labs resolve to the department scope.
    """
    from apps.accounts.models import LabMembership

    for membership in LabMembership.objects.filter(user=user).select_related("lab"):
        sync_lab_member(user, membership.lab)


def unsync_lab_member(user: User, lab) -> Seat | None:
    """Schedule removal of a lab member's seat on whichever scope pays for the lab."""
    _kind, sub = paying_scope_for_lab(lab)
    return schedule_seat_removal(sub, user) if sub is not None else None


def unsync_dept_member(user: User, department) -> Seat | None:
    """Schedule removal of a direct department member's seat."""
    return schedule_seat_removal(
        _active_subscription_for_department(department), user
    )
