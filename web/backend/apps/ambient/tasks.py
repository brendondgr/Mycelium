"""Scheduled work for the ambient ledger.

One task for now: the retention sweep. It is idempotent, it holds no state of
its own, and a missed run costs nothing but a day of references living slightly
longer than they should — so it is safe to run on Beat and safe to run by hand.
"""

from __future__ import annotations

import logging

from celery import shared_task

from . import attention, retention

logger = logging.getLogger(__name__)


@shared_task(name="apps.ambient.sweep_retention")
def sweep_retention() -> dict[str, int]:
    """Delete message references past the retention window."""
    result = retention.sweep()
    return {
        "refs_deleted": result.refs_deleted,
        "stamps_cleared": result.stamps_cleared,
    }


@shared_task(name="apps.ambient.recompute_attention")
def recompute_attention() -> int:
    """Rebuild every person's 7- and 28-day attention share per project."""
    return attention.recompute()
