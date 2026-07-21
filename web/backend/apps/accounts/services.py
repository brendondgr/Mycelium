from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone
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
    if user.is_superuser:
        return Lab.objects.filter(slug=slug).first()

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
