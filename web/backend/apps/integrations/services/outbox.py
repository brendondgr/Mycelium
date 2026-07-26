"""The outbound Discord queue: enqueue here, a worker delivers.

Before this, "the system decided to send something" and "Discord received it" were
the same instant, and the record that stops a duplicate was written either way. Thirty
seconds of Discord being unavailable therefore retired that person's reminder
permanently. Now a producer queues a row and gets on with its work; a drain attempts
delivery, and a failure stays claimable instead of vanishing.

**Two senders deliberately do not go through here**, and that is not an oversight to
be tidied up later:

* ``reminders_discord.preflight_channel`` — ``/setup`` proves a channel is postable by
  actually posting to it, and has to tell the admin *there and then* whether the bind
  worked. Queued, it could only answer "pending", and the whole bind flow loses its
  meaning.
* ``errors.post_embed`` — the ops error channel. Routing the outage reporter through
  the thing that might be broken means an outbox failure is silent, which is the one
  failure mode operations cannot afford.

Both are diagnostics rather than product messages, and both keep their own direct
path. ``test_outbox_drain.py`` asserts it, so nobody "finishes the migration" later by
accident.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from . import discord_api, resolve
from .discord_failure import (
    Classification,
    Reason,
    Verdict,
    classify,
    classify_exception,
)

log = logging.getLogger(__name__)


@dataclass
class DrainResult:
    """A tally of one drain pass."""

    claimed: int = 0
    delivered: int = 0
    retried: int = 0
    failed: int = 0
    dead: int = 0
    reasons: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "claimed": self.claimed,
            "delivered": self.delivered,
            "retried": self.retried,
            "failed": self.failed,
            "dead": self.dead,
            "reasons": self.reasons,
        }


# --------------------------------------------------------------------------- #
# Producing
# --------------------------------------------------------------------------- #
def enqueue_dm(
    *,
    dedupe_key: str,
    kind: str,
    user,
    content: str = "",
    embed: dict | None = None,
    attachment_path: str = "",
    attachment_filename: str = "",
    subject_type: str = "",
    subject_id: str = "",
) -> tuple[object, bool]:
    """Queue a direct message. The DM channel is resolved at *send* time.

    Deliberately not resolved here: a cached ``dm_channel_id`` can go stale between
    queueing and delivery, and re-resolving costs one request only on the attempt that
    actually happens.
    """
    return resolve.enqueue_outbox(
        dedupe_key=dedupe_key,
        kind=kind,
        target_type=resolve.OUTBOX_DM,
        recipient_user=user,
        content=content,
        embed=embed,
        attachment_path=attachment_path,
        attachment_filename=attachment_filename,
        subject_type=subject_type,
        subject_id=subject_id,
    )


def enqueue_channel(
    *,
    dedupe_key: str,
    kind: str,
    channel_id: str,
    lab=None,
    content: str = "",
    embed: dict | None = None,
    allowed_mentions: dict | None = None,
    subject_type: str = "",
    subject_id: str = "",
) -> tuple[object, bool]:
    """Queue a channel post."""
    return resolve.enqueue_outbox(
        dedupe_key=dedupe_key,
        kind=kind,
        target_type=resolve.OUTBOX_CHANNEL,
        channel_id=str(channel_id),
        lab=lab,
        content=content,
        embed=embed,
        allowed_mentions=allowed_mentions,
        subject_type=subject_type,
        subject_id=subject_id,
    )


# --------------------------------------------------------------------------- #
# Delivering
# --------------------------------------------------------------------------- #
def deliver_one(message) -> Classification:
    """Attempt one queued message. Never raises."""
    if not getattr(settings, "DISCORD_BOT_TOKEN", ""):
        # No token: we cannot reach Discord at all, and no amount of retrying will
        # configure one. Permanent, and distinctly labelled so it is not misread as
        # the recipient's fault.
        return Classification(Verdict.PERMANENT, Reason.NOT_CONFIGURED)

    if message.target_type == resolve.OUTBOX_DM:
        channel_id, precheck = _dm_channel_for(message)
        if precheck is not None:
            return precheck
    else:
        channel_id = message.channel_id
        if not channel_id:
            return Classification(Verdict.PERMANENT, Reason.NO_ACCESS)

    payload = _payload(message)
    try:
        if message.attachment_path:
            file_bytes = _read_attachment(message)
            if file_bytes is None:
                return Classification(Verdict.PERMANENT, Reason.ATTACHMENT_GONE)
            resp = discord_api.create_message_with_attachment(
                channel_id,
                filename=message.attachment_filename or "attachment.pdf",
                file_bytes=file_bytes,
                **payload,
            )
        else:
            resp = discord_api.create_message(channel_id, **payload)
    except discord_api.DiscordHTTPError as exc:
        return classify_exception(exc)

    verdict = classify(
        status=resp.status,
        error_code=discord_api._err_code(resp.json),
        retry_after=resp.retry_after,
    )
    if verdict.ok:
        message.discord_message_id = str(resp.json.get("id") or "")
    return verdict


def _payload(message) -> dict:
    return {
        "content": message.content or "",
        "embed": message.embed or None,
        "allowed_mentions": message.allowed_mentions or None,
        "nonce": message.nonce,
    }


def _read_attachment(message) -> bytes | None:
    path = Path(message.attachment_path)
    try:
        return path.read_bytes()
    except OSError:
        log.warning("outbox attachment missing: %s", message.attachment_path)
        return None


def _dm_channel_for(message) -> tuple[str, Classification | None]:
    """Resolve (and cache) the DM channel, or explain why we cannot.

    Returns ``(channel_id, None)`` on success, or ``("", classification)`` when the
    person is not reachable — which is a fact about the link, not a transport blip,
    so it must not consume retries.
    """
    user = message.recipient_user
    if user is None:
        return "", Classification(Verdict.PERMANENT, Reason.NO_ACCESS)

    identity = resolve.active_identity_for_user(user)
    if identity is None:
        return "", Classification(Verdict.PERMANENT, Reason.NO_ACCESS)
    if identity.dm_ok is False:
        return "", Classification(Verdict.PERMANENT, Reason.DM_BLOCKED)

    if identity.dm_channel_id:
        return identity.dm_channel_id, None

    try:
        opened = discord_api.open_dm_raw(identity.discord_user_id)
    except discord_api.DiscordHTTPError as exc:
        return "", classify_exception(exc)

    verdict = classify(
        status=opened.status,
        error_code=discord_api._err_code(opened.json),
        retry_after=opened.retry_after,
    )
    if not verdict.ok:
        if verdict.verdict is Verdict.PERMANENT:
            resolve.set_identity_dm(
                identity, dm_ok=False, error_code=verdict.error_code
            )
        return "", verdict

    channel_id = str(opened.json.get("id") or "")
    if not channel_id:
        return "", Classification(Verdict.PERMANENT, Reason.NO_ACCESS)
    resolve.set_identity_dm(identity, dm_ok=True, dm_channel_id=channel_id)
    return channel_id, None


# --------------------------------------------------------------------------- #
# Draining
# --------------------------------------------------------------------------- #
def drain(*, limit: int | None = None, now: datetime | None = None) -> DrainResult:
    """Claim due messages, attempt each, and settle it. Never raises."""
    now = now or timezone.now()
    limit = limit or getattr(settings, "DISCORD_OUTBOX_BATCH_LIMIT", 50)
    result = DrainResult()

    for message in resolve.claim_outbox_batch(limit=limit, now=now):
        result.claimed += 1
        verdict = deliver_one(message)
        _settle(message, verdict, result, now=now)
    return result


def _settle(message, verdict: Classification, result: DrainResult, *, now) -> None:
    if verdict.ok:
        resolve.mark_outbox_sent(
            message, discord_message_id=message.discord_message_id, now=now
        )
        result.delivered += 1
        return

    reason = str(verdict.reason or "")
    result.reasons[reason] = result.reasons.get(reason, 0) + 1

    if verdict.verdict is Verdict.PERMANENT:
        _on_permanent(message, verdict)
        resolve.mark_outbox_permanent(
            message, error_code=verdict.error_code, reason=reason, now=now
        )
        result.failed += 1
        return

    max_attempts = getattr(settings, "DISCORD_OUTBOX_MAX_ATTEMPTS", 5)
    if message.attempts >= max_attempts:
        resolve.mark_outbox_dead(
            message, error_code=verdict.error_code, reason=reason, now=now
        )
        result.dead += 1
        _on_dead(message, verdict)
        return

    resolve.mark_outbox_retry(
        message,
        next_attempt_at=now + timedelta(seconds=_wait_seconds(verdict)),
        error_code=verdict.error_code,
        reason=reason,
    )
    result.retried += 1


def _wait_seconds(verdict: Classification) -> float:
    """The flat interval, unless Discord asked us to wait longer than that.

    Discord's own ``Retry-After`` may only lengthen the wait. Honouring a *shorter*
    one would let a rate-limited burst re-enter the same rate limit immediately.
    """
    base = float(getattr(settings, "DISCORD_OUTBOX_RETRY_SECONDS", 300))
    return max(base, float(verdict.retry_after or 0))


def _on_permanent(message, verdict: Classification) -> None:
    """Record what a permanent failure taught us about the link.

    A failed send is evidence: an undeliverable DM means that person is unreachable.
    Feeding it back here rather than treating it as a separate concern is what stops
    the queue retrying into a void every day (Workstream E builds on this).
    """
    if verdict.reason is Reason.DM_BLOCKED and message.recipient_user_id:
        identity = resolve.active_identity_for_user(message.recipient_user)
        if identity is not None and identity.dm_ok is not False:
            resolve.set_identity_dm(
                identity, dm_ok=False, error_code=verdict.error_code
            )


def _on_dead(message, verdict: Classification) -> None:
    """Hook for A-7's one-and-only-one user notification."""
    log.warning(
        "outbox message dead after %s attempts: kind=%s reason=%s",
        message.attempts,
        message.kind,
        verdict.reason,
    )
