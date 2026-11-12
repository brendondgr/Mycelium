"""What each role may do in a lab or a department — the one place that says so.

A capability is a named right over one org: edit its profile, manage its
people, run its servers. The list is closed (:data:`CAPABILITIES`) and every
role maps onto a fixed set of them (:data:`LAB_PRESETS`, :data:`DEPT_PRESETS`).
Nothing else in the codebase decides "may this person do X here?" from a role:
the permission functions in :mod:`apps.accounts.permissions` are thin calls into
:func:`has_capability`, ``/api/auth/me/`` sends each org's set to the app, and
the app asks ``can(org, capability)`` rather than re-deriving it from the role.

Roles are presets for now — owner, admin, member, viewer, and the lead PI, who
holds every capability an admin does (settings plan, decision 13). Giving one
admin more or less than the preset would be a data change against this list,
not a rewrite; it is deliberately not built (decision 14).

Rank — who may grant which role, and who may act on whom — is a different
question and stays in :mod:`apps.accounts.permissions`. A capability says *that*
someone manages people; rank says *whom*.

Org-scoped views declare what they need in a ``capabilities`` attribute, a map
from HTTP method to a capability or :data:`MEMBERSHIP`. A test walks every
org-scoped route and fails on a view that names none.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Q
from rest_framework.exceptions import PermissionDenied

from .models import Department, DeptMembership, Lab, LabMembership

if TYPE_CHECKING:
    from django.contrib.auth.models import AnonymousUser, User

PROFILE_EDIT = "org.profile.edit"
PEOPLE_VIEW = "org.people.view"
PEOPLE_MANAGE = "org.people.manage"
INVITES_ISSUE = "org.invites.issue"
PROJECTS_POLICY = "org.projects.policy"
PROJECTS_OVERSEE = "org.projects.oversee"
SERVERS_MANAGE = "org.servers.manage"
ANNOUNCEMENTS_MANAGE = "org.announcements.manage"
MYLO_POLICY = "org.mylo.policy"
BILLING_MANAGE = "org.billing.manage"
TRANSFER = "org.transfer"

#: The closed list, in the order the app shows them.
CAPABILITIES: tuple[str, ...] = (
    PROFILE_EDIT,
    PEOPLE_VIEW,
    PEOPLE_MANAGE,
    INVITES_ISSUE,
    PROJECTS_POLICY,
    PROJECTS_OVERSEE,
    SERVERS_MANAGE,
    ANNOUNCEMENTS_MANAGE,
    MYLO_POLICY,
    BILLING_MANAGE,
    TRANSFER,
)

#: Not a capability: "any member of the org". A view declares it for what every
#: member may read (a lab's feeds, its roster). Every preset grants
#: :data:`PEOPLE_VIEW`, so a non-empty capability set is membership.
MEMBERSHIP = "org.membership"

_ALL = frozenset(CAPABILITIES)
_MANAGER = _ALL - {TRANSFER}
_READER = frozenset({PEOPLE_VIEW})

#: Lab presets. ``lead`` is the lead PI flag, held beside a role; a membership's
#: capabilities are the union of its role's preset and, if it leads, ``lead``.
LAB_PRESETS: dict[str, frozenset[str]] = {
    LabMembership.Role.OWNER: _ALL,
    LabMembership.Role.ADMIN: _MANAGER,
    "lead": _MANAGER,
    LabMembership.Role.MEMBER: _READER,
    LabMembership.Role.VIEWER: _READER,
}

#: Department presets. ``owner`` is the head (``Department.owner``); an OWNER
#: row on anyone else counts as admin, never as a second head. ``affiliate`` is
#: someone folded in through one of the department's labs with no direct row.
DEPT_PRESETS: dict[str, frozenset[str]] = {
    DeptMembership.Role.OWNER: _ALL,
    DeptMembership.Role.ADMIN: _MANAGER,
    DeptMembership.Role.MEMBER: _READER,
    DeptMembership.Role.VIEWER: _READER,
    "affiliate": _READER,
}

#: What a Discord gate level (``integrations.services.gate._Action``) asks of
#: the web's rights, so the bot and the app agree. ``access`` is membership.
GATE_LEVELS: dict[str, str] = {
    "manage": SERVERS_MANAGE,
    "edit": PROFILE_EDIT,
    "access": MEMBERSHIP,
}

Org = Lab | Department


def membership_capabilities(membership: LabMembership) -> frozenset[str]:
    """One lab membership's capabilities: its role's preset, plus the lead's."""
    caps = LAB_PRESETS.get(membership.role, frozenset())
    if membership.is_lead:
        caps = caps | LAB_PRESETS["lead"]
    return caps


def dept_preset(
    department: Department, user_id: int, row_role: str | None
) -> str | None:
    """The department preset for a user, from the head FK and their direct row."""
    if department.owner_id == user_id:
        return DeptMembership.Role.OWNER
    if row_role is None:
        return None
    if row_role == DeptMembership.Role.OWNER:
        return DeptMembership.Role.ADMIN
    return row_role


def lab_capabilities(user: User | AnonymousUser, lab: Lab) -> frozenset[str]:
    """``user``'s capabilities in ``lab``; empty for a non-member."""
    if not user.is_authenticated:
        return frozenset()
    membership = LabMembership.objects.filter(user=user, lab=lab).first()
    if membership is None:
        return frozenset()
    return membership_capabilities(membership)


def dept_capabilities(
    user: User | AnonymousUser, department: Department
) -> frozenset[str]:
    """``user``'s capabilities in ``department``; empty for a stranger."""
    if not user.is_authenticated:
        return frozenset()
    row = (
        DeptMembership.objects.filter(user=user, department=department)
        .values_list("role", flat=True)
        .first()
    )
    preset = dept_preset(department, user.id, row)
    if preset is not None:
        return DEPT_PRESETS.get(preset, frozenset())
    if LabMembership.objects.filter(user=user, lab__department=department).exists():
        return DEPT_PRESETS["affiliate"]
    return frozenset()


def org_capabilities(user: User | AnonymousUser, org: Org) -> frozenset[str]:
    if isinstance(org, Lab):
        return lab_capabilities(user, org)
    if isinstance(org, Department):
        return dept_capabilities(user, org)
    raise TypeError(f"Not an org: {org!r}")


def has_capability(user: User | AnonymousUser, org: Org, capability: str) -> bool:
    """Whether ``user`` holds ``capability`` (or, for :data:`MEMBERSHIP`, any)."""
    if capability != MEMBERSHIP and capability not in _ALL:
        raise ValueError(f"Unknown capability: {capability}")
    caps = org_capabilities(user, org)
    if capability == MEMBERSHIP:
        return bool(caps)
    return capability in caps


def require(
    user: User | AnonymousUser, org: Org, capability: str, message: str = ""
) -> None:
    """Refuse with 403 unless ``user`` holds ``capability`` in ``org``."""
    if not has_capability(user, org, capability):
        kind = "lab" if isinstance(org, Lab) else "department"
        raise PermissionDenied(message or f"You do not have access to this {kind}.")


def lab_capability_q(capability: str, prefix: str = "") -> Q:
    """The ``LabMembership`` filter for "holds ``capability`` in the lab".

    Built from :data:`LAB_PRESETS`, so bulk queries ("every manager of this
    lab") agree with :func:`has_capability`. ``prefix`` is the relation path
    when filtering from another model (``"lab_memberships__"`` from ``User``).
    """
    roles = [
        role
        for role, caps in LAB_PRESETS.items()
        if role != "lead" and (capability == MEMBERSHIP or capability in caps)
    ]
    q = Q(**{f"{prefix}role__in": roles})
    if capability == MEMBERSHIP or capability in LAB_PRESETS["lead"]:
        q |= Q(**{f"{prefix}is_lead": True})
    return q


def capabilities_for_user(user: User) -> dict[str, dict[str, list[str]]]:
    """Every org the caller acts in, with their capabilities — for ``/me``.

    Labs are the caller's memberships; departments are the ones they head or
    hold a direct role in (the departments the app lists, not the ones they are
    folded into through a lab). Lists follow :data:`CAPABILITIES` order.
    """
    labs = {
        m.lab.slug: _ordered(membership_capabilities(m))
        for m in LabMembership.objects.filter(user=user).select_related("lab")
    }
    rows = dict(
        DeptMembership.objects.filter(user=user).values_list("department_id", "role")
    )
    departments: dict[str, list[str]] = {}
    for department in Department.objects.filter(
        Q(owner=user) | Q(memberships__user=user)
    ).distinct():
        preset = dept_preset(department, user.id, rows.get(department.id))
        departments[str(department.id)] = _ordered(
            DEPT_PRESETS.get(preset or "", frozenset())
        )
    return {"labs": labs, "departments": departments}


def _ordered(caps: frozenset[str]) -> list[str]:
    return [c for c in CAPABILITIES if c in caps]


def declared(view: type, method: str) -> str | None:
    """The capability a view class declares for ``method``, or ``None``."""
    mapping = getattr(view, "capabilities", None) or {}
    return mapping.get(method.upper())
