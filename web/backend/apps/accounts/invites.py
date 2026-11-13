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

import hashlib
import logging
import re
import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, models, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.core.mail import app_url, send_email

from .models import (
    Department,
    DeptMembership,
    Lab,
    LabMembership,
    OrgInvite,
    OrgInviteRedemption,
)
from .services import (
    add_dept_member,
    add_lab_member,
    grantable_dept_role,
    grantable_lab_role,
    record_audit_event,
)

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

#: How many addresses one submission may carry. Not a quota — a manager may send
#: another batch straight away — but a ceiling on how far a single paste can fan
#: out mail in Mycelium's name.
MAX_BATCH_EMAILS = 15

#: What separates one address from the next in a pasted list. Chips arrive as a
#: JSON array; a paste arrives as one string, and people delimit it every way.
_ADDRESS_SPLIT = re.compile(r"[,;\s]+")


class AddressRefused(ValidationError):
    """One address a batch could not invite, with a reason the UI can branch on.

    A DRF ``ValidationError`` subclass on purpose: raised from
    :func:`create_invite`, it reaches the single-address endpoint as exactly the
    ``{"email": [...]}`` body it always returned. :func:`create_invites` catches
    it instead and reads ``reason`` off it, so one screening pass serves both.
    """

    #: Machine-readable reason: ``invalid_email``, ``already_member``,
    #: ``already_invited``, or ``duplicate``.
    reason = "invalid_email"

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__({"email": [detail]})
        self.reason = reason
        #: The sentence on its own, without DRF's field wrapper.
        self.message = detail


class InviteError(Exception):
    """An invite that cannot be spent, with a reason a stranger may safely read."""

    #: Machine-readable reason, for the join page to branch on.
    reason = "invalid"

    def __init__(self, message: str, reason: str = "invalid") -> None:
        super().__init__(message)
        self.reason = reason


#: How many invitations one account may create in a day, across every org, and
#: how many one org may receive. Each email invite puts Mycelium's name in a
#: stranger's inbox, so these are what stop an instance being used to send bulk
#: mail; a share link counts too because it is the same authority. Generous for
#: a lab inviting its people; a burst past them is not a lab inviting its people.
MAX_INVITES_PER_CREATOR_PER_DAY = 100
MAX_INVITES_PER_ORG_PER_DAY = 200


class InviteQuotaExceeded(Exception):
    """The creator, or the org, has sent as many invitations as a day allows."""


def new_token() -> str:
    """A fresh URL-safe invite token (about 256 bits)."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """The SHA-256 hex digest an invite is stored and looked up under.

    A plain digest is enough here, unlike for a six-digit code: the token carries
    about 256 bits, so there is no space small enough to sweep offline.
    """
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def invite_url(invite: OrgInvite) -> str | None:
    """The absolute link a recipient follows, or ``None`` once it is unknown.

    The raw token exists only on the object that minted it (``invite.token``, set
    by :func:`create_invite` and :func:`regenerate_invite`); a row read back from
    the database has only the digest, and no link can be rebuilt from that.
    """
    token = getattr(invite, "token", None)
    if not token:
        return None
    return app_url(f"{JOIN_PATH}/{token}")


def check_daily_quota(
    creator: User,
    *,
    lab: Lab | None = None,
    department: Department | None = None,
    adding: int = 1,
) -> None:
    """Refuse once ``creator`` or the org would pass a day's invitations.

    Counted from the rows themselves (the last 24 hours of ``OrgInvite`` and
    legacy ``LabInvitation``), so the cap holds across processes and restarts
    without a cache to agree on.
    """
    from .models import LabInvitation

    since = timezone.now() - timedelta(days=1)
    by_creator = (
        OrgInvite.objects.filter(created_by=creator, created_at__gte=since).count()
        + LabInvitation.objects.filter(inviter=creator, created_at__gte=since).count()
    )
    if by_creator + adding > MAX_INVITES_PER_CREATOR_PER_DAY:
        raise InviteQuotaExceeded(
            "You have sent as many invitations as one day allows. Try again tomorrow."
        )
    if lab is not None:
        by_org = (
            OrgInvite.objects.filter(lab=lab, created_at__gte=since).count()
            + LabInvitation.objects.filter(lab=lab, created_at__gte=since).count()
        )
    else:
        by_org = OrgInvite.objects.filter(
            department=department, created_at__gte=since
        ).count()
    if by_org + adding > MAX_INVITES_PER_ORG_PER_DAY:
        raise InviteQuotaExceeded(
            "This organization has sent as many invitations as one day allows. "
            "Try again tomorrow."
        )


def check_grant(
    creator: User,
    role: str,
    *,
    lab: Lab | None = None,
    department: Department | None = None,
) -> None:
    """Refuse a role the creator may not hand out (the rank rule; never owner)."""
    from rest_framework.exceptions import PermissionDenied

    from .permissions import user_can_grant_dept_role, user_can_invite_with_lab_role

    allowed = (
        user_can_invite_with_lab_role(creator, lab, role)
        if lab is not None
        else user_can_grant_dept_role(creator, department, role)
    )
    if allowed:
        return
    record_audit_event(
        actor=creator,
        action="org.invite.refused",
        target_type="lab" if lab is not None else "department",
        target_id=str(lab.id if lab is not None else department.id),
        metadata={"role": role},
    )
    if role == OrgInvite.Role.OWNER:
        raise PermissionDenied("An invitation never makes someone an owner.")
    if role == OrgInvite.Role.ADMIN:
        raise PermissionDenied("Only the owner can invite someone as an admin.")
    raise PermissionDenied("You can only invite people to a role below your own.")


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
    checked: bool = False,
) -> OrgInvite:
    """Create one invitation and, for an email invite, mail it.

    Raises DRF ``ValidationError`` on anything the creator can fix: a missing or
    malformed address, a role the org does not have, or a budget or window outside
    what is allowed. An address that is already a member, or that already holds an
    open invitation, raises the :class:`AddressRefused` subclass — which reaches a
    single-address caller as the same ``{"email": [...]}`` body, and gives
    :func:`create_invites` a reason to report per row.

    Raises DRF ``PermissionDenied`` when the creator may not hand out ``role``
    (owner never; admin only from the owner) and :class:`InviteQuotaExceeded`
    past the day's cap. ``checked=True`` skips both, for :func:`create_invites`,
    which runs them once for the whole batch.

    The returned object carries the raw token as ``invite.token`` — the only
    time it exists outside the recipient's mailbox.
    """
    if (lab is None) == (department is None):
        raise ValueError("Pass exactly one of lab / department.")

    kind = str(kind or "").strip().lower()
    if kind not in OrgInvite.Kind.values:
        raise ValidationError({"kind": ["Choose an email invite or a share link."]})

    role = _clean_role(role)
    if not checked:
        check_grant(creator, role, lab=lab, department=department)
        check_daily_quota(creator, lab=lab, department=department)
    address = str(email or "").strip().lower()

    if kind == OrgInvite.Kind.EMAIL:
        if not address:
            raise ValidationError({"email": ["An email address is required."]})
        screen_address(address, lab=lab, department=department)
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
    """Insert the row, retrying the (vanishingly unlikely) token collision.

    Only the digest is written; the raw token rides on the returned object.
    """
    for _ in range(5):
        token = new_token()
        try:
            with transaction.atomic():
                invite = OrgInvite.objects.create(
                    token_hash=hash_token(token), **fields
                )
        except IntegrityError:
            continue
        invite.token = token
        return invite
    raise RuntimeError("Could not allocate an invite token.")


def regenerate_invite(invite: OrgInvite, *, actor: User) -> OrgInvite:
    """Give a live invite a fresh token and return it carrying the raw one.

    The way a manager gets a share link back after the creation response is gone:
    the old link stops working in the same write, so a link that leaked is also
    retired by asking for it again.
    """
    for _ in range(5):
        token = new_token()
        try:
            with transaction.atomic():
                OrgInvite.objects.filter(pk=invite.pk).update(
                    token_hash=hash_token(token)
                )
        except IntegrityError:
            continue
        invite.token_hash = hash_token(token)
        invite.token = token
        record_audit_event(
            actor=actor,
            action="org.invite.regenerate",
            target_type="org_invite",
            target_id=str(invite.id),
            metadata={"org_kind": invite.org_kind},
        )
        return invite
    raise RuntimeError("Could not allocate an invite token.")


@dataclass(frozen=True)
class BatchResult:
    """What one :func:`create_invites` call did, address by address."""

    #: The invitations that were created, in the order the addresses were given.
    created: list[OrgInvite]
    #: One ``{"email", "reason", "detail"}`` per address that was refused.
    failed: list[dict]
    #: How many addresses the caller asked for, refusals included.
    requested: int


def normalize_addresses(raw) -> list[str]:
    """Clean a batch of addresses without deciding anything about them.

    Accepts what each surface actually sends: a list of chips, or one string a
    person pasted and delimited with commas, semicolons, or newlines. Lower-cases
    and strips, drops blanks, and **keeps duplicates** — collapsing them silently
    would leave the manager counting chips to work out why 12 addresses produced
    11 invitations. :func:`create_invites` reports them instead.
    """
    if raw in (None, ""):
        return []
    parts: list[str] = []
    values = raw if isinstance(raw, (list, tuple)) else [raw]
    for value in values:
        for piece in _ADDRESS_SPLIT.split(str(value or "").strip()):
            cleaned = piece.strip().strip(",;<>").lower()
            if cleaned:
                parts.append(cleaned)
    return parts


def create_invites(
    *,
    creator: User,
    lab: Lab | None = None,
    department: Department | None = None,
    emails,
    role: str = OrgInvite.Role.MEMBER,
    message: str = "",
    send: bool = True,
) -> BatchResult:
    """Invite up to :data:`MAX_BATCH_EMAILS` addresses in one go.

    Two kinds of problem, handled differently on purpose:

    * **The batch is wrong** — empty, or over the cap. That is the creator's
      mistake about the submission itself, so it raises ``ValidationError`` and
      nothing is created.
    * **One address is wrong** — malformed, already a member, already invited, or
      repeated. The other addresses are still invited and the refusal is returned
      alongside them. Discarding eleven good invitations because a twelfth was a
      typo would make the batch less useful than sending them one at a time.

    Each address is created and mailed in its own transaction, so a failure
    part-way through leaves the invitations before it standing.
    """
    if (lab is None) == (department is None):
        raise ValueError("Pass exactly one of lab / department.")

    _require_grantable(creator, _clean_role(role), lab=lab, department=department)
    addresses = normalize_addresses(emails)
    if not addresses:
        raise ValidationError({"emails": ["Add at least one email address."]})
    if len(addresses) > MAX_BATCH_EMAILS:
        raise ValidationError(
            {
                "emails": [
                    f"Invite at most {MAX_BATCH_EMAILS} people at a time — "
                    f"you gave {len(addresses)}."
                ]
            }
        )

    # Authority and the day's budget are settled once for the whole batch, before
    # any address is looked at: the batch is refused as a unit rather than half
    # sent.
    role = _clean_role(role)
    check_grant(creator, role, lab=lab, department=department)
    check_daily_quota(
        creator, lab=lab, department=department, adding=len(set(addresses))
    )

    created: list[OrgInvite] = []
    failed: list[dict] = []
    seen: set[str] = set()

    for address in addresses:
        if address in seen:
            failed.append(
                {
                    "email": address,
                    "reason": "duplicate",
                    "detail": "That address is in this list twice.",
                }
            )
            continue
        seen.add(address)
        try:
            invite = create_invite(
                creator=creator,
                lab=lab,
                department=department,
                kind=OrgInvite.Kind.EMAIL,
                email=address,
                role=role,
                message=message,
                send=send,
                checked=True,
            )
        except AddressRefused as exc:
            failed.append(
                {"email": address, "reason": exc.reason, "detail": exc.message}
            )
        except ValidationError as exc:
            failed.append(
                {"email": address, "reason": "invalid", "detail": _first_detail(exc)}
            )
        else:
            created.append(invite)

    record_audit_event(
        actor=creator,
        action="org.invite.batch",
        target_type="lab" if lab is not None else "department",
        target_id=str(lab.id if lab is not None else department.id),
        metadata={
            "org_kind": "lab" if lab is not None else "department",
            "requested": len(addresses),
            "created": len(created),
            "failed": len(failed),
            "role": _clean_role(role),
        },
    )
    return BatchResult(created=created, failed=failed, requested=len(addresses))


def invite_dept_member_by_username(
    department: Department,
    username: str,
    *,
    actor: User,
    role: str = OrgInvite.Role.MEMBER,
) -> OrgInvite | None:
    """Mail the account named ``username`` an invitation into ``department``.

    The department twin of
    :func:`apps.accounts.services.invite_lab_member_by_username`: never a
    membership written on the manager's say-so, and silent about the target —
    an unknown username, an existing member or an outstanding invitation all
    return ``None`` and the caller answers the same either way. The invitation is
    an ordinary email invite to the account's own address, so only that mailbox
    can spend it.
    """
    role = _clean_role(role)
    check_grant(actor, role, department=department)
    check_daily_quota(actor, department=department)

    target = User.objects.filter(username__iexact=str(username or "").strip()).first()
    if target is None or target == actor or not (target.email or "").strip():
        return None
    try:
        return create_invite(
            creator=actor,
            department=department,
            kind=OrgInvite.Kind.EMAIL,
            email=target.email,
            role=role,
            checked=True,
        )
    except ValidationError:
        # Already a member, already invited, or an address that will not
        # validate: the answer to the caller is the same as for a stranger.
        return None


def _first_detail(exc: ValidationError) -> str:
    """The first human sentence out of a DRF validation error, for one row."""
    detail = exc.detail
    if isinstance(detail, dict):
        for messages in detail.values():
            if isinstance(messages, (list, tuple)) and messages:
                return str(messages[0])
            return str(messages)
    if isinstance(detail, (list, tuple)) and detail:
        return str(detail[0])
    return "That address could not be invited."


def deliver_invite(invite: OrgInvite) -> bool:
    """Mail an email invite to the address it is bound to."""
    if invite.kind != OrgInvite.Kind.EMAIL or not invite.email:
        return False
    if invite_url(invite) is None:
        # Only the digest is stored; a link can be mailed only by the code that
        # just minted (or regenerated) the token.
        logger.error("Invite %s has no raw token to mail", invite.id)
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
        .filter(token_hash=hash_token(value))
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
    # The role is re-checked against the creator's authority *now*: an admin
    # link from someone who has since lost the right to make admins grants
    # member, and no link ever grants owner.
    role = grantable_lab_role(invite.created_by, lab, invite.role)
    add_lab_member(
        lab, user, role=role, actor=invite.created_by, enforce_rank=False
    )


def _join_department(invite: OrgInvite, user: User) -> None:
    department = invite.department
    if DeptMembership.objects.filter(department=department, user=user).exists():
        return
    role = grantable_dept_role(invite.created_by, department, invite.role)
    add_dept_member(
        department, user, role=role, actor=invite.created_by, enforce_rank=False
    )


def redeem_token(token: str, user: User) -> OrgInvite:
    """:func:`find_invite` then :func:`redeem`, the pair every caller wants."""
    return redeem(find_invite(token), user)


# --------------------------------------------------------------------------- #
# Serialization
# --------------------------------------------------------------------------- #


def invite_payload(invite: OrgInvite) -> dict:
    """The manager's view of one invite.

    ``url`` is present only on the response that created or regenerated the
    invite; listed afterwards it is ``null``, because only the token's digest is
    stored (``url_available`` says which).
    """
    url = invite_url(invite)
    return {
        "id": str(invite.id),
        "kind": invite.kind,
        "role": invite.role,
        "email": invite.email,
        "message": invite.message,
        "url": url,
        "url_available": url is not None,
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


def pending_for_email(email: str) -> OrgInvite | None:
    """The live email invite waiting for ``email``, or ``None``.

    Exists because an invited person who ignores the link and signs up on their
    own was, until now, silently stranded outside the org that asked for them:
    :func:`register_view` redeems only when an ``invite_token`` is posted, and
    ``claim_pending_invitations`` covers the legacy ``LabInvitation`` model, not
    this one. Matching on the typed address closes that.

    Deliberately **not** exposed as its own endpoint. "Does this address have an
    invitation?" answered to anyone who asks is an enumeration oracle over who
    has been invited where; the answer is only ever given to someone who has
    already registered that address, and the org is only named once they have
    proved the mailbox.
    """
    value = str(email or "").strip().lower()
    if not value:
        return None
    invite = (
        OrgInvite.objects.select_related("lab", "department", "created_by")
        .filter(
            kind=OrgInvite.Kind.EMAIL,
            email=value,
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
        )
        .order_by("-created_at")
        .first()
    )
    if invite is None or invite.used_count >= invite.max_uses or invite.org is None:
        return None
    return invite


def claim_for_verified_email(user) -> OrgInvite | None:
    """Redeem the invite addressed to ``user``'s just-proved address, if any.

    The mailbox is the proof. A pending invite matched at sign-up is only a
    *claim* — anyone who can type an address could have made it — so the
    membership is granted here, once a code mailed to that address has come
    back, which is the same standard the token path already meets.

    Never raises: a seat ceiling, a revoked invite or a race that spent the last
    use must not turn a successful verification into a failed one. The invite is
    simply left unspent and the person is still verified.
    """
    invite = pending_for_email(getattr(user, "email", ""))
    if invite is None:
        return None
    try:
        return redeem(invite, user)
    except (InviteError, ValidationError):
        logger.warning("pending invite claim failed for %s", user, exc_info=True)
        return None


def is_live(invite: OrgInvite) -> bool:
    return (
        invite.revoked_at is None
        and invite.expires_at > timezone.now()
        and invite.used_count < invite.max_uses
    )


# --------------------------------------------------------------------------- #
# Input cleaning
# --------------------------------------------------------------------------- #


def _require_grantable(
    creator: User,
    role: str,
    *,
    lab: Lab | None,
    department: Department | None,
) -> None:
    """An invitation grants its role on redemption, so its creator must be able to.

    Without this a department or lab admin could mint another admin by link —
    the same escalation the role edit was closed against, by a different door.
    """
    from .permissions import user_can_grant_org_role

    if user_can_grant_org_role(creator, role, lab=lab, department=department):
        return
    from .services import record_audit_event

    org = lab if lab is not None else department
    record_audit_event(
        actor=creator,
        action=f"{'lab' if lab is not None else 'dept'}.member.role.refused",
        target_type="lab" if lab is not None else "department",
        target_id=str(org.id),
        metadata={"user_id": None, "role": role, "via": "invite"},
    )
    head = "lab's PI" if lab is not None else "department head"
    raise PermissionDenied(f"Only the {head} can invite someone as {role}.")


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


def screen_address(
    address: str, *, lab: Lab | None, department: Department | None
) -> None:
    """Refuse an address this org should not be mailed about, with a reason.

    Three refusals, each :class:`AddressRefused`:

    * ``invalid_email`` — not an address at all, caught before any query.
    * ``already_member`` — say so rather than mailing an invitation to somebody
      who is already inside.
    * ``already_invited`` — a live, unspent email invitation to this address for
      this org exists. Without this check a re-submitted batch mails the same
      person twice, which is how an invitation starts reading as spam.
    """
    noun = "lab" if lab is not None else "department"
    try:
        validate_email(address)
    except DjangoValidationError as exc:
        raise AddressRefused(
            "invalid_email", "That does not look like an email address."
        ) from exc

    user = User.objects.filter(email__iexact=address).first()
    if user is not None:
        in_lab = lab is not None and LabMembership.objects.filter(
            lab=lab, user=user
        ).exists()
        if in_lab:
            raise AddressRefused(
                "already_member", f"That person is already a member of this {noun}."
            )
        if (
            department is not None
            and DeptMembership.objects.filter(department=department, user=user).exists()
        ):
            raise AddressRefused(
                "already_member", f"That person is already a member of this {noun}."
            )

    outstanding = OrgInvite.objects.filter(
        lab=lab,
        department=department,
        kind=OrgInvite.Kind.EMAIL,
        email=address,
        revoked_at__isnull=True,
        expires_at__gt=timezone.now(),
    ).filter(used_count__lt=models.F("max_uses"))
    if outstanding.exists():
        raise AddressRefused(
            "already_invited",
            f"That address already has an open invitation to this {noun}. "
            "Withdraw it first to send another.",
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
