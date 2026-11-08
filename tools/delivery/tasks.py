"""Celery tasks of the delivery code: the share fan-out and announcement
activation. The ranking tasks (the daily runs, project seeding, team-profile
recompute) and target selection live in ``tools.recommendation.tasks``."""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="apps.content.fanout_relevance")
def fanout_relevance(share_id: str) -> dict:
    """Score a shared item against each other project member (Feature F).

    The async arm of the cross-member fan-out (used when ``FANOUT_ASYNC`` is on);
    embeds any member whose profile vector is missing.
    """
    from tools.delivery.fanout import fan_out_relevance
    from tools.delivery.models import ProjectShare

    share = (
        ProjectShare.objects.filter(id=share_id)
        .select_related("project", "content")
        .first()
    )
    if share is None:
        return {"error": "share_not_found", "share_id": str(share_id)}
    return fan_out_relevance(share, embed_missing=True)


@shared_task(name="apps.content.activate_announcements")
def activate_announcements(kind: str, target_id: str) -> dict:
    """Post a target's activation seed and closing-soon list (plan D5), off the
    request that switched announcements on: the editor is a model call per item."""
    from tools.delivery import announcement_setup

    return announcement_setup.activate_target(kind, target_id)


def enqueue_activation(kind: str, target_id) -> bool:
    """Best effort: a missing broker means tonight's run does the seed instead."""
    try:
        activate_announcements.delay(kind, str(target_id))
        return True
    except Exception:
        logger.warning("could not enqueue announcement activation", exc_info=True)
        return False
