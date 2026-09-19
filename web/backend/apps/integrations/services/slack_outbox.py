"""The Slack outbox: enqueue now, deliver when the drain reaches the row.

The same shape as the Discord outbox (:mod:`.outbox`): the dedupe key makes a
producer safe to re-run, a transient failure is retried with a delay, a
permanent one settles the row as failed, and attempts run out into ``dead``.
A DM resolves the person's identity at send time, so an identity revoked in
the meantime is never written to. Every row is reached through
:mod:`.slack_resolve`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from . import slack_api, slack_resolve


def enqueue_dm(
    *,
    user,
    dedupe_key: str,
    kind: str,
    text: str,
    blocks=None,
    subject_type: str = "",
    subject_id: str = "",
    not_before=None,
) -> tuple:
    """Queue a DM to ``user``'s Slack identity. ``(row, created)``; ``(None,
    False)`` when the person has no Slack identity."""
    identity = slack_resolve.identity_for(user)
    if identity is None:
        return None, False
    return _enqueue(
        dedupe_key=dedupe_key,
        kind=kind,
        target_type=slack_resolve.TARGET_DM,
        recipient_user=user,
        team_id=identity.team_id,
        text=text,
        blocks=blocks,
        subject_type=subject_type,
        subject_id=subject_id,
        not_before=not_before,
    )


def enqueue_channel(
    *,
    workspace,
    dedupe_key: str,
    kind: str,
    text: str,
    blocks=None,
    subject_type: str = "",
    subject_id: str = "",
    not_before=None,
) -> tuple:
    if not workspace.updates_channel_id:
        return None, False
    return _enqueue(
        dedupe_key=dedupe_key,
        kind=kind,
        target_type=slack_resolve.TARGET_CHANNEL,
        team_id=workspace.team_id,
        channel_id=workspace.updates_channel_id,
        lab=workspace.lab,
        text=text,
        blocks=blocks,
        subject_type=subject_type,
        subject_id=subject_id,
        not_before=not_before,
    )


def enqueue_reply(
    *, team_id: str, channel_id: str, dedupe_key: str, kind: str, text: str, blocks=None
) -> tuple:
    """A reply into the conversation it answers (a DM channel, usually) —
    for people who may not be linked yet, so no identity is resolved."""
    return _enqueue(
        dedupe_key=dedupe_key,
        kind=kind,
        target_type=slack_resolve.TARGET_CHANNEL,
        team_id=team_id,
        channel_id=channel_id,
        text=text,
        blocks=blocks,
        not_before=None,
    )


def _enqueue(*, dedupe_key, not_before, **fields):
    existing = slack_resolve.outbox_by_key(dedupe_key)
    if existing is not None:
        return existing, False
    try:
        with transaction.atomic():
            row = slack_resolve.outbox_create(
                dedupe_key=dedupe_key,
                next_attempt_at=not_before or timezone.now(),
                **fields,
            )
    except IntegrityError:
        return slack_resolve.outbox_by_key(dedupe_key), False
    return row, True


@dataclass
class Drained:
    sent: int = 0
    retried: int = 0
    failed: int = 0
    dead: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "sent": self.sent,
            "retried": self.retried,
            "failed": self.failed,
            "dead": self.dead,
        }


def deliver_one(row, *, send=None) -> str:
    """Send one row. Returns ``sent``, ``retry``, ``failed`` or ``dead``."""
    send = send or _send
    workspace = slack_resolve.active_workspace(row.team_id)
    if workspace is None or not workspace.bot_token:
        return _settle(row, "failed", "workspace_not_installed")
    channel = row.channel_id
    if row.target_type == slack_resolve.TARGET_DM:
        identity = slack_resolve.identity_for(row.recipient_user, row.team_id)
        if identity is None:
            return _settle(row, "failed", "identity_revoked")
        channel = identity.slack_user_id
    try:
        ts = send(workspace, row, channel)
    except slack_api.SlackError as exc:
        if exc.permanent:
            return _settle(row, "failed", exc.error)
        return _retry(row, exc.error)
    row.slack_ts = ts
    return _settle(row, "sent", "")


def _send(workspace, row, channel) -> str:
    token = workspace.bot_token
    if row.target_type == slack_resolve.TARGET_DM:
        channel = slack_api.open_dm(token, channel)
    return slack_api.post_message(token, channel, text=row.text, blocks=row.blocks)


def _settle(row, outcome: str, error: str) -> str:
    now = timezone.now()
    row.attempts += 1
    row.last_error = error[:64]
    row.status = {
        "sent": slack_resolve.OUTBOX_SENT,
        "failed": slack_resolve.OUTBOX_FAILED,
        "dead": slack_resolve.OUTBOX_DEAD,
    }[outcome]
    row.settled_at = now
    if outcome == "sent":
        row.sent_at = now
    row.save()
    return outcome


def _retry(row, error: str) -> str:
    row.attempts += 1
    row.last_error = error[:64]
    if row.attempts >= int(settings.SLACK_OUTBOX_MAX_ATTEMPTS):
        row.status = slack_resolve.OUTBOX_DEAD
        row.settled_at = timezone.now()
        row.save()
        return "dead"
    row.status = slack_resolve.OUTBOX_PENDING
    row.next_attempt_at = timezone.now() + timedelta(
        seconds=int(settings.SLACK_OUTBOX_RETRY_SECONDS) * row.attempts
    )
    row.save()
    return "retry"


def drain(*, limit: int | None = None, now=None, send=None) -> Drained:
    limit = limit or int(settings.SLACK_OUTBOX_BATCH_LIMIT)
    result = Drained()
    with transaction.atomic():
        claimed = slack_resolve.outbox_claim(limit, now or timezone.now())
    for pk in claimed:
        row = slack_resolve.outbox_row(pk)
        outcome = deliver_one(row, send=send)
        if outcome == "sent":
            result.sent += 1
        elif outcome == "retry":
            result.retried += 1
        elif outcome == "failed":
            result.failed += 1
            result.errors.append(row.last_error)
        else:
            result.dead += 1
    return result
