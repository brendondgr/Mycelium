"""The sweep that keeps the ledger from remembering more than it needs to.

Two different things expire, for two different reasons.

**Bodies** expire in Redis, by TTL, within hours. The sweep does not manage
them — it only clears the ``buffered_until`` stamps of bodies that have already
gone, so a reference never claims to have a body it does not.

**References** expire here. A :class:`~apps.ambient.models.RawMessageRef` holds
ids and timestamps and no text, but a permanent record of every message id and
the minute it was sent is still a record of who talked when, and this feature
has no use for one. They are kept only as long as they are useful: long enough
to spot a repeat, long enough to reconcile an edit or a deletion that arrives
late. After that they go.

**Observations are never touched by this sweep.** They are the person's own
record and they leave only when the person removes them (:mod:`.reconcile`).
That is the "and nothing else" in Plan 01's acceptance criteria.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import RawMessageRef

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SweepResult:
    """What one sweep did, so the task can log a number rather than a hope."""

    refs_deleted: int = 0
    stamps_cleared: int = 0


def ref_retention_days() -> int:
    """How long a reference is kept, in days.

    Never shorter than the repeat window plus a day, nor than the attention
    window plus a day: a reference that vanishes while its hash could still
    match would silently turn a repeat back into new evidence, and one that
    vanishes inside the attention window would quietly skew a share — bugs that
    would look like nothing at all from the outside.
    """
    configured = int(getattr(settings, "AMBIENT_REF_RETENTION_DAYS", 45))
    repeat_window = int(getattr(settings, "AMBIENT_REPEAT_WINDOW_DAYS", 30))
    # Attention share reads 28 days of attributed references, so they must
    # outlive that window too — a share computed over a history the sweep has
    # half-deleted would be wrong in a way nobody would notice.
    from .attention import LONG_DAYS

    return max(configured, repeat_window + 1, LONG_DAYS + 1)


def sweep(now=None) -> SweepResult:
    """Delete references past the retention window; clear dead buffer stamps."""
    now = now or timezone.now()
    cutoff = now - timedelta(days=ref_retention_days())

    expired = RawMessageRef.objects.filter(sent_at__lt=cutoff)
    refs_deleted = expired.count()
    if refs_deleted:
        expired.delete()

    stamps_cleared = RawMessageRef.objects.filter(
        buffered_until__lt=now
    ).update(buffered_until=None)

    if refs_deleted or stamps_cleared:
        logger.info(
            "ambient sweep: %s references past %s days, %s expired buffer stamps",
            refs_deleted,
            ref_retention_days(),
            stamps_cleared,
        )
    return SweepResult(refs_deleted=refs_deleted, stamps_cleared=stamps_cleared)
