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

from .opportunities import run_daily_opportunities_batch
from .pipeline import DEFAULT_SUGGESTIONS, run_daily_batch
from .runlog import new_run_log

logger = logging.getLogger(__name__)


def select_users(usernames: list[str] | None) -> list[User]:
    """Active users to run for: all of them, or just the named ones."""
    queryset = User.objects.filter(is_active=True).select_related("profile")
    if usernames:
        queryset = queryset.filter(username__in=usernames)
    return list(queryset.order_by("id"))


def select_targets(usernames: list[str] | None) -> tuple[list, list]:
    """The labs and lab-scoped projects to also match on a full run.

    Every lab and every lab project is a scoring target; the matcher short-circuits
    cheaply for any that have not declared a focus, so passing them all is safe. A
    *targeted* run (``usernames`` given) stays user-scoped and returns nothing here.
    """
    if usernames:
        return [], []
    from apps.accounts.models import Lab
    from apps.research.models import Project

    labs = list(Lab.objects.select_related("profile", "watch").order_by("id"))
    projects = list(Project.objects.filter(scope_lab__isnull=False).order_by("id"))
    return labs, projects


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
    labs, projects = select_targets(usernames)
    runlog = new_run_log(settings.DAILY_SUGGESTIONS_LOG_DIR, label="beat")
    runlog.line(
        f"daily run start: {len(users)} user(s), {len(labs)} lab(s), "
        f"{len(projects)} project(s)"
    )
    logger.info("daily suggestions run log: %s", runlog.path)
    try:
        batch = run_daily_batch(
            users,
            labs=labs,
            projects=projects,
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


@shared_task(name="apps.content.run_daily_opportunities")
def run_daily_opportunities(
    usernames: list[str] | None = None,
    *,
    ingest: bool = True,
    prune: bool = True,
    embed: bool = True,
) -> dict:
    """Refresh + prune the Pivot corpus, then match opportunities per user.

    Covers grants, conferences, and fellowships.  Fellowships are matched via the
    deterministic rule engine (no LLM call) and are always included.

    The opportunity twin of :func:`run_daily_suggestions`, wired to its own 1am
    Beat schedule. Ingest is best-effort (a no-op without a saved Pivot session),
    so the job reliably re-matches and prunes the existing corpus every night.
    """
    users = select_users(usernames)
    labs, projects = select_targets(usernames)
    runlog = new_run_log(settings.DAILY_SUGGESTIONS_LOG_DIR, label="opportunities")
    runlog.line(
        f"daily opportunities start: {len(users)} user(s), {len(labs)} lab(s), "
        f"{len(projects)} project(s)"
    )
    logger.info("daily opportunities run log: %s", runlog.path)
    try:
        batch = run_daily_opportunities_batch(
            users,
            labs=labs,
            projects=projects,
            areas=("grants", "conferences", "fellowships"),
            ingest=ingest,
            prune=prune,
            embed=embed,
            log=runlog.line,
        )
        for result in batch.results:
            runlog.line(
                f"[{result.username}:{result.area}] done: {result.status} "
                f"({result.suggestions} scored, {result.new} new)"
            )
        runlog.line("daily opportunities complete")
    finally:
        runlog.close()
    return batch.as_dict()


@shared_task(name="apps.content.scan_and_recommend_for_user")
def scan_and_recommend_for_user(username: str) -> dict:
    """Scan one user's watch topics and recommend — the sign-up background scan.

    Fired by :func:`apps.content.scan_status.trigger_paper_scan` when a new user's
    latest-batch match was too thin. Runs :func:`~apps.content.pipeline.run_for_user`
    (scan their topics → embed → recommend the fresh batch), then clears the
    "scanning" flag so the Research Papers page shows the results. The flag is
    cleared even on failure (it also TTLs out) so the page can never wedge on
    "scanning".
    """
    from .pipeline import run_for_user
    from .scan_status import clear_paper_scan_inflight

    user = (
        User.objects.filter(username=username).select_related("profile").first()
    )
    if user is None:
        return {"error": "user_not_found", "username": username}
    try:
        return run_for_user(user).as_dict()
    finally:
        clear_paper_scan_inflight(user)


@shared_task(name="apps.content.fanout_relevance")
def fanout_relevance(share_id: str) -> dict:
    """Score a shared item against each other project member (Feature F).

    The async arm of the cross-member fan-out (used when ``FANOUT_ASYNC`` is on);
    embeds any member whose profile vector is missing.
    """
    from .fanout import fan_out_relevance
    from .models import ProjectShare

    share = (
        ProjectShare.objects.filter(id=share_id)
        .select_related("project", "content")
        .first()
    )
    if share is None:
        return {"error": "share_not_found", "share_id": str(share_id)}
    return fan_out_relevance(share, embed_missing=True)


@shared_task(name="apps.content.recompute_project_profiles")
def recompute_project_profiles(project_ids: list[str] | None = None) -> dict:
    """Recompute team profiles for the given projects, or all of them (Feature D).

    The nightly / on-demand batch arm of the team signal; embeds members whose
    profile vector is missing. A failure for one project never sinks the run.
    """
    from apps.research.models import Project

    from .models import ProjectProfile
    from .team_profile import recompute_project_profile

    queryset = Project.objects.all()
    if project_ids:
        queryset = queryset.filter(id__in=project_ids)
    done = 0
    for project in queryset.iterator():
        try:
            recompute_project_profile(
                project,
                reason=ProjectProfile.Reason.ENGAGEMENT,
                embed_missing=True,
            )
            done += 1
        except Exception:  # pragma: no cover - one bad project never sinks the run
            logger.warning(
                "team-profile recompute failed for project %s",
                project.id,
                exc_info=True,
            )
    return {"recomputed": done}
