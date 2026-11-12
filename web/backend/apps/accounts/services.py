from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from rest_framework.serializers import ValidationError

from .models import (
    AuditEvent,
    Department,
    DeptMembership,
    Lab,
    LabInvitation,
    LabMembership,
)


def record_audit_event(
    *,
    actor: User | None,
    action: str,
    target_type: str,
    target_id: str = "",
    metadata: dict | None = None,
) -> AuditEvent:
    return AuditEvent.objects.create(
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
        metadata=metadata or {},
    )


def is_onboarding_complete(user: User) -> bool:
    """True once the user has finished profile onboarding.

    The intake confirm step (``POST /api/auth/intake/confirm/``) persists
    ``Profile.interests`` with a required, non-empty ``areas`` list. Its presence
    is the canonical "onboarded" marker: a freshly registered user starts with an
    empty interests dict and only gains ``areas`` after completing onboarding.
    """
    profile = getattr(user, "profile", None)
    if profile is None:
        return False
    return bool((profile.interests or {}).get("areas"))


def get_lab_for_user(user: User, slug: str) -> Lab | None:
    """The lab ``slug`` names, if ``user`` is a member of it — otherwise ``None``.

    Membership is the whole rule. A superuser used to get any lab by slug here,
    which is what let an operator account open a workspace it had never joined;
    platform administration belongs to ``apps.adminpanel`` and Django admin, not
    to the workspace API. See the note at the top of ``apps.accounts.permissions``.
    """
    return (
        Lab.objects.filter(slug=slug, memberships__user=user)
        .distinct()
        .first()
    )


def effective_member_ids(department: Department) -> set[int]:
    """Derive a department's effective membership (briefing §4, decision D4).

    The set is direct department members unioned with the members of every lab
    that belongs to the department, deduplicated by user. It is *computed*, not
    stored as redundant rows — a user in two labs of the same department counts
    once. Seats are issued against this set and department-wide routing uses it.
    """
    direct = DeptMembership.objects.filter(department=department).values_list(
        "user_id", flat=True
    )
    via_labs = LabMembership.objects.filter(
        lab__department=department
    ).values_list("user_id", flat=True)
    return set(direct) | set(via_labs)


def plan_member_ids(department: Department) -> set[int]:
    """The users the department **plan** covers — direct members ∪ included labs.

    The billing-only twin of :func:`effective_member_ids`: same direct-department
    members, but a lab-under-department member is only counted when the department
    head has opted that lab into the plan (``Lab.department_plan_included``).
    Inclusion is a billing choice, so this — not ``effective_member_ids`` — is what
    the seat-issuing paths read; visibility/access keep using the full effective set.
    """
    direct = DeptMembership.objects.filter(department=department).values_list(
        "user_id", flat=True
    )
    via_included_labs = LabMembership.objects.filter(
        lab__department=department, lab__department_plan_included=True
    ).values_list("user_id", flat=True)
    return set(direct) | set(via_included_labs)


def effective_members(department: Department) -> QuerySet[User]:
    """Return the users in a department's effective membership set."""
    return User.objects.filter(id__in=effective_member_ids(department))


def effective_member_count(department: Department) -> int:
    """Number of distinct effective members — the basis for Canopy seat sizing."""
    return len(effective_member_ids(department))


def lab_lead_count(lab: Lab) -> int:
    """Count PIs (lead memberships) of a lab — checked against per-tier PI caps."""
    return LabMembership.objects.filter(lab=lab, is_lead=True).count()


# -- Lab invitations -----------------------------------------------------------


def invite_to_lab(
    *,
    lab: Lab,
    inviter: User,
    identifier: str,
    role: str = LabMembership.Role.MEMBER,
) -> LabInvitation:
    """Create a pending invitation from an email or username.

    An email is matched to an existing account when possible, otherwise kept as
    a pending email invite (claimed on signup). A username must match an existing
    account. Raises DRF ``ValidationError`` for empty input, an unknown username,
    an existing member, or a duplicate pending invite.
    """
    identifier = (identifier or "").strip()
    if not identifier:
        raise ValidationError({"identifier": ["An email or username is required."]})

    invitee: User | None = None
    invited_email = ""
    invited_username = ""

    if "@" in identifier:
        invited_email = identifier.lower()
        invitee = User.objects.filter(email__iexact=invited_email).first()
    else:
        invited_username = identifier
        invitee = User.objects.filter(username__iexact=identifier).first()
        if invitee is None:
            raise ValidationError(
                {
                    "identifier": [
                        "No Mycelium user found with that username. Use an email "
                        "address to invite someone without an account.",
                    ]
                }
            )

    if invitee is not None and LabMembership.objects.filter(
        lab=lab, user=invitee
    ).exists():
        raise ValidationError(
            {"identifier": ["That person is already a member of this lab."]}
        )

    pending = LabInvitation.objects.filter(
        lab=lab, status=LabInvitation.Status.PENDING
    )
    if invitee is not None:
        pending = pending.filter(invitee=invitee)
    else:
        pending = pending.filter(invited_email=invited_email, invitee__isnull=True)
    if pending.exists():
        raise ValidationError(
            {"identifier": ["There is already a pending invitation for that person."]}
        )

    if role not in dict(LabMembership.Role.choices):
        role = LabMembership.Role.MEMBER

    invitation = LabInvitation.objects.create(
        lab=lab,
        inviter=inviter,
        invitee=invitee,
        invited_email=invited_email,
        invited_username=invited_username,
        role=role,
    )
    record_audit_event(
        actor=inviter,
        action="lab.invite",
        target_type="lab_invitation",
        target_id=str(invitation.id),
        metadata={
            "lab_id": str(lab.id),
            "role": role,
            "invitee_id": invitee.id if invitee else None,
            "invited_email": invited_email,
        },
    )
    return invitation


def ensure_lab_has_room(lab: Lab, user: User) -> None:
    """Refuse a *new* member past the lab's member limit (its staff override, else
    ``limits.lab_members``; unlimited by default).

    An existing member re-joining is never refused. Under subscriptions an active
    plan's seat ceiling still applies on top, through ``seat_sync``.
    """
    from apps.billing.entitlements import lab_member_cap

    cap = lab_member_cap(lab)
    if cap is None or LabMembership.objects.filter(lab=lab, user=user).exists():
        return
    if LabMembership.objects.filter(lab=lab).count() >= cap:
        raise ValidationError(
            {
                "detail": [
                    f"This lab is full: it already has {cap} members, the most "
                    "allowed. An administrator can raise the lab's limit "
                    "(limits.lab_members)."
                ]
            }
        )


@transaction.atomic
def accept_invitation(invitation: LabInvitation, user: User) -> LabMembership:
    """Accept: add the lab membership, grant a seat, and mark the invite accepted.

    Granting the seat in the same atomic block is what makes a paying lab's invited
    members resolve to LAB instead of FREE (the seat is entitlement, A6). A lab with
    no active subscription (a Free lab) has nothing to seat, so ``grant_seat_...``
    returns ``None`` and the membership stands on its own. Exceeding the tier's
    member ceiling refuses the whole acceptance rather than silently over-seating.
    """
    # Imported here (not at module top) to avoid an accounts↔billing import cycle.
    from apps.billing.seat_sync import sync_lab_member
    from apps.billing.seats import SeatCeilingExceeded

    ensure_lab_has_room(invitation.lab, user)
    membership, _ = LabMembership.objects.get_or_create(
        lab=invitation.lab,
        user=user,
        defaults={"role": invitation.role},
    )
    try:
        # Seats on the correct paying scope: the lab's plan, or its department's plan
        # when the lab belongs to an active department (decision B2 / rule 2).
        sync_lab_member(user, invitation.lab)
    except SeatCeilingExceeded as exc:
        raise ValidationError({"detail": [str(exc)]}) from exc
    _close_invitation(
        invitation, user, LabInvitation.Status.ACCEPTED, "lab.invitation.accept"
    )
    return membership


def decline_invitation(
    invitation: LabInvitation, user: User, *, ignore: bool = False
) -> None:
    """Reject (definitive decline) or ignore (silent dismiss) an invitation."""
    if ignore:
        _close_invitation(
            invitation, user, LabInvitation.Status.IGNORED, "lab.invitation.ignore"
        )
    else:
        _close_invitation(
            invitation, user, LabInvitation.Status.REJECTED, "lab.invitation.reject"
        )


def _close_invitation(
    invitation: LabInvitation, user: User, status: str, action: str
) -> None:
    invitation.status = status
    invitation.responded_at = timezone.now()
    invitation.save(update_fields=["status", "responded_at"])
    record_audit_event(
        actor=user,
        action=action,
        target_type="lab_invitation",
        target_id=str(invitation.id),
        metadata={"lab_id": str(invitation.lab_id)},
    )


def claim_pending_invitations(user: User) -> int:
    """Attach pending email invites to a freshly registered user (not auto-accept).

    Matches pending, unclaimed invites by email so the new user sees them in the
    notifications panel. Skips a lab where the user already has a pending invite
    to avoid colliding with the one-live-invite-per-lab constraint.
    """
    if not user.email:
        return 0
    claimed = 0
    invites = LabInvitation.objects.filter(
        status=LabInvitation.Status.PENDING,
        invitee__isnull=True,
        invited_email__iexact=user.email,
    )
    for invite in invites:
        if LabInvitation.objects.filter(
            lab=invite.lab, invitee=user, status=LabInvitation.Status.PENDING
        ).exists():
            continue
        invite.invitee = user
        invite.save(update_fields=["invitee"])
        claimed += 1
    return claimed


# -- Lab & department membership management (seat-synced) ----------------------
#
# Every mutation routes through the billing ``seat_sync`` service so a member's
# entitlement tracks their membership (rules 1 & 2). Removal is deferred: the seat
# stays ACTIVE (billed + entitled) until the billing tick revokes it at period end,
# and a member who is still *effective* through another lab/direct membership keeps
# their seat. Memberships are never re-parented silently — billing follows structure.


def add_lab_member(
    lab: Lab,
    user: User,
    *,
    role: str = LabMembership.Role.MEMBER,
    actor: User | None = None,
) -> LabMembership:
    """Add an existing user to a lab and seat them on the paying scope (rules 1/2)."""
    from apps.billing.seat_sync import sync_lab_member
    from apps.billing.seats import SeatCeilingExceeded

    if role not in dict(LabMembership.Role.choices):
        role = LabMembership.Role.MEMBER
    with transaction.atomic():
        ensure_lab_has_room(lab, user)
        membership, _ = LabMembership.objects.get_or_create(
            lab=lab, user=user, defaults={"role": role}
        )
        try:
            sync_lab_member(user, lab)
        except SeatCeilingExceeded as exc:
            raise ValidationError({"detail": [str(exc)]}) from exc
        record_audit_event(
            actor=actor or user,
            action="lab.member.add",
            target_type="lab",
            target_id=str(lab.id),
            metadata={"user_id": user.id, "role": role},
        )
    return membership


def set_lab_member_role(
    lab: Lab, user: User, role: str, *, actor: User | None = None
) -> LabMembership:
    """Change a lab member's permission role (owner/admin/member/viewer).

    Authority runs strictly downward — see ``permissions.LAB_ROLE_RANK``. The
    check lives here rather than only in the view so that every caller inherits
    it; a service that quietly skips the rule is how an escalation hole reopens.

    ``actor=None`` is a trusted internal call (sign-up provisioning, invite
    redemption, ownership transfer) and is not rank-checked. Those paths decide
    authority themselves before they get here.
    """
    from .permissions import user_can_grant_lab_role, user_outranks_lab_member

    if role not in dict(LabMembership.Role.choices):
        raise ValidationError({"role": ["Unknown role."]})
    membership = LabMembership.objects.filter(lab=lab, user=user).first()
    if membership is None:
        raise ValidationError({"detail": ["That user is not a member of this lab."]})

    if actor is not None:
        refused = None
        if not user_outranks_lab_member(actor, lab, user):
            refused = "You cannot change the role of someone at or above your own."
        elif not user_can_grant_lab_role(actor, lab, role):
            refused = (
                "Only the lab's PI can grant that role."
                if role == LabMembership.Role.ADMIN
                else "Ownership is handed over by transfer, not by a role change."
            )
        if refused is not None:
            record_audit_event(
                actor=actor,
                action="lab.member.role.refused",
                target_type="lab",
                target_id=str(lab.id),
                metadata={"user_id": user.id, "role": role},
            )
            raise PermissionDenied(refused)

    membership.role = role
    membership.save(update_fields=["role"])
    record_audit_event(
        actor=actor,
        action="lab.member.role",
        target_type="lab",
        target_id=str(lab.id),
        metadata={"user_id": user.id, "role": role},
    )
    return membership


@transaction.atomic
def transfer_lab_ownership(lab: Lab, new_owner: User, *, actor: User) -> LabMembership:
    """Hand ``lab`` to ``new_owner``; ``actor`` steps down to admin.

    The case this exists for: the person who created the account and stood the
    lab up is often not the person who runs it. Ownership moves in one step
    rather than by two role edits, because the in-between state — two owners, or
    none — is one nobody should be able to leave a lab sitting in.

    Both marks of authority move together. ``role=OWNER`` is what the permission
    checks read; ``is_lead=True`` is the PI badge the roster and the lab profile
    read. Splitting them is how a lab ends up with an owner who is not its PI,
    so every other lead is cleared and the lab keeps exactly one.

    **Irreversible by design**, and not by a flag: the outgoing owner becomes an
    admin, and an admin cannot grant ownership (see ``permissions.LAB_ROLE_RANK``).
    Only the new owner can hand it back.

    Raises ``ValidationError`` if the target is not a member or has not verified
    their address — they are about to hold the lab — and ``PermissionDenied`` if
    the actor is not its current owner.
    """
    from .permissions import LAB_ROLE_RANK

    current = LabMembership.objects.filter(lab=lab, user=actor).first()
    if current is None or current.role != LabMembership.Role.OWNER:
        raise PermissionDenied("Only the lab's owner can transfer it.")
    if new_owner == actor:
        raise ValidationError({"username": ["They already own this lab."]})

    incoming = LabMembership.objects.filter(lab=lab, user=new_owner).first()
    if incoming is None:
        raise ValidationError(
            {"username": ["Add them to the lab before handing it over."]}
        )
    from .permissions import user_email_verified

    if not user_email_verified(new_owner):
        raise ValidationError(
            {
                "username": [
                    "They need to verify their email before they can own a lab."
                ]
            }
        )

    # Exactly one lead, exactly one owner, and the old owner left as an admin
    # rather than removed — handing the lab over is not leaving it.
    LabMembership.objects.filter(lab=lab, is_lead=True).exclude(
        pk=incoming.pk
    ).update(is_lead=False)
    incoming.role = LabMembership.Role.OWNER
    incoming.is_lead = True
    incoming.save(update_fields=["role", "is_lead"])
    current.role = LabMembership.Role.ADMIN
    current.is_lead = False
    current.save(update_fields=["role", "is_lead"])

    record_audit_event(
        actor=actor,
        action="lab.ownership.transfer",
        target_type="lab",
        target_id=str(lab.id),
        metadata={
            "from_user_id": actor.id,
            "to_user_id": new_owner.id,
            "from_role_now": LabMembership.Role.ADMIN,
            "rank_granted": LAB_ROLE_RANK[LabMembership.Role.OWNER],
        },
    )
    return incoming


def remove_lab_member(lab: Lab, user: User, *, actor: User | None = None) -> None:
    """Remove a lab member; defer their seat unless they remain effective (L3)."""
    from apps.billing.seat_sync import paying_scope_for_lab
    from apps.billing.seats import schedule_seat_removal

    with transaction.atomic():
        kind, subscription = paying_scope_for_lab(lab)
        LabMembership.objects.filter(lab=lab, user=user).delete()
        if subscription is not None:
            # A department-paid member who is still effective (another lab under the
            # department, or a direct dept membership) keeps their seat.
            if kind == "department":
                if user.id not in effective_member_ids(lab.department):
                    schedule_seat_removal(subscription, user)
            else:
                schedule_seat_removal(subscription, user)
        record_audit_event(
            actor=actor,
            action="lab.member.remove",
            target_type="lab",
            target_id=str(lab.id),
            metadata={"user_id": user.id},
        )


def add_dept_member(
    department: Department,
    user: User,
    *,
    role: str = DeptMembership.Role.MEMBER,
    actor: User | None = None,
) -> DeptMembership:
    """Add a direct department member and seat them on the department plan (rule 2)."""
    from apps.billing.seat_sync import sync_dept_member

    if role not in dict(DeptMembership.Role.choices):
        role = DeptMembership.Role.MEMBER
    with transaction.atomic():
        membership, _ = DeptMembership.objects.get_or_create(
            department=department, user=user, defaults={"role": role}
        )
        sync_dept_member(user, department)
        record_audit_event(
            actor=actor or user,
            action="dept.member.add",
            target_type="department",
            target_id=str(department.id),
            metadata={"user_id": user.id, "role": role},
        )
    return membership


def remove_dept_member(
    department: Department, user: User, *, actor: User | None = None
) -> None:
    """Remove a direct dept member; defer their seat unless still effective (L3)."""
    from apps.billing.seats import (
        _active_subscription_for_department,
        schedule_seat_removal,
    )

    with transaction.atomic():
        DeptMembership.objects.filter(department=department, user=user).delete()
        if user.id not in effective_member_ids(department):
            schedule_seat_removal(
                _active_subscription_for_department(department), user
            )
        record_audit_event(
            actor=actor,
            action="dept.member.remove",
            target_type="department",
            target_id=str(department.id),
            metadata={"user_id": user.id},
        )


def set_dept_member_role(
    department: Department, user: User, role: str, *, actor: User
) -> DeptMembership:
    """Change a direct department member's role, strictly downward.

    The department twin of :func:`set_lab_member_role` (see
    ``permissions.DEPT_ROLE_RANK``): an actor re-roles only someone below them,
    and grants only a role below their own. Ownership is never set here — it
    moves with the department head, by :func:`transfer_department_ownership`.
    """
    from .permissions import user_can_grant_dept_role, user_outranks_dept_member

    if role not in dict(DeptMembership.Role.choices):
        raise ValidationError({"role": ["Unknown role."]})
    membership = DeptMembership.objects.filter(
        department=department, user=user
    ).first()
    if membership is None:
        raise ValidationError(
            {"detail": ["That user is not a direct member of this department."]}
        )

    refused = None
    if not user_outranks_dept_member(actor, department, user):
        refused = "You cannot change the role of someone at or above your own."
    elif not user_can_grant_dept_role(actor, department, role):
        refused = (
            "Only the department head can grant that role."
            if role == DeptMembership.Role.ADMIN
            else "The department is handed over by transfer, not by a role change."
        )
    if refused is not None:
        record_audit_event(
            actor=actor,
            action="dept.member.role.refused",
            target_type="department",
            target_id=str(department.id),
            metadata={"user_id": user.id, "role": role},
        )
        raise PermissionDenied(refused)

    membership.role = role
    membership.save(update_fields=["role"])
    record_audit_event(
        actor=actor,
        action="dept.member.role",
        target_type="department",
        target_id=str(department.id),
        metadata={"user_id": user.id, "role": role},
    )
    return membership


@transaction.atomic
def transfer_department_ownership(
    department: Department, new_head: User, *, actor: User
) -> DeptMembership:
    """Hand ``department`` to ``new_head``; ``actor`` steps down to admin.

    The department head is ``Department.owner``, a foreign key, and also an
    OWNER ``DeptMembership`` row kept in step with it. Both move here together,
    with the outgoing head's row set to admin — handing a department over is not
    leaving it, the same answer the lab transfer gives. Any other OWNER row is
    lowered to admin so the department keeps exactly one.

    Irreversible from the outgoing side: an admin cannot grant ownership.

    Raises ``PermissionDenied`` unless the actor is the head, and
    ``ValidationError`` unless the target is a direct, verified member.
    """
    from .permissions import DEPT_ROLE_RANK, user_email_verified

    department = Department.objects.select_for_update().get(pk=department.pk)
    if department.owner_id != actor.id:
        raise PermissionDenied("Only the department head can transfer it.")
    if new_head == actor:
        raise ValidationError({"username": ["They already run this department."]})

    incoming = DeptMembership.objects.filter(
        department=department, user=new_head
    ).first()
    if incoming is None:
        raise ValidationError(
            {
                "username": [
                    "Add them to the department directly before handing it over."
                ]
            }
        )
    if not user_email_verified(new_head):
        raise ValidationError(
            {
                "username": [
                    "They need to verify their email before they can run a "
                    "department."
                ]
            }
        )

    DeptMembership.objects.filter(
        department=department, role=DeptMembership.Role.OWNER
    ).exclude(pk=incoming.pk).update(role=DeptMembership.Role.ADMIN)
    outgoing, created = DeptMembership.objects.get_or_create(
        department=department,
        user=actor,
        defaults={"role": DeptMembership.Role.ADMIN},
    )
    if not created and outgoing.role != DeptMembership.Role.ADMIN:
        outgoing.role = DeptMembership.Role.ADMIN
        outgoing.save(update_fields=["role"])
    incoming.role = DeptMembership.Role.OWNER
    incoming.save(update_fields=["role"])
    department.owner = new_head
    department.save(update_fields=["owner", "updated_at"])

    record_audit_event(
        actor=actor,
        action="department.ownership.transfer",
        target_type="department",
        target_id=str(department.id),
        metadata={
            "from_user_id": actor.id,
            "to_user_id": new_head.id,
            "from_role_now": DeptMembership.Role.ADMIN,
            "rank_granted": DEPT_ROLE_RANK[DeptMembership.Role.OWNER],
        },
    )
    return incoming


def attach_existing_lab_to_department(
    department: Department, lab: Lab, *, actor: User | None = None
) -> Lab:
    """Attach an unowned lab to a department, re-seating its members (B2)."""
    from apps.billing.services import attach_lab_to_department

    if lab.department_id and lab.department_id != department.id:
        raise ValidationError({"detail": ["That lab already belongs to a department."]})
    with transaction.atomic():
        attach_lab_to_department(lab, department)
        record_audit_event(
            actor=actor,
            action="dept.lab.attach",
            target_type="department",
            target_id=str(department.id),
            metadata={"lab_id": str(lab.id)},
        )
    return lab


def create_lab_in_department(
    department: Department, name: str, owner: User, *, actor: User | None = None
) -> Lab:
    """Create a new lab under a department (owner is its PI), re-seating on the plan."""
    from apps.billing.services import attach_lab_to_department, create_lab_workspace

    with transaction.atomic():
        result = create_lab_workspace(owner, name)
        attach_lab_to_department(result.lab, department)
        record_audit_event(
            actor=actor,
            action="dept.lab.create",
            target_type="department",
            target_id=str(department.id),
            metadata={"lab_id": str(result.lab.id), "name": name},
        )
    return result.lab


def detach_lab_from_department(
    department: Department, lab: Lab, *, actor: User | None = None
) -> Lab:
    """Detach a lab from a dept; defer the dept seats of members it alone covered."""
    from apps.billing.seats import (
        _active_subscription_for_department,
        schedule_seat_removal,
    )

    if lab.department_id != department.id:
        raise ValidationError({"detail": ["That lab is not in this department."]})
    with transaction.atomic():
        lab.department = None
        # Leaving the department also drops the lab out of its plan; reset the flag
        # so a future re-attach starts opt-out again.
        lab.department_plan_included = False
        lab.save(
            update_fields=["department", "department_plan_included", "updated_at"]
        )
        dept_sub = _active_subscription_for_department(department)
        if dept_sub is not None:
            remaining = plan_member_ids(department)  # recomputed after detach
            for membership in LabMembership.objects.filter(lab=lab).select_related(
                "user"
            ):
                if membership.user_id not in remaining:
                    schedule_seat_removal(dept_sub, membership.user)
        record_audit_event(
            actor=actor,
            action="dept.lab.detach",
            target_type="department",
            target_id=str(department.id),
            metadata={"lab_id": str(lab.id)},
        )
    return lab


def set_lab_department_inclusion(
    department: Department, lab: Lab, included: bool, *, actor: User | None = None
) -> Lab:
    """Include/exclude one of a department's labs in its plan (dept head choice).

    Thin orchestration around :func:`apps.billing.services.set_lab_plan_inclusion`
    (which owns the seat lifecycle), adding the membership guard + audit — mirroring
    :func:`attach_existing_lab_to_department` / :func:`detach_lab_from_department`.
    """
    from apps.billing.services import set_lab_plan_inclusion

    if lab.department_id != department.id:
        raise ValidationError({"detail": ["That lab is not in this department."]})
    with transaction.atomic():
        set_lab_plan_inclusion(lab, included)
        record_audit_event(
            actor=actor,
            action="dept.lab.plan_inclusion",
            target_type="department",
            target_id=str(department.id),
            metadata={"lab_id": str(lab.id), "included": included},
        )
    return lab


def cancel_invitation(
    invitation: LabInvitation, *, actor: User | None = None
) -> LabInvitation:
    """Withdraw a pending invitation the manager sent (the unused CANCELLED status)."""
    if invitation.status != LabInvitation.Status.PENDING:
        raise ValidationError({"detail": ["That invitation is no longer pending."]})
    invitation.status = LabInvitation.Status.CANCELLED
    invitation.responded_at = timezone.now()
    invitation.save(update_fields=["status", "responded_at"])
    record_audit_event(
        actor=actor,
        action="lab.invitation.cancel",
        target_type="lab_invitation",
        target_id=str(invitation.id),
        metadata={"lab_id": str(invitation.lab_id)},
    )
    return invitation


def department_members_payload(department: Department) -> list[dict]:
    """The department's effective-membership roster with role, source, and seat state.

    Direct department members are listed first, then members who belong only through a
    lab under the department. ``seat_status`` reflects each person's seat on the active
    department plan (``None`` while the plan is inactive).
    """
    from apps.billing.models import Seat
    from apps.billing.seats import _active_subscription_for_department
    from apps.core.people import display_name, initials

    sub = _active_subscription_for_department(department)
    seat_status: dict[int, str] = {}
    if sub is not None:
        seat_status = dict(
            Seat.objects.filter(subscription=sub).values_list("member_id", "status")
        )

    rows: dict[int, dict] = {}
    for membership in DeptMembership.objects.filter(
        department=department
    ).select_related("user"):
        rows[membership.user_id] = {
            "username": membership.user.username,
            "name": display_name(membership.user),
            "initials": initials(membership.user),
            "email": membership.user.email,
            "role": membership.role,
            "is_head": membership.user_id == department.owner_id,
            "source": "direct",
            "lab": None,
            "seat_status": seat_status.get(membership.user_id),
        }
    for lm in LabMembership.objects.filter(
        lab__department=department
    ).select_related("user", "lab"):
        if lm.user_id in rows:
            continue
        rows[lm.user_id] = {
            "username": lm.user.username,
            "name": display_name(lm.user),
            "initials": initials(lm.user),
            "email": lm.user.email,
            "role": lm.role,
            "is_head": lm.user_id == department.owner_id,
            "source": "lab",
            "lab": lm.lab.name,
            "seat_status": seat_status.get(lm.user_id),
        }
    return sorted(
        rows.values(), key=lambda r: (r["source"] != "direct", r["name"].lower())
    )


def department_labs_payload(department: Department) -> list[dict]:
    """The labs under a department with their member counts (for the labs card)."""
    from django.db.models import Count

    labs = department.labs.annotate(n=Count("memberships")).order_by("name")
    return [
        {
            "slug": lab.slug,
            "name": lab.name,
            "member_count": lab.n,
            "has_logo": lab.has_logo,
            "included_in_plan": lab.department_plan_included,
        }
        for lab in labs
    ]
