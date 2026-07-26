"""Celery tasks for the Discord integration.

All fire-and-forget, out of any request path:

* ``post_discord_incident`` — the actual ERROR_CHANNEL POST (the sink enqueues it).
* ``probe_identity`` — the DM reachability probe, with backoff on 429/5xx.
* ``reconcile_discord`` — the nightly presence + token-health sweep.
* ``drain_outbox`` — the outbound queue's worker, every minute on Beat.

None import a model; DB access is via ``services.resolve``.
"""

from __future__ import annotations

import logging

from celery import shared_task

from .services import errors, outbox, probe, reconcile, resolve

logger = logging.getLogger("mycelium.integrations.discord")

_PROBE_MAX_RETRIES = 3


@shared_task(name="apps.integrations.post_discord_incident")
def post_discord_incident(
    title: str, body: str, severity: str, fields: dict | None = None
) -> bool:
    return errors.post_embed(title, body, severity=severity, fields=fields or {})


@shared_task(
    name="apps.integrations.probe_identity",
    bind=True,
    max_retries=_PROBE_MAX_RETRIES,
)
def probe_identity(self, identity_id: int) -> dict:
    identity = resolve.get_identity(identity_id)
    if identity is None:
        return {"status": "gone"}

    result = probe.run_probe(identity)
    if result.transient:
        if self.request.retries < _PROBE_MAX_RETRIES:
            countdown = int(result.retry_after or (2 ** self.request.retries) * 5)
            raise self.retry(countdown=countdown)
        # Retries exhausted: reachability unknown + alert.
        probe.mark_unknown(identity)
        errors.note_incident(
            "probe", "exhausted", detail="DM probe gave up after retries"
        )
        return {"status": "unknown"}
    return {"status": "ok", "dm_ok": result.dm_ok}


@shared_task(name="apps.integrations.reconcile_discord")
def reconcile_discord() -> dict:
    return reconcile.reconcile()


@shared_task(name="apps.integrations.drain_outbox")
def drain_outbox() -> dict:
    """Deliver whatever is due in the outbound queue.

    Retry state lives in the rows, not in Celery: a message that fails carries its own
    ``next_attempt_at``, so this task never retries itself and a missed run costs a
    minute of latency rather than a lost message.
    """
    return outbox.drain().as_dict()
