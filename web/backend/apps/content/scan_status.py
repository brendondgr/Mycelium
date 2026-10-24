"""The "paper scan in flight" flag for the sign-up hybrid.

At sign-up a new user is matched against the latest gather batch already in the
store (:mod:`.onboarding_match`). When that batch is too thin, we kick off a
background literature scan of the user's watch topics and want the Research Papers
page to say "scanning new articles for you" until it lands. The web process sets
the flag; the Celery worker clears it when the scan finishes — so the flag must
live in a **shared** cache (the ``scan`` alias, Redis-backed), not the per-process
default LocMemCache.

Everything here is **best-effort**: a Redis outage (or a missing broker) degrades
to "no scanning state" rather than raising in the request path. The flag also
carries a TTL (``PAPER_SCAN_INFLIGHT_TTL``) so a scan that dies without clearing it
can never wedge the page on "scanning" forever.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import caches

logger = logging.getLogger(__name__)

_CACHE_ALIAS = "scan"


def _key(user: User) -> str:
    return f"paper_scan_inflight:{user.pk}"


def mark_paper_scan_inflight(user: User) -> None:
    """Flag that a background paper scan is running for ``user`` (best-effort)."""
    ttl = getattr(settings, "PAPER_SCAN_INFLIGHT_TTL", 1800)
    try:
        caches[_CACHE_ALIAS].set(_key(user), "1", timeout=ttl)
    except Exception:  # pragma: no cover - Redis down: degrade, never raise
        logger.warning("could not set paper-scan flag for %s", user.pk, exc_info=True)


def clear_paper_scan_inflight(user: User) -> None:
    """Clear the flag once the background scan has landed (best-effort)."""
    try:
        caches[_CACHE_ALIAS].delete(_key(user))
    except Exception:  # pragma: no cover - Redis down: degrade, never raise
        logger.warning(
            "could not clear paper-scan flag for %s", user.pk, exc_info=True
        )


def is_paper_scan_inflight(user: User) -> bool:
    """Whether a background paper scan is currently running for ``user``.

    Best-effort: a Redis outage reads as "not scanning" so the page still renders.
    """
    try:
        return bool(caches[_CACHE_ALIAS].get(_key(user)))
    except Exception:  # pragma: no cover - Redis down: degrade, never raise
        logger.warning("could not read paper-scan flag for %s", user.pk, exc_info=True)
        return False


def _project_key(project_id) -> str:
    return f"project_seed_inflight:{project_id}"


def mark_project_seed_inflight(project_id) -> None:
    """Flag that a project's initial recommendation seeding is running (best-effort)."""
    ttl = getattr(settings, "PAPER_SCAN_INFLIGHT_TTL", 1800)
    try:
        caches[_CACHE_ALIAS].set(_project_key(project_id), "1", timeout=ttl)
    except Exception:  # pragma: no cover - Redis down: degrade, never raise
        logger.warning(
            "could not set project-seed flag for %s", project_id, exc_info=True
        )


def clear_project_seed_inflight(project_id) -> None:
    """Clear the project-seed flag once seeding has landed (best-effort)."""
    try:
        caches[_CACHE_ALIAS].delete(_project_key(project_id))
    except Exception:  # pragma: no cover - Redis down: degrade, never raise
        logger.warning(
            "could not clear project-seed flag for %s", project_id, exc_info=True
        )


def is_project_seed_inflight(project_id) -> bool:
    """Whether a project's recommendations are still being seeded (best-effort)."""
    try:
        return bool(caches[_CACHE_ALIAS].get(_project_key(project_id)))
    except Exception:  # pragma: no cover - Redis down: degrade, never raise
        logger.warning(
            "could not read project-seed flag for %s", project_id, exc_info=True
        )
        return False


def trigger_paper_scan(user: User, *, enqueue=None) -> bool:
    """Flag ``user`` as scanning and enqueue the background scan (best-effort).

    Returns ``True`` when the scan was handed off. ``enqueue`` is an injectable seam
    (tests pass a fake; production defaults to the Celery task) taking the username.
    If the hand-off fails — no broker, Celery down — the flag is cleared and this
    returns ``False`` so the UI does not promise a scan that will never run.
    """
    mark_paper_scan_inflight(user)
    try:
        if enqueue is None:
            from .tasks import scan_and_recommend_for_user

            def enqueue(username: str) -> None:
                scan_and_recommend_for_user.delay(username)

        enqueue(user.get_username())
        return True
    except Exception:
        logger.warning(
            "could not enqueue paper scan for %s", user.get_username(), exc_info=True
        )
        clear_paper_scan_inflight(user)
        return False
