from django.contrib.auth.models import AnonymousUser, User
from django.db.models import Q
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission

from . import capabilities as caps
from .models import Department, DeptMembership, Lab, LabMembership, ProjectCreation

UserOrAnon = User | AnonymousUser


#: Why there is no ``is_superuser`` escape hatch below.
#:
#: A superuser used to pass every lab and department check here, which made an
#: operator account a silent member of every workspace: opening a lab URL showed
#: its feed, its members and its settings even though no ``LabMembership`` row
#: said so. That is the wrong shape for two reasons. It reads someone else's
#: research without leaving a membership anybody can audit, and it means an
#: operator cannot tell what a *member* sees from what their own privilege
#: grants — the account that most needs to reproduce a bug is the one account
#: that cannot.
#:
#: Platform administration goes through the admin dashboard instead
#: (``apps.adminpanel``, guarded by its own ``IsStaffOrSuperuser``) and Django
#: admin. Those surfaces are built to be audited; the workspace API is not.
#: Object-level authority in this module is therefore membership, and only
#: membership. The one deliberate exception is :func:`user_email_verified`,
#: which exempts staff because an operator-created account has no mailbox to
#: answer a code with — that is about activation, not about access to data.


#: Every function below that answers "may this person do X in this org?" is a
#: thin call into :mod:`apps.accounts.capabilities`, which alone maps roles to
#: rights. The names stay because many callers use them; new code may call
#: :func:`apps.accounts.capabilities.has_capability` directly.


def user_has_lab_access(user: UserOrAnon, lab: Lab) -> bool:
    return caps.has_capability(user, lab, caps.MEMBERSHIP)


#: The roles that manage a lab on their own account.
LAB_MANAGER_ROLES = (LabMembership.Role.OWNER, LabMembership.Role.ADMIN)


def lab_manager_q(prefix: str = "") -> Q:
    """The ``LabMembership`` filter for "manages this lab": owner, admin or lead PI.

    A lead PI holds every right an admin does (settings plan, decision 13). Before
    this, a PI who was not also owner/admin could edit the lab profile and invite,
    but the Discord, announcement and member endpoints refused them while the app
    showed them the controls. Bulk queries that list a lab's managers use this so
    they agree with :func:`user_can_manage_lab`; ``prefix`` is the relation path
    when filtering from another model (``"lab_memberships__"`` from ``User``).
    """
    return caps.lab_capability_q(caps.PEOPLE_MANAGE, prefix)


def user_can_manage_lab(user: UserOrAnon, lab: Lab) -> bool:
    """Owner, admin, or the lab's lead PI: ``org.people.manage``."""
    return caps.has_capability(user, lab, caps.PEOPLE_MANAGE)


#: Lab roles, ranked. Authority runs strictly downward: an actor may only act on
#: a target *below* them, and may only grant a role *below* their own.
#:
#: Before this, ``user_can_manage_lab`` (owner **or** admin) was the only gate on
#: role edits, and ``set_lab_member_role`` accepted every role — so any admin
#: could mint an owner, including themselves, or quietly appoint another admin.
#: Two consequences, both bad: a lab could be taken from its PI by someone the PI
#: promoted, and "transfer ownership is irreversible" was unimplementable,
#: because a demoted owner could simply set themselves back.
#:
#: The rank rule gives the product what it asked for without special cases: only
#: the PI (owner) creates admins, only the PI creates owners — and that last one
#: only through :func:`apps.accounts.services.transfer_lab_ownership`, never a
#: plain role edit.
LAB_ROLE_RANK: dict[str, int] = {
    LabMembership.Role.OWNER: 3,
    LabMembership.Role.ADMIN: 2,
    LabMembership.Role.MEMBER: 1,
    LabMembership.Role.VIEWER: 0,
}


def lab_role_rank(user: UserOrAnon, lab: Lab) -> int:
    """``user``'s authority in ``lab``; ``-1`` for a non-member.

    ``-1`` rather than ``0`` because a viewer is a member with the least
    authority, and a stranger is not a member at all — they must not compare
    equal to the bottom role.
    """
    if not user.is_authenticated:
        return -1
    membership = LabMembership.objects.filter(user=user, lab=lab).first()
    if membership is None:
        return -1
    return membership_rank(membership)


def membership_rank(membership: LabMembership) -> int:
    """One membership's rank: its role, raised to admin for a lead PI.

    A lead PI holds every right an admin does, including granting the roles
    below admin and acting on members and viewers. They do not outrank an
    admin, and only the owner still creates admins.
    """
    rank = LAB_ROLE_RANK.get(membership.role, 0)
    if membership.is_lead:
        rank = max(rank, LAB_ROLE_RANK[LabMembership.Role.ADMIN])
    return rank


def user_can_grant_lab_role(user: UserOrAnon, lab: Lab, role: str) -> bool:
    """Whether ``user`` may hand out ``role`` in ``lab``.

    Strictly below their own rank, so nobody can clone their own authority and
    an owner is only ever made by the transfer route.
    """
    granted = LAB_ROLE_RANK.get(role)
    if granted is None:
        return False
    return lab_role_rank(user, lab) > granted


def user_outranks_lab_member(user: UserOrAnon, lab: Lab, target: User) -> bool:
    """Whether ``user`` may act on ``target`` at all — remove them, or re-role them."""
    return lab_role_rank(user, lab) > lab_role_rank(target, lab)


def user_can_invite_with_lab_role(user: UserOrAnon, lab: Lab, role: str) -> bool:
    """Whether ``user`` may bring someone into ``lab`` *as* ``role``.

    Every path that grants a lab role — a direct add, a legacy invitation, an
    emailed invitation or a share link — asks this one question, so the rule
    cannot be skipped by picking a different door:

    * ``owner`` is never granted this way. Ownership moves only by
      :func:`apps.accounts.services.transfer_lab_ownership`.
    * ``admin`` only from the owner — the strict rank rule above.
    * ``member`` and ``viewer`` from anyone who may invite at all, which also
      covers a lead PI whose own role is ``member``; holding the lab's PI badge
      is what lets them invite people, not their role column.
    """
    if role not in LAB_ROLE_RANK or role == LabMembership.Role.OWNER:
        return False
    if role == LabMembership.Role.ADMIN:
        return user_can_grant_lab_role(user, lab, role)
    return user_can_invite_to_lab(user, lab)


def user_can_edit_lab_profile(user: UserOrAnon, lab: Lab) -> bool:
    """A lab's interest profile is edited by its lead PI or owner/admin (brief G)."""
    return caps.has_capability(user, lab, caps.PROFILE_EDIT)


def user_can_invite_to_lab(user: UserOrAnon, lab: Lab) -> bool:
    """A lab's PI (lead) or owner/admin may invite people to it."""
    return caps.has_capability(user, lab, caps.INVITES_ISSUE)


def user_can_create_lab_project(user: UserOrAnon, lab: Lab) -> bool:
    """Who may start a project in ``lab``: its PI / owner / admins always; any
    other member (not a viewer) while the lab's *Who can create projects*
    setting is "any member" (the default)."""
    if not user.is_authenticated:
        return False
    if user_can_edit_lab_profile(user, lab):
        return True
    if lab.project_creation != ProjectCreation.MEMBERS:
        return False
    return (
        LabMembership.objects.filter(user=user, lab=lab)
        .exclude(role=LabMembership.Role.VIEWER)
        .exists()
    )


def user_can_create_department_project(
    user: UserOrAnon, department: Department
) -> bool:
    """Who may start a department project: its owner / admins always; any
    effective member while the department's setting is "any member"."""
    if not user.is_authenticated:
        return False
    if user_can_edit_dept_profile(user, department):
        return True
    if department.project_creation != ProjectCreation.MEMBERS:
        return False
    return user_has_department_access(user, department)


def user_has_department_access(user: UserOrAnon, department: Department) -> bool:
    """The head, a direct member, or a member of one of its labs."""
    return caps.has_capability(user, department, caps.MEMBERSHIP)


#: Department roles, ranked — the twin of :data:`LAB_ROLE_RANK`, and for the same
#: reason. Before it, ``DeptMembersView.post`` accepted any role from any
#: manager, so a department admin could mint owners and admins, themselves
#: included. Authority now runs strictly downward: only the head creates
#: admins, and the head is only ever made by
#: :func:`apps.accounts.services.transfer_department_ownership`.
#:
#: The head is ``Department.owner``. Their ``DeptMembership`` row is kept at
#: OWNER in step with it, but rank reads the foreign key, so a stray OWNER row
#: on anyone else counts as an admin, never as a second head.
DEPT_ROLE_RANK: dict[str, int] = {
    DeptMembership.Role.OWNER: 3,
    DeptMembership.Role.ADMIN: 2,
    DeptMembership.Role.MEMBER: 1,
    DeptMembership.Role.VIEWER: 0,
}


def dept_role_rank(user: UserOrAnon, department: Department) -> int:
    """``user``'s authority in ``department``; ``-1`` without a direct role.

    Someone folded in through a lab has access but no department role, so they
    rank with strangers here: they hold no authority over the department roster.
    """
    if not user.is_authenticated:
        return -1
    if department.owner_id == user.id:
        return DEPT_ROLE_RANK[DeptMembership.Role.OWNER]
    membership = DeptMembership.objects.filter(
        user=user, department=department
    ).first()
    if membership is None:
        return -1
    rank = DEPT_ROLE_RANK.get(membership.role, 0)
    return min(rank, DEPT_ROLE_RANK[DeptMembership.Role.ADMIN])


def user_can_grant_dept_role(
    user: UserOrAnon, department: Department, role: str
) -> bool:
    """Whether ``user`` may hand out ``role`` in ``department`` — strictly below."""
    granted = DEPT_ROLE_RANK.get(role)
    if granted is None:
        return False
    return dept_role_rank(user, department) > granted


def user_outranks_dept_member(
    user: UserOrAnon, department: Department, target: User
) -> bool:
    """Whether ``user`` may act on ``target`` — remove them, or re-role them."""
    return dept_role_rank(user, department) > dept_role_rank(target, department)


def user_can_grant_org_role(
    user: UserOrAnon,
    role: str,
    *,
    lab: Lab | None = None,
    department: Department | None = None,
) -> bool:
    """The grant rule for whichever org an invitation names."""
    if lab is not None:
        return user_can_grant_lab_role(user, lab, role)
    if department is not None:
        return user_can_grant_dept_role(user, department, role)
    return False


def user_can_edit_dept_profile(user: UserOrAnon, department: Department) -> bool:
    """A department's interest profile is edited by its owner or an admin (brief G)."""
    return caps.has_capability(user, department, caps.PROFILE_EDIT)


def user_can_manage_department(user: UserOrAnon, department: Department) -> bool:
    """Manage a department's members, labs, and subscription: owner or admin only.

    Same authority as editing the department profile — the head (owner) plus any
    ``DeptMembership`` with an OWNER/ADMIN role — surfaced under a management-intent
    name so the member/lab/billing endpoints read clearly.
    """
    return caps.has_capability(user, department, caps.PEOPLE_MANAGE)


#: Message every organization endpoint gives an account that has not verified.
UNVERIFIED_MESSAGE = (
    "Verify your email address to activate your account. "
    "Enter the code we sent you from the Account page."
)


def user_email_verified(user: UserOrAnon) -> bool:
    """Whether ``user``'s account is active.

    Verification is what activates an account *when the instance asks for it*
    (``signup.verify_email``, or ``signup.mode = "domain"``); otherwise every
    account is active at creation. Staff are exempt because they are created by
    an operator, not by the sign-up form, and there may be no mailbox behind the
    address at all. ``Profile.is_verified`` still records whether the address was
    actually proved — this function answers a different question.
    """
    if not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    from .signup_policy import verification_required

    if not verification_required():
        return True  # the instance does not ask for verification
    profile = getattr(user, "profile", None)
    return bool(profile and profile.is_verified)


#: The routes an unactivated account still reaches, by URL name: everything it
#: needs to *become* activated (read the account, fix a typo'd address, verify,
#: resend), to leave (sign out, sign out everywhere, delete or export its data),
#: and to answer an invitation — joining what someone asked you into is the one
#: thing verification never gates (see ``InviteAcceptView``).
VERIFICATION_EXEMPT_URL_NAMES = frozenset(
    {
        "auth-me",
        "auth-me-no-slash",
        "auth-logout",
        "auth-logout-no-slash",
        "account",
        "account-no-slash",
        "account-export",
        "account-export-no-slash",
        "account-delete-request",
        "account-delete-request-no-slash",
        "sessions-revoke",
        "sessions-revoke-no-slash",
        "email-change",
        "email-change-no-slash",
        "email-verify",
        "email-verify-no-slash",
        "email-resend",
        "email-resend-no-slash",
        "invite-accept",
        "invite-accept-no-slash",
    }
)


class VerifiedEmailRequired(BasePermission):
    """The API's default gate: an activated account, when the instance asks.

    When ``signup.verify_email`` is on or sign-up is in domain mode, an account
    that has not proved its address reaches only the routes in
    :data:`VERIFICATION_EXEMPT_URL_NAMES` until it does. Anonymous requests are
    left to ``IsAuthenticated`` (and ``AllowAny`` views never reach this, since
    they replace the default classes). With verification off this is inert —
    :func:`user_email_verified` is then true for every account.
    """

    message = UNVERIFIED_MESSAGE

    def has_permission(self, request, view) -> bool:
        from django.conf import settings

        if not getattr(settings, "API_REQUIRE_VERIFIED_EMAIL", True):
            return True
        user = request.user
        if not user or not user.is_authenticated:
            return True  # IsAuthenticated answers for the anonymous
        if getattr(getattr(request, "_request", request), "demo", None) is not None:
            return True  # the public demo's viewer is a fixture, not a sign-up
        if user_email_verified(user):
            return True
        match = getattr(request, "resolver_match", None)
        return bool(match and match.url_name in VERIFICATION_EXEMPT_URL_NAMES)


def require_verified_email(user: UserOrAnon) -> None:
    """Refuse the caller unless their account is activated.

    Guards the endpoints that stand up an organization or invite someone into
    one. Mycelium mails strangers on a lab's behalf, so an account that has not
    proved it owns its own inbox does not get to originate that mail — and a lab
    whose founding address bounces is a lab nobody can be added to.
    """
    if not user_email_verified(user):
        raise PermissionDenied(UNVERIFIED_MESSAGE)


def user_can_invite_to_department(user: UserOrAnon, department: Department) -> bool:
    """A department's owner or an admin may invite people to it.

    The lab sibling of :func:`user_can_invite_to_lab`, named separately so the
    invitation views read the same for both org types even though the underlying
    authority differs (a lab also lets its lead PI invite).
    """
    return caps.has_capability(user, department, caps.INVITES_ISSUE)


def user_owns_lab(user: UserOrAnon, lab: Lab) -> bool:
    """Whether ``user`` holds ``lab``'s owner role — the one authority that may
    put the lab under a department, because doing so shows the department's heads
    every project and every member of the lab."""
    if not user.is_authenticated:
        return False
    return LabMembership.objects.filter(
        user=user, lab=lab, role=LabMembership.Role.OWNER
    ).exists()
