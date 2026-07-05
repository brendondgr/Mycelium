"""Celery entry point for the daily research-suggestion pipeline.

Runs :func:`apps.content.pipeline.run_daily_batch`: **one** global ingest (gather
every selected user's watch topics, search + embed once) followed by a per-user
recommend pass — so a topic shared by many users is searched once, not per user.
Scoped to all active users by default; pass ``usernames`` to limit it (the daily
Beat schedule and the management command both call through here). A failure for
one user is caught inside the batch so one bad profile never sinks the run.
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.conf import settings
from django.contrib.auth.models import User

from .pipeline import DEFAULT_SUGGESTIONS, run_daily_batch
from .runlog import new_run_log

logger = logging.getLogger(__name__)


def select_users(usernames: list[str] | None) -> list[User]:
    """Active users to run for: all of them, or just the named ones."""
    queryset = User.objects.filter(is_active=True).select_related("profile")
    if usernames:
        queryset = queryset.filter(username__in=usernames)
    return list(queryset.order_by("id"))


@shared_task(name="apps.content.run_daily_suggestions")
def run_daily_suggestions(
    usernames: list[str] | None = None,
    *,
    days_back: int = 2,
    days_forward: int = 7,
    sources: list[str] | None = None,
    query_limit: int = 6,
    top_k: int = 20,
    suggestion_limit: int = DEFAULT_SUGGESTIONS,
    embed: bool = True,
) -> dict:
    """Ingest once, then recommend per user; return the ingest + per-user summary."""
    users = select_users(usernames)
    runlog = new_run_log(settings.DAILY_SUGGESTIONS_LOG_DIR, label="beat")
    runlog.line(f"daily run start: {len(users)} user(s)")
    logger.info("daily suggestions run log: %s", runlog.path)
    try:
        batch = run_daily_batch(
            users,
            days_back=days_back,
            days_forward=days_forward,
            sources=sources,
            query_limit=query_limit,
            top_k=top_k,
            suggestion_limit=suggestion_limit,
            embed=embed,
            log=runlog.line,
        )
        for result in batch.results:
            runlog.line(
                f"[{result.username}] done: {result.status} "
                f"({result.suggestions} suggestions)"
            )
        runlog.line("daily run complete")
    finally:
        runlog.close()
    return batch.as_dict()
