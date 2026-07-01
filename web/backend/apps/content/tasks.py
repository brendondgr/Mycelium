"""Celery entry point for the daily research-suggestion pipeline.

Runs :func:`apps.content.pipeline.run_for_user` for each selected user. Scoped to
all active users by default; pass ``usernames`` to limit it (the daily Beat
schedule and the management command both call through here). A failure for one
user is logged and skipped so one bad profile never sinks the whole batch.
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.conf import settings
from django.contrib.auth.models import User

from .pipeline import DEFAULT_SUGGESTIONS, run_for_user
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
) -> list[dict]:
    """Run the pipeline for every selected user; return each user's summary."""
    users = select_users(usernames)
    results: list[dict] = []
    runlog = new_run_log(settings.DAILY_SUGGESTIONS_LOG_DIR, label="beat")
    runlog.line(f"daily run start: {len(users)} user(s)")
    logger.info("daily suggestions run log: %s", runlog.path)
    try:
        for user in users:
            try:
                result = run_for_user(
                    user,
                    days_back=days_back,
                    days_forward=days_forward,
                    sources=sources,
                    query_limit=query_limit,
                    top_k=top_k,
                    suggestion_limit=suggestion_limit,
                    embed=embed,
                    log=runlog.line,
                )
            except Exception:
                logger.exception("daily suggestions failed for %s", user.get_username())
                runlog.line(f"[{user.get_username()}] ERROR (see worker log)")
                results.append({"username": user.get_username(), "status": "error"})
            else:
                runlog.line(
                    f"[{result.username}] done: {result.status} "
                    f"({result.suggestions} suggestions)"
                )
                results.append(result.as_dict())
        runlog.line("daily run complete")
    finally:
        runlog.close()
    return results
