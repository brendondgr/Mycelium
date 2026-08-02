"""Cross-member relevance fan-out — Feature F.

When a paper enters a project (share or paste-a-link), score it against each *other*
member's individual profile and record a :class:`~apps.content.models.MemberSuggestion`
for each: ``suggested=True`` (above the cosine floor → delivered in-app) or
``suggested=False`` (a persisted, audited abstention). The threshold reads the
**normalized cosine directly** — never an RRF rank (RRF ranks aren't calibrated for
absolute thresholding). One row per ``(user, content)``: re-sharing never re-notifies.

Cosine is pure-Python (no numpy). The sharer is never suggested to themselves.
"""

from __future__ import annotations

import logging
import math

from django.conf import settings

from apps.accounts.embedding import canonical_text

from . import embeddings
from .models import MemberSuggestion

logger = logging.getLogger(__name__)


def cosine(a, b) -> float:
    """Pure-Python cosine similarity; ``0.0`` for an empty or zero vector.

    Shared with :mod:`apps.content.member_fit`, which thresholds on the same
    absolute similarity to shortlist who an item is for.
    """
    if not a or not b:
        return 0.0
    dot = sum(float(x) * float(y) for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(float(x) * float(x) for x in a))
    nb = math.sqrt(sum(float(y) * float(y) for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


#: Legacy private alias — existing callers/tests inside this module.
_cosine = cosine


def member_vector(user, *, embed_missing: bool = True) -> list[float] | None:
    """A member's interest vector: stored ``Profile.embedding`` or embed on demand."""
    profile = getattr(user, "profile", None)
    if profile is None:
        return None
    if profile.embedding is not None:
        return list(profile.embedding)
    if not embed_missing:
        return None
    text = canonical_text(profile)
    if not text.strip():
        return None
    return embeddings.embed_text(text)


def fan_out_relevance(share, *, embed_missing: bool = True) -> dict:
    """Score a share's item against each other member; record MemberSuggestions.

    ``embed_missing`` off (the inline share-request path) scores only members with a
    stored profile vector, to bound latency; the batch task/command turns it on.
    """
    project = share.project
    item = share.content
    if item.embedding is None:
        # No abstract to match on — nothing to score against (embed_status != ok).
        return {"scored": 0, "suggested": 0, "reason": "no_embedding"}

    item_vec = list(item.embedding)
    floor = settings.FANOUT_COSINE_FLOOR
    recipients = [u for u in project.members.all() if u.id != share.shared_by_id]

    scored = 0
    suggested = 0
    for user in recipients:
        vector = member_vector(user, embed_missing=embed_missing)
        if vector is None:
            continue
        cosine = _cosine(item_vec, vector)
        scored += 1
        is_suggested = cosine >= floor
        # unique_together (user, content) — a prior share already decided this pair,
        # so re-sharing never double-notifies.
        _obj, created = MemberSuggestion.objects.get_or_create(
            user=user,
            content=item,
            defaults={
                "project": project,
                "origin_share": share,
                "score": cosine,
                "suggested": is_suggested,
                "floor_used": floor,
                "delivered_via": "in_app" if is_suggested else "",
            },
        )
        if created and is_suggested:
            suggested += 1
    return {"scored": scored, "suggested": suggested, "floor": floor}


def trigger_fanout(share) -> None:
    """Run fan-out for a new share — async via Celery or inline — never fatal.

    Inline (default) works without a running worker and scores stored profile
    vectors only; ``settings.FANOUT_ASYNC`` routes through Celery (embedding missing
    profiles on the worker). A failure here must never break the share itself.
    """
    try:
        if settings.FANOUT_ASYNC:
            from .tasks import fanout_relevance

            fanout_relevance.delay(str(share.id))
        else:
            fan_out_relevance(share, embed_missing=False)
    except Exception:  # pragma: no cover - defensive; the share already committed
        logger.warning("fan-out failed for share %s", share.id, exc_info=True)
