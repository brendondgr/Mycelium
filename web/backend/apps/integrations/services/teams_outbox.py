"""The Teams outbox (ambient Plan 11): the Slack outbox's contract, sending
into conversations Mylo holds a reference to."""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from . import teams_api, teams_auth, teams_resolve


def enqueue(
    *,
    dedupe_key: str,
    kind: str,
    service_url: str,
    conversation_id: str,
    text: str,
    attachments=None,
    user=None,
    not_before=None,
) -> tuple:
    existing = teams_resolve.outbox_by_key(dedupe_key)
    if existing is not None:
        return existing, False
    try:
        with transaction.atomic():
            row = teams_resolve.outbox_create(
                dedupe_key=dedupe_key,
                kind=kind,
                recipient_user=user,
                service_url=service_url,
                conversation_id=conversation_id,
                text=text,
                attachments=attachments,
                next_attempt_at=not_before or timezone.now(),
            )
    except IntegrityError:
        return teams_resolve.outbox_by_key(dedupe_key), False
    return row, True


def enqueue_dm(
    *, user, dedupe_key: str, kind: str, text: str, attachments=None, not_before=None
):
    """To a person's personal chat with Mylo — known once they have DMed it."""
    identity = teams_resolve.identity_for(user)
    if identity is None or not identity.conversation_id:
        return None, False
    return enqueue(
        dedupe_key=dedupe_key,
        kind=kind,
        service_url=identity.service_url,
        conversation_id=identity.conversation_id,
        text=text,
        attachments=attachments,
        user=user,
        not_before=not_before,
    )


def _send(row) -> str:
    return teams_api.send_activity(
        row.service_url,
        row.conversation_id,
        token=teams_auth.bot_token(),
        text=row.text,
        attachments=row.attachments,
    )


def drain(*, limit: int = 50, now=None, send=None) -> dict:
    send = send or _send
    counts = {"sent": 0, "retried": 0, "failed": 0, "dead": 0}
    with transaction.atomic():
        claimed = teams_resolve.outbox_claim(limit, now or timezone.now())
    for pk in claimed:
        row = teams_resolve.outbox_row(pk)
        row.attempts += 1
        try:
            send(row)
        except teams_api.TeamsError as exc:
            row.last_error = exc.error[:64]
            if exc.permanent:
                row.status, row.settled_at = teams_resolve.OUTBOX_FAILED, timezone.now()
                counts["failed"] += 1
            elif row.attempts >= int(settings.TEAMS_OUTBOX_MAX_ATTEMPTS):
                row.status, row.settled_at = teams_resolve.OUTBOX_DEAD, timezone.now()
                counts["dead"] += 1
            else:
                row.status = teams_resolve.OUTBOX_PENDING
                row.next_attempt_at = timezone.now() + timedelta(
                    seconds=int(settings.TEAMS_OUTBOX_RETRY_SECONDS) * row.attempts
                )
                counts["retried"] += 1
            row.save()
            continue
        row.status, row.settled_at = teams_resolve.OUTBOX_SENT, timezone.now()
        row.save()
        counts["sent"] += 1
    return counts
