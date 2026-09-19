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

from . import slack_resolve

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
    kind = slack_resolve.CODE_LAB if lab is not None else slack_resolve.CODE_PERSON
    now = timezone.now()
    slack_resolve.retire_codes(kind=kind, user=user, lab=lab, now=now)
    code = _new_code()
    slack_resolve.store_code(
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


def _claim(code: str, kind: str):
    return slack_resolve.claim_code(_hash(code), kind)


def redeem_person(code: str, *, team_id: str, slack_user_id: str) -> Redeemed:
    """Bind the Slack user who DMed the code to the account that issued it."""
    with transaction.atomic():
        row = _claim(code, slack_resolve.CODE_PERSON)
        if row is None:
            return Redeemed(False, "invalid_or_expired")
        if slack_resolve.linked_elsewhere(team_id, slack_user_id, not_user=row.user):
            return Redeemed(False, "slack_user_linked_elsewhere")
        slack_resolve.bind_identity(row.user, team_id, slack_user_id)
        slack_resolve.use_code(row, team_id)
    return Redeemed(True, kind="person")


def redeem_lab(code: str, *, team_id: str, channel_id: str) -> Redeemed:
    """Bind the workspace to the code's lab; the channel becomes its updates
    channel. The workspace must already be installed."""
    with transaction.atomic():
        row = _claim(code, slack_resolve.CODE_LAB)
        if row is None or row.lab_id is None:
            return Redeemed(False, "invalid_or_expired")
        workspace = slack_resolve.active_workspace(team_id)
        if workspace is None:
            return Redeemed(False, "workspace_not_installed")
        if workspace.lab_id and workspace.lab_id != row.lab_id:
            return Redeemed(False, "workspace_linked_to_another_lab")
        slack_resolve.bind_workspace_lab(workspace, row.lab_id, channel_id)
        slack_resolve.use_code(row, team_id)
    return Redeemed(True, kind="lab")


def find_code(text: str) -> str | None:
    """A link code inside a message, if there is one."""
    import re

    match = re.search(r"MYLO-[A-Z0-9]{4}-[A-Z0-9]{4}", (text or "").upper())
    return match.group(0) if match else None
