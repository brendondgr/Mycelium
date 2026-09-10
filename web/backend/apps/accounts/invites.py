"""Inviting people into a lab or a department.

Two ways in, one model (:class:`~apps.accounts.models.OrgInvite`):

* **Email.** The creator names one address. A link goes to that mailbox and only
  that address can spend it — checked again at redemption, so forwarding the mail
  does not hand the invitation on. This is the one to reach for when it matters
  who joins.
* **Link.** The creator gets a URL to paste wherever they like. Nothing binds it
  to a person, so it is bounded the other way: a maximum number of accounts and
  an expiry (a week unless the creator says otherwise).

Redemption always goes through the membership services in
:mod:`apps.accounts.services`, never straight to the membership table, because a
seat is what makes a member entitled — a row written behind billing's back is a
member the product then refuses to serve.

Who may create one: the same authority that already manages the org's roster,
*and* an activated account. Mycelium mails strangers on the creator's behalf, so
an account that has not answered its own mailbox does not get to originate that
mail — see :func:`apps.accounts.permissions.require_verified_email`.
"""

from __future__ import annotations

import logging
import secrets
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.core.mail import app_url, send_email

from .models import (
    Department,
    DeptMembership,
    Lab,
    LabMembership,
    OrgInvite,
    OrgInviteRedemption,
)
from .services import add_dept_member, add_lab_member, record_audit_event

logger = logging.getLogger(__name__)

#: Where an invite link lands in the app.
JOIN_PATH = "/join"

#: How long a link lives when the creator does not choose.
DEFAULT_EXPIRY_DAYS = 7
#: The window a creator may choose from. A day is the shortest useful life; past a
#: quarter the link has outlived any conversation that produced it.
MIN_EXPIRY_DAYS = 1
MAX_EXPIRY_DAYS = 90

#: How many accounts a share link admits when the creator does not choose, and the
#: ceiling on what they may ask for. The cap is not a licence check — seats still
#: enforce the tier — it is what stops a leaked link becoming an open door.
DEFAULT_MAX_USES = 25
MAX_MAX_USES = 500

#: Human phrasing of the default window, for the email body.
_EXPIRES_IN_FALLBACK = "a week"


class InviteError(Exception):
    """An invite that cannot be spent, with a reason a stranger may safely read."""

    #: Machine-readable reason, for the join page to branch on.
    reason = "invalid"

    def __init__(self, message: str, reason: str = "invalid") -> None:
        super().__init__(message)
        self.reason = reason


def new_token() -> str:
    """A fresh URL-safe invite token (about 256 bits)."""
    return secrets.token_urlsafe(32)


def invite_url(invite: OrgInvite) -> str:
    """The absolute link a recipient follows."""
    return app_url(f"{JOIN_PATH}/{invite.token}")


# --------------------------------------------------------------------------- #
# Creating
# --------------------------------------------------------------------------- #


def create_invite(
    *,
    creator: User,
    lab: Lab | None = None,
    department: Department | None = None,
    kind: str,
    email: str = "",
    role: str = OrgInvite.Role.MEMBER,
    max_uses: int | None = None,
    expires_in_days: int | None = None,
    message: str = "",
    send: bool = True,
) -> OrgInvite:
    """Create one invitation and, for an email invite, mail it.

    Raises DRF ``ValidationError`` on anything the creator can fix: a missing or
    malformed address, a role the org does not have, a budget or window outside
    what is allowed, or an address that is already a member.
    """
    if (lab is None) == (department is None):
        raise ValueError("Pass exactly one of lab / department.")

    kind = str(kind or "").strip().lower()
    if kind not in OrgInvite.Kind.values:
        raise ValidationError({"kind": ["Choose an email invite or a share link."]})

    role = _clean_role(role)
    address = str(email or "").strip().lower()

    if kind == OrgInvite.Kind.EMAIL:
        if not address:
            raise ValidationError({"email": ["An email address is required."]})
        _refuse_existing_member(address, lab=lab, department=department)
        # One address, one seat: a personal invitation is not a share link with a
        # name attached, and letting it be spent twice would erase the binding.
        uses = 1
    else:
        address = ""
        uses = _clean_max_uses(max_uses)

    expires_at = timezone.now() + timedelta(days=_clean_expiry_days(expires_in_days))

    invite = _create_with_unique_token(
        lab=lab,
        department=department,
        kind=kind,
        role=role,
        email=address,
        message=str(message or "").strip()[:500],
        created_by=creator,
        max_uses=uses,
        expires_at=expires_at,
    )

    record_audit_event(
        actor=creator,
        action="org.invite.create",
        target_type="org_invite",
        target_id=str(invite.id),
        metadata={
            "org_kind": invite.org_kind,
            "org_id": str(invite.lab_id or invite.department_id),
            "kind": kind,
            "role": role,
            "max_uses": uses,
        },
    )

    if send and kind == OrgInvite.Kind.EMAIL:
        deliver_invite(invite)
    return invite


def _create_with_unique_token(**fields) -> OrgInvite:
    """Insert the row, retrying the (vanishingly unlikely) token collision."""
    for _ in range(5):
        try:
            with transaction.atomic():
                return OrgInvite.objects.create(token=new_token(), **fields)
        except IntegrityError:
            continue
    raise RuntimeError("Could not allocate an invite token.")


def deliver_invite(invite: OrgInvite) -> bool:
    """Mail an email invite to the address it is bound to."""
    if invite.kind != OrgInvite.Kind.EMAIL or not invite.email:
        return False
    template = (
        "lab_invitation" if invite.org_kind == "lab" else "department_invitation"
    )
    inviter = invite.created_by
    outcome = send_email(
        template,
        to=invite.email,
        context={
            "recipient_name": "",
            "inviter_name": _display(inviter),
            "lab_name": invite.org_name,
            "department_name": invite.org_name,
            "invitation_url": invite_url(invite),
            "expires_in": _expires_in(invite),
            "message": invite.message,
        },
        fail_silently=True,
    )
    if not outcome.sent:
        logger.error("Invitation email not accepted for invite %s", invite.id)
    return bool(outcome.sent)


def revoke_invite(invite: OrgInvite, *, actor: User) -> OrgInvite:
    """Withdraw an invitation. Idempotent — re-revoking keeps the first timestamp."""
    if invite.revoked_at is None:
        invite.revoked_at = timezone.now()
        invite.save(update_fields=["revoked_at"])
        record_audit_event(
            actor=actor,
            action="org.invite.revoke",
            target_type="org_invite",
            target_id=str(invite.id),
            metadata={"org_kind": invite.org_kind},
        )
    return invite


# --------------------------------------------------------------------------- #
# Reading & redeeming
# --------------------------------------------------------------------------- #


def find_invite(token: str) -> OrgInvite:
    """Look up a live invite by token, or raise :class:`InviteError`.

    Every refusal — unknown token, revoked, expired, spent — is a distinct reason
    so the join page can say something true. None of them leak anything the token
    holder does not already have.
    """
    value = str(token or "").strip()
    invite = (
        OrgInvite.objects.select_related("lab", "department", "created_by")
        .filter(token=value)
        .first()
        if value
        else None
    )
    if invite is None:
        raise InviteError("This invitation link is not valid.", "invalid")
    if invite.revoked_at is not None:
        raise InviteError("This invitation has been withdrawn.", "revoked")
    if invite.expires_at <= timezone.now():
        raise InviteError("This invitation has expired.", "expired")
    if invite.used_count >= invite.max_uses:
        raise InviteError("This invitation has already been used.", "exhausted")
    if invite.org is None:
        raise InviteError("This invitation link is not valid.", "invalid")
    return invite


def check_email_matches(invite: OrgInvite, email: str) -> None:
    """Refuse an email invite presented by any address but the invited one."""
    if invite.kind != OrgInvite.Kind.EMAIL:
        return
    if str(email or "").strip().lower() != invite.email:
        raise InviteError(
            f"This invitation was sent to {invite.email}. "
            "Sign in with that address, or ask for an invitation to yours.",
            "wrong_email",
        )


@transaction.atomic
def redeem(invite: OrgInvite, user: User) -> OrgInvite:
    """Add ``user`` to the invite's org and spend one use.

    Idempotent per person: someone who follows their own link twice keeps the one
    membership and the budget only moves once. The membership goes through the
    seat-syncing services, so a roster already at its tier ceiling refuses the
    whole redemption rather than admitting an unseated member.
    """
    check_email_matches(invite, user.email)

    # Re-read under a row lock: two people finishing sign-up on the same link at
    # the same moment must not both see the last remaining use.
    locked = OrgInvite.objects.select_for_update().get(pk=invite.pk)
    if locked.revoked_at is not None:
        raise InviteError("This invitation has been withdrawn.", "revoked")
    if locked.expires_at <= timezone.now():
        raise InviteError("This invitation has expired.", "expired")

    already = OrgInviteRedemption.objects.filter(invite=locked, user=user).exists()
    if not already and locked.used_count >= locked.max_uses:
        raise InviteError("This invitation has already been used.", "exhausted")

    if locked.lab_id is not None:
        _join_lab(locked, user)
    else:
        _join_department(locked, user)

    if not already:
        OrgInviteRedemption.objects.create(invite=locked, user=user)
        locked.used_count += 1
        locked.save(update_fields=["used_count"])

    record_audit_event(
        actor=user,
        action="org.invite.redeem",
        target_type="org_invite",
        target_id=str(locked.id),
        metadata={
            "org_kind": locked.org_kind,
            "org_id": str(locked.lab_id or locked.department_id),
            "repeat": already,
        },
    )
    invite.used_count = locked.used_count
    return locked


def _join_lab(invite: OrgInvite, user: User) -> None:
    lab = invite.lab
    if LabMembership.objects.filter(lab=lab, user=user).exists():
        return
    add_lab_member(lab, user, role=invite.role, actor=invite.created_by)


def _join_department(invite: OrgInvite, user: User) -> None:
    department = invite.department
    if DeptMembership.objects.filter(department=department, user=user).exists():
        return
    add_dept_member(department, user, role=invite.role, actor=invite.created_by)


def redeem_token(token: str, user: User) -> OrgInvite:
    """:func:`find_invite` then :func:`redeem`, the pair every caller wants."""
    return redeem(find_invite(token), user)


# --------------------------------------------------------------------------- #
# Serialization
# --------------------------------------------------------------------------- #


def invite_payload(invite: OrgInvite) -> dict:
    """The manager's view of one invite, token included so a link stays copyable."""
    return {
        "id": str(invite.id),
        "kind": invite.kind,
        "role": invite.role,
        "email": invite.email,
        "message": invite.message,
        "url": invite_url(invite),
        "max_uses": invite.max_uses,
        "used_count": invite.used_count,
        "uses_left": invite.uses_left,
        "expires_at": invite.expires_at.isoformat(),
        "revoked_at": invite.revoked_at.isoformat() if invite.revoked_at else None,
        "is_live": is_live(invite),
        "created_at": invite.created_at.isoformat(),
        "created_by": _display(invite.created_by),
    }


def preview_payload(invite: OrgInvite) -> dict:
    """What an anonymous visitor holding the token is told about it.

    The bound address is shown because the holder was the one it was mailed to,
    and a join page that will not say which mailbox it wants is a dead end.
    """
    return {
        "org_kind": invite.org_kind,
        "org_name": invite.org_name,
        "role": invite.role,
        "kind": invite.kind,
        "email": invite.email,
        "message": invite.message,
        "invited_by": _display(invite.created_by),
        "expires_at": invite.expires_at.isoformat(),
    }


def is_live(invite: OrgInvite) -> bool:
    return (
        invite.revoked_at is None
        and invite.expires_at > timezone.now()
        and invite.used_count < invite.max_uses
    )


# --------------------------------------------------------------------------- #
# Input cleaning
# --------------------------------------------------------------------------- #


def _clean_role(role: str) -> str:
    value = str(role or "").strip().lower()
    if value not in OrgInvite.Role.values:
        return OrgInvite.Role.MEMBER
    if value == OrgInvite.Role.OWNER:
        # Ownership is transferred, not handed out to whoever clicks a link.
        return OrgInvite.Role.ADMIN
    return value


def _clean_max_uses(value: int | None) -> int:
    if value in (None, ""):
        return DEFAULT_MAX_USES
    try:
        uses = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            {"max_uses": ["Give a whole number of accounts."]}
        ) from exc
    if uses < 1 or uses > MAX_MAX_USES:
        raise ValidationError(
            {"max_uses": [f"Choose between 1 and {MAX_MAX_USES} accounts."]}
        )
    return uses


def _clean_expiry_days(value: int | None) -> int:
    if value in (None, ""):
        return DEFAULT_EXPIRY_DAYS
    try:
        days = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError({"expires_in_days": ["Give a number of days."]}) from exc
    if days < MIN_EXPIRY_DAYS or days > MAX_EXPIRY_DAYS:
        raise ValidationError(
            {
                "expires_in_days": [
                    f"Choose between {MIN_EXPIRY_DAYS} and {MAX_EXPIRY_DAYS} days."
                ]
            }
        )
    return days


def _refuse_existing_member(
    address: str, *, lab: Lab | None, department: Department | None
) -> None:
    """Do not invite someone who is already in — say so instead of mailing them."""
    user = User.objects.filter(email__iexact=address).first()
    if user is None:
        return
    if lab is not None and LabMembership.objects.filter(lab=lab, user=user).exists():
        raise ValidationError(
            {"email": ["That person is already a member of this lab."]}
        )
    if (
        department is not None
        and DeptMembership.objects.filter(department=department, user=user).exists()
    ):
        raise ValidationError(
            {"email": ["That person is already a member of this department."]}
        )


def _expires_in(invite: OrgInvite) -> str:
    remaining = invite.expires_at - timezone.now()
    days = max(int(remaining.total_seconds() // 86400), 0)
    if days >= 1:
        return "1 day" if days == 1 else f"{days} days"
    hours = max(int(remaining.total_seconds() // 3600), 1)
    return "1 hour" if hours == 1 else f"{hours} hours"


def _display(user: User | None) -> str:
    if user is None:
        return ""
    from apps.core.people import display_name

    return display_name(user)
