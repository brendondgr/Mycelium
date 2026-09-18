"""The transient raw-message buffer — the one place a person's words exist.

Everything else in this app stores Mylo's account of what was said. This module
stores what was actually said, and it stores it in Redis, under a TTL measured
in hours, keyed per message. It is deleted explicitly once a window has been
read; the TTL is the safety net for the night that never runs.

**Nothing here is ever written to Postgres, a disk, or a backup.** That is the
whole point, and it is why the buffer has no index of its own: the index is
:class:`~apps.ambient.models.RawMessageRef`, which holds external ids and
timestamps and no body at all. A window is assembled by asking Postgres *which*
messages fall in a range and then asking Redis for whatever bodies are still
alive. A body that has expired simply does not come back, and the window is
read without it — which is the correct behaviour, not a degraded one.

Writes and reads are best-effort. A Redis outage costs a night's extraction,
which Plan 04 retries; it must never raise into the gateway path that is
receiving messages, and it must never cause a message to be kept somewhere else.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.cache import caches

logger = logging.getLogger(__name__)

_CACHE_ALIAS = "ambient"
_KEY_PREFIX = "raw"


def _cache():
    return caches[_CACHE_ALIAS]


def ttl_seconds(source=None) -> int:
    """How long a body may live, in seconds, clamped to the hard ceiling.

    A :class:`~apps.ambient.models.Source` may set ``raw_ttl_hours`` to shorten
    its own window. It can never lengthen it past ``AMBIENT_RAW_TTL_HOURS_MAX``,
    so "Mylo does not keep your messages" holds for every source however it is
    configured — including one edited straight in the database.
    """
    ceiling = int(getattr(settings, "AMBIENT_RAW_TTL_HOURS_MAX", 24))
    default = int(getattr(settings, "AMBIENT_RAW_TTL_HOURS", 6))
    hours = default
    override = getattr(source, "raw_ttl_hours", None)
    if override:
        hours = int(override)
    hours = max(1, min(hours, ceiling))
    return hours * 3600


def key(source_id: int, external_id: str) -> str:
    """The buffer key for one message. Scoped by source so ids cannot collide."""
    return f"{_KEY_PREFIX}:{source_id}:{external_id}"


def put(source_id: int, external_id: str, text: str, *, ttl: int) -> bool:
    """Hold one message body for ``ttl`` seconds. False if it could not be held."""
    try:
        _cache().set(key(source_id, external_id), text, timeout=ttl)
        return True
    except Exception:  # pragma: no cover - Redis down: degrade, never raise
        logger.warning("ambient buffer write failed for %s", external_id, exc_info=True)
        return False


def get(source_id: int, external_id: str) -> str | None:
    """One message body, or None if it has expired or was never held."""
    try:
        return _cache().get(key(source_id, external_id))
    except Exception:  # pragma: no cover - Redis down: degrade, never raise
        logger.warning("ambient buffer read failed for %s", external_id, exc_info=True)
        return None


def get_many(source_id: int, external_ids) -> dict[str, str]:
    """The bodies still alive for ``external_ids``, keyed by external id.

    Missing ids are simply absent. The caller must treat a short result as
    normal — it is what a TTL doing its job looks like.
    """
    ids = list(external_ids)
    if not ids:
        return {}
    keys = {key(source_id, external_id): external_id for external_id in ids}
    try:
        found = _cache().get_many(list(keys))
    except Exception:  # pragma: no cover - Redis down: degrade, never raise
        logger.warning("ambient buffer window read failed", exc_info=True)
        return {}
    return {keys[cache_key]: text for cache_key, text in found.items()}


def drop(source_id: int, external_ids) -> None:
    """Delete bodies explicitly, the moment a window has been read.

    This is the primary deletion path. The TTL exists only for the messages this
    never reaches.
    """
    ids = list(external_ids)
    if not ids:
        return
    try:
        _cache().delete_many([key(source_id, external_id) for external_id in ids])
    except Exception:  # pragma: no cover - Redis down: degrade, never raise
        logger.warning("ambient buffer delete failed", exc_info=True)
