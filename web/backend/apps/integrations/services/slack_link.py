"""Link codes: carrying Mycelium authority into Slack (ambient Plan 11).

A person links by DMing Mylo the code the web gave them; a lab manager links a
workspace to a lab by mentioning Mylo with a lab code in the channel that
should get the lab's reports. Codes are single-use, short-lived, stored as a
hash, and the authority lives at issuance: only a lab's managers can make a
lab code.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ..models import SlackIdentity, SlackLinkCode, SlackWorkspace

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I


def _hash(code: str) -> str:
    normal = "".join(ch for ch in code.upper() if ch.isalnum())
    return hashlib.sha256(normal.encode()).hexdigest()


def _new_code() -> str:
    body = "".join(secrets.choice(_ALPHABET) for _ in range(8))
    return f"MYLO-{body[:4]}-{body[4:]}"


def issue(*, user, lab=None) -> str:
    """A fresh code (the plaintext, shown once). Older unused codes of the same
    kind for the same person or lab are retired."""
    kind = SlackLinkCode.Kind.LAB if lab is not None else SlackLinkCode.Kind.PERSON
    now = timezone.now()
    SlackLinkCode.objects.filter(
        kind=kind, user=user, lab=lab, used_at__isnull=True
    ).update(expires_at=now)
    code = _new_code()
    SlackLinkCode.objects.create(
        kind=kind,
        user=user,
        lab=lab,
        code_hash=_hash(code),
        expires_at=now + timedelta(minutes=int(settings.SLACK_LINK_CODE_MINUTES)),
    )
    return code


@dataclass(frozen=True)
class Redeemed:
    ok: bool
    reason: str = ""
    kind: str = ""


def _claim(code: str, kind: str) -> SlackLinkCode | None:
    row = (
        SlackLinkCode.objects.select_for_update()
        .filter(code_hash=_hash(code), kind=kind, used_at__isnull=True)
        .first()
    )
    if row is None or row.expires_at <= timezone.now():
        return None
    return row


def redeem_person(code: str, *, team_id: str, slack_user_id: str) -> Redeemed:
    """Bind the Slack user who DMed the code to the account that issued it."""
    with transaction.atomic():
        row = _claim(code, SlackLinkCode.Kind.PERSON)
        if row is None:
            return Redeemed(False, "invalid_or_expired")
        taken = SlackIdentity.objects.filter(
            team_id=team_id,
            slack_user_id=slack_user_id,
            state=SlackIdentity.State.ACTIVE,
        ).exclude(user=row.user)
        if taken.exists():
            return Redeemed(False, "slack_user_linked_elsewhere")
        now = timezone.now()
        SlackIdentity.objects.filter(
            user=row.user, team_id=team_id, state=SlackIdentity.State.ACTIVE
        ).exclude(slack_user_id=slack_user_id).update(
            state=SlackIdentity.State.REVOKED, revoked_at=now
        )
        SlackIdentity.objects.get_or_create(
            user=row.user,
            team_id=team_id,
            slack_user_id=slack_user_id,
            state=SlackIdentity.State.ACTIVE,
        )
        row.used_at = now
        row.used_team_id = team_id
        row.save(update_fields=["used_at", "used_team_id"])
    return Redeemed(True, kind="person")


def redeem_lab(code: str, *, team_id: str, channel_id: str) -> Redeemed:
    """Bind the workspace to the code's lab; the channel becomes its updates
    channel. The workspace must already be installed."""
    with transaction.atomic():
        row = _claim(code, SlackLinkCode.Kind.LAB)
        if row is None or row.lab_id is None:
            return Redeemed(False, "invalid_or_expired")
        workspace = SlackWorkspace.objects.filter(team_id=team_id, active=True).first()
        if workspace is None:
            return Redeemed(False, "workspace_not_installed")
        if workspace.lab_id and workspace.lab_id != row.lab_id:
            return Redeemed(False, "workspace_linked_to_another_lab")
        workspace.lab_id = row.lab_id
        workspace.updates_channel_id = channel_id
        workspace.save(update_fields=["lab", "updates_channel_id", "updated_at"])
        row.used_at = timezone.now()
        row.used_team_id = team_id
        row.save(update_fields=["used_at", "used_team_id"])
    return Redeemed(True, kind="lab")


def find_code(text: str) -> str | None:
    """A link code inside a message, if there is one."""
    import re

    match = re.search(r"MYLO-[A-Z0-9]{4}-[A-Z0-9]{4}", (text or "").upper())
    return match.group(0) if match else None
