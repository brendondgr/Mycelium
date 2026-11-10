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
    """Threads untouched for ``retention_days`` (DMs and per-person channel
    conversations included), and the conversation of an announcement closed
    more than ``discord_closed_thread_days`` ago (plan D)."""
    from . import config
    from .models import AgentThread

    deleted = closed_announcement_sweep()
    # A public-demo visitor's question lives a day (apps.demo).
    demo_cutoff = timezone.now() - timedelta(hours=24)
    gone, _ = (
        AgentThread.objects.exclude(demo_visitor="")
        .filter(last_activity_at__lt=demo_cutoff)
        .delete()
    )
    deleted += gone
    days = int(config.get("retention_days") or 0)
    if days <= 0:
        return deleted
    cutoff = timezone.now() - timedelta(days=days)
    gone, _ = AgentThread.objects.filter(last_activity_at__lt=cutoff).delete()
    return deleted + gone


def closed_announcement_sweep(now=None) -> int:
    """Delete the shared conversations of announcements closed long enough."""
    from datetime import datetime

    from tools._framework import services

    from . import config
    from .models import AgentThreadLink

    days = int(config.get("discord_closed_thread_days") or 0)
    read = services.get("delivery", "read")
    if days <= 0 or read is None:
        return 0
    cutoff = (now or timezone.now()) - timedelta(days=days)
    deleted = 0
    links = AgentThreadLink.objects.filter(anchor__kind="announcement").select_related(
        "thread"
    )
    for link in links:
        post = read.announcement_post_for_thread(link.place_id)
        if not post or not post.get("closed_at"):
            continue
        if datetime.fromisoformat(post["closed_at"]) < cutoff:
            link.thread.delete()
            deleted += 1
    return deleted


@shared_task(name="tools.agent.tasks.learn_from_quiet_threads")
def learn_from_quiet_threads() -> int:
    from . import learning

    return learning.run_pass()
