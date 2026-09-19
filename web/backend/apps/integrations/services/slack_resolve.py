"""Slack's one door to the ORM (ambient Plan 11), like ``resolve`` for Discord.

Every Slack module — the events handler, link codes, the outbox, the views —
reaches a model only through here, so the boundary the import-graph test
enforces for Discord holds for Slack too. An ACTIVE identity resolves and
nothing else does; most people in a workspace have no Mycelium account, and
``None`` is the whole of what happens to them.
"""

from __future__ import annotations

from django.contrib.auth.models import User
from django.utils import timezone

from ..models import (
    LinkCode,
    SlackIdentity,
    SlackOutboxMessage,
    SlackWorkspace,
)

ACTIVE = SlackIdentity.State.ACTIVE
CODE_PERSON = LinkCode.Kind.PERSON
CODE_LAB = LinkCode.Kind.LAB
OUTBOX_PENDING = SlackOutboxMessage.Status.PENDING
OUTBOX_SENDING = SlackOutboxMessage.Status.SENDING
OUTBOX_SENT = SlackOutboxMessage.Status.SENT
OUTBOX_FAILED = SlackOutboxMessage.Status.FAILED
OUTBOX_DEAD = SlackOutboxMessage.Status.DEAD
TARGET_DM = SlackOutboxMessage.Target.DM
TARGET_CHANNEL = SlackOutboxMessage.Target.CHANNEL


# -- identities ------------------------------------------------------------------


def resolve_user(team_id: str, slack_user_id: str) -> User | None:
    identity = (
        SlackIdentity.objects.filter(
            team_id=str(team_id), slack_user_id=str(slack_user_id), state=ACTIVE
        )
        .select_related("user")
        .first()
    )
    if identity is None or not identity.user.is_active:
        return None
    return identity.user


def identity_for(user, team_id: str | None = None) -> SlackIdentity | None:
    """A person's active Slack identity (in a workspace, or the latest)."""
    rows = SlackIdentity.objects.filter(user=user, state=ACTIVE)
    if team_id is not None:
        rows = rows.filter(team_id=str(team_id))
    return rows.order_by("-linked_at").first()


def identities_for(user) -> list[SlackIdentity]:
    return list(SlackIdentity.objects.filter(user=user, state=ACTIVE))


def unlink(user, team_id: str) -> int:
    return SlackIdentity.objects.filter(
        user=user, team_id=str(team_id), state=ACTIVE
    ).update(state=SlackIdentity.State.REVOKED, revoked_at=timezone.now())


def linked_elsewhere(team_id: str, slack_user_id: str, *, not_user) -> bool:
    return (
        SlackIdentity.objects.filter(
            team_id=team_id, slack_user_id=slack_user_id, state=ACTIVE
        )
        .exclude(user=not_user)
        .exists()
    )


def bind_identity(user, team_id: str, slack_user_id: str) -> SlackIdentity:
    """Make this the person's one active identity in the workspace."""
    now = timezone.now()
    SlackIdentity.objects.filter(user=user, team_id=team_id, state=ACTIVE).exclude(
        slack_user_id=slack_user_id
    ).update(state=SlackIdentity.State.REVOKED, revoked_at=now)
    identity, _ = SlackIdentity.objects.get_or_create(
        user=user, team_id=team_id, slack_user_id=slack_user_id, state=ACTIVE
    )
    return identity


# -- workspaces ------------------------------------------------------------------


def active_workspace(team_id: str) -> SlackWorkspace | None:
    return SlackWorkspace.objects.filter(team_id=str(team_id), active=True).first()


def workspace_for_lab(lab, *, with_channel: bool = False) -> SlackWorkspace | None:
    rows = SlackWorkspace.objects.filter(lab=lab, active=True)
    if with_channel:
        rows = rows.exclude(updates_channel_id="")
    return rows.first()


def labs_with_workspaces():
    from apps.accounts.models import Lab

    return Lab.objects.filter(slack_workspaces__active=True).distinct()


def team_names() -> dict[str, str]:
    return dict(SlackWorkspace.objects.values_list("team_id", "name"))


def install_workspace(
    *, team_id: str, name: str, bot_token: str, bot_user_id: str, installed_by
) -> SlackWorkspace:
    workspace, _ = SlackWorkspace.objects.update_or_create(
        team_id=team_id,
        defaults={
            "name": name[:120],
            "bot_token": bot_token,
            "bot_user_id": bot_user_id,
            "installed_by": installed_by,
            "active": True,
        },
    )
    return workspace


def deactivate_workspace(workspace: SlackWorkspace) -> None:
    workspace.active = False
    workspace.save(update_fields=["active", "updated_at"])


def bind_workspace_lab(workspace: SlackWorkspace, lab_id, channel_id: str) -> None:
    workspace.lab_id = lab_id
    workspace.updates_channel_id = channel_id
    workspace.save(update_fields=["lab", "updates_channel_id", "updated_at"])


def set_reports_primary(workspace: SlackWorkspace, primary: bool) -> None:
    workspace.reports_primary = bool(primary)
    workspace.save(update_fields=["reports_primary", "updated_at"])


# -- link codes ------------------------------------------------------------------


def retire_codes(*, kind: str, user, lab, now, platform: str = "slack") -> None:
    LinkCode.objects.filter(
        platform=platform, kind=kind, user=user, lab=lab, used_at__isnull=True
    ).update(expires_at=now)


def store_code(
    *, kind: str, user, lab, code_hash: str, expires_at, platform: str = "slack"
) -> None:
    LinkCode.objects.create(
        platform=platform,
        kind=kind,
        user=user,
        lab=lab,
        code_hash=code_hash,
        expires_at=expires_at,
    )


def claim_code(code_hash: str, kind: str, platform: str = "slack") -> LinkCode | None:
    """The unused, unexpired code, locked. Call inside a transaction."""
    row = (
        LinkCode.objects.select_for_update()
        .filter(
            code_hash=code_hash, kind=kind, platform=platform, used_at__isnull=True
        )
        .first()
    )
    if row is None or row.expires_at <= timezone.now():
        return None
    return row


def use_code(row: LinkCode, team_id: str) -> None:
    row.used_at = timezone.now()
    row.used_team_id = team_id
    row.save(update_fields=["used_at", "used_team_id"])


# -- the outbox ------------------------------------------------------------------


def outbox_by_key(dedupe_key: str) -> SlackOutboxMessage | None:
    return SlackOutboxMessage.objects.filter(dedupe_key=dedupe_key).first()


def outbox_create(**fields) -> SlackOutboxMessage:
    return SlackOutboxMessage.objects.create(**fields)


def outbox_claim(limit: int, now) -> list[int]:
    """Due pending rows, marked sending. Call inside a transaction."""
    ids = list(
        SlackOutboxMessage.objects.select_for_update(skip_locked=True)
        .filter(status=OUTBOX_PENDING, next_attempt_at__lte=now)
        .order_by("next_attempt_at", "id")
        .values_list("pk", flat=True)[:limit]
    )
    SlackOutboxMessage.objects.filter(pk__in=ids).update(status=OUTBOX_SENDING)
    return ids


def outbox_row(pk: int) -> SlackOutboxMessage:
    return SlackOutboxMessage.objects.get(pk=pk)
