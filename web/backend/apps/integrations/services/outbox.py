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
    not_before: datetime | None = None,
    components: list | None = None,
) -> tuple[object, bool]:
    """Queue a direct message. The DM channel is resolved at *send* time.

    Deliberately not resolved here: a cached ``dm_channel_id`` can go stale between
    queueing and delivery, and re-resolving costs one request only on the attempt that
    actually happens.

    ``not_before`` holds the row until the recipient's local send hour
    (:func:`apps.content.delivery.send_time`); see :func:`resolve.enqueue_outbox`.
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
        not_before=not_before,
        components=components,
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
    attachment_path: str = "",
    attachment_filename: str = "",
    subject_type: str = "",
    subject_id: str = "",
    not_before: datetime | None = None,
) -> tuple[object, bool]:
    """Queue a channel post, optionally carrying a file.

    Attachments are held as a **path**, not bytes — the same contract as
    :func:`enqueue_dm`, and for the same reason: a queued row may wait minutes for
    the drain, so the file lives in ``DISCORD_OUTBOX_ATTACHMENT_DIR`` and the
    retention sweep removes it once the row settles. :func:`deliver_one` branches on
    the path alone, never on the target type, so a channel attachment takes exactly
    the multipart path a DM attachment already did.
    """
    return resolve.enqueue_outbox(
        dedupe_key=dedupe_key,
        kind=kind,
        target_type=resolve.OUTBOX_CHANNEL,
        channel_id=str(channel_id),
        lab=lab,
        content=content,
        embed=embed,
        allowed_mentions=allowed_mentions,
        attachment_path=attachment_path,
        attachment_filename=attachment_filename,
        subject_type=subject_type,
        subject_id=subject_id,
        not_before=not_before,
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
            resp = discord_api.create_message(
                channel_id,
                **payload,
                **({"components": message.components} if message.components else {}),
            )
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
        # A permanent failure is the *more* actionable of the two — "your DMs are
        # closed" is something the person can fix today — so it is reported just
        # like an exhausted one.
        _notify_undelivered(message, verdict)
        return

    max_attempts = getattr(settings, "DISCORD_OUTBOX_MAX_ATTEMPTS", 5)
    if message.attempts >= max_attempts:
        resolve.mark_outbox_dead(
            message, error_code=verdict.error_code, reason=reason, now=now
        )
        result.dead += 1
        _notify_undelivered(message, verdict)
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
        return

    # A channel we cannot post to is a fact about the binding, and the queue is
    # often the first to learn it — sooner than the nightly sweep. Recording it here
    # is what stops the same message being retried into a void every day, and is
    # what the portal reads to explain the silence.
    channel_failures = (
        Reason.NO_PERMISSION,
        Reason.NO_ACCESS,
        Reason.CHANNEL_GONE,
        Reason.GUILD_GONE,
    )
    if verdict.reason in channel_failures and message.channel_id:
        # Every route posting to this channel learns it at once: the daily summary
        # and the report chunks that follow it share one updates route, and a lab
        # bound in two servers never shares a channel id across them.
        resolve.set_channel_health_by_channel(
            message.channel_id, ok=False, error_code=verdict.error_code
        )


def _notify_undelivered(message, verdict: Classification) -> None:
    """Tell the affected person, once, in the Mycelium app.

    Imported lazily and by service module rather than by model: the queue must not
    reach the ORM directly (the boundary test enforces it), and a top-level import
    would put ``integrations`` and ``content`` in a cycle. A failure to notify must
    never turn one undelivered message into a broken drain, so it is swallowed.
    """
    log.warning(
        "outbox message dead after %s attempts: kind=%s reason=%s",
        message.attempts,
        message.kind,
        verdict.reason,
    )
    try:
        from apps.content.delivery_failures import notify_delivery_failed

        notify_delivery_failed(
            outbox_id=message.pk,
            reason=str(verdict.reason or ""),
            target_type=message.target_type,
            recipient_user=message.recipient_user,
            lab=message.lab,
            kind=message.kind,
        )
    except Exception:  # noqa: BLE001 — never let the notice sink the drain
        log.exception("could not record a delivery-failure notice")


# --------------------------------------------------------------------------- #
# Retention
# --------------------------------------------------------------------------- #
def purge(*, now: datetime | None = None) -> dict:
    """Drop delivered rows past their retention window, and their attachments.

    Only successes are purged. A failed or dead row is the record of what went wrong
    and for whom — deleting it would throw away the evidence exactly when someone is
    trying to work out why a report never arrived.

    The database and the filesystem are settled in that order deliberately: a file
    left behind is recoverable litter, whereas a deleted file whose row survived would
    make the outbox promise an attachment it can no longer read.
    """
    now = now or timezone.now()
    days = int(getattr(settings, "DISCORD_OUTBOX_RETENTION_DAYS", 30))
    paths = resolve.purge_outbox(before=now - timedelta(days=days))

    removed = 0
    for raw in paths:
        try:
            Path(raw).unlink(missing_ok=True)
            removed += 1
        except OSError:  # a stale mount or a path we no longer own
            log.warning("could not remove outbox attachment: %s", raw)
    return {"rows": len(paths), "files_removed": removed}
