"""Celery tasks: the turn, and the Beat sweeps (learning, resume, retention)."""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)

#: A turn whose thread has shown no activity this long is presumed dead.
STUCK_AFTER = timedelta(minutes=10)


@shared_task(name="tools.agent.tasks.run_turn")
def run_turn(thread_id: str) -> str:
    from . import loop

    return loop.run_turn(thread_id)


@shared_task(name="tools.agent.tasks.resume_stuck_turns")
def resume_stuck_turns() -> int:
    """Restart turns left ``running`` by a crash. The loop resumes from the log:
    calls without results run, then the model is asked again."""
    from .models import AgentThread

    cutoff = timezone.now() - STUCK_AFTER
    stuck = list(
        AgentThread.objects.filter(
            state="running", last_activity_at__lt=cutoff
        ).values_list("pk", flat=True)
    )
    for pk in stuck:
        run_turn.delay(str(pk))
    return len(stuck)


@shared_task(name="tools.agent.tasks.retention_sweep")
def retention_sweep() -> int:
    from . import config
    from .models import AgentThread

    days = int(config.get("retention_days") or 0)
    if days <= 0:
        return 0
    cutoff = timezone.now() - timedelta(days=days)
    deleted, _ = AgentThread.objects.filter(last_activity_at__lt=cutoff).delete()
    return deleted


@shared_task(name="tools.agent.tasks.learn_from_quiet_threads")
def learn_from_quiet_threads() -> int:
    from . import learning

    return learning.run_pass()
