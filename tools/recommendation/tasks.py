"""Celery entry point for the daily research-suggestion pipeline.

Runs :func:`tools.recommendation.pipeline.run_daily_batch`: **one** global ingest
(gather
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

from tools.recommendation.opportunities import run_daily_opportunities_batch
from tools.recommendation.pipeline import DEFAULT_SUGGESTIONS, run_daily_batch
from tools.recommendation.runlog import new_run_log

logger = logging.getLogger(__name__)


def select_users(usernames: list[str] | None) -> list[User]:
    """Active users entitled to scheduled delivery — the chokepoint for both dailies.

    A Free account is an on-demand product: it searches and scores when asked but is
    never pushed a scheduled run. So the daily pipelines only run for users who hold
    ``SCHEDULED_REPORTS`` (Spore and up). This one filter covers both the paper and
    the opportunity pipelines. Entitlement is resolved in bulk to avoid an N+1.
    """
    from apps.billing.entitlements import Feature, users_with_feature
    from apps.demo.world import nightly_users

    # The public demo's people are ranked only while the demo is served.
    queryset = nightly_users(
        User.objects.filter(is_active=True).select_related("profile")
    )
    if usernames:
        queryset = queryset.filter(username__in=usernames)
    users = list(queryset.order_by("id"))
    entitled = users_with_feature(
        Feature.SCHEDULED_REPORTS, user_ids=[u.id for u in users]
    )
    return [u for u in users if u.id in entitled]


#: Where the departments to score come from. A department has no feed of its
#: own: it is scored only because something built on recommendation needs its
#: slate (announcements register their enabled departments, see
#: :func:`register_department_source`). Recommendation never imports that code.
_DEPARTMENT_SOURCES: list = []


def register_department_source(source) -> None:
    """Add a zero-argument callable returning the departments it needs scored."""
    if source not in _DEPARTMENT_SOURCES:
        _DEPARTMENT_SOURCES.append(source)


def select_departments(usernames: list[str] | None) -> list:
    """Departments to score on a full run: whatever the registered sources ask
    for (today, those with announcements switched on and a plan that covers
    them), each once. A targeted run (``usernames`` given) scores none."""
    if usernames:
        return []
    from apps.demo.world import nightly_skipped_scopes

    _labs, seen = nightly_skipped_scopes()  # the demo's, while it is off
    seen = set(seen)
    out: list = []
    for source in _DEPARTMENT_SOURCES:
        for department in source():
            if department.pk not in seen:
                seen.add(department.pk)
                out.append(department)
    return out


def select_targets(usernames: list[str] | None) -> tuple[list, list]:
    """The labs and projects to also match on a full run.

    Institutional scoring targets are:

    * Labs on an **active** subscription (a lab-scoped plan, or a department plan
      covering the lab).
    * Those labs' projects, each department's projects, and the personal projects
      of scheduled-eligible users — but only the **active (non-archived)** ones that
      fit inside the owner's plan cap (oldest-first), so an archived project or one
      pushed over the limit by a downgrade never consumes daily budget.

    The matcher short-circuits cheaply for any target with no declared focus, so
    passing a focus-less project is safe. A *targeted* run (``usernames`` given)
    stays user-scoped and returns nothing here.
    """
    if usernames:
        return [], []
    from apps.accounts.models import Lab
    from apps.billing.models import Subscription
    from apps.research.limits import in_cap_ids
    from apps.research.models import Project

    active_lab_ids = set(
        Subscription.objects.filter(
            status=Subscription.Status.ACTIVE, scope_lab__isnull=False
        ).values_list("scope_lab_id", flat=True)
    )
    active_dept_ids = set(
        Subscription.objects.filter(
            status=Subscription.Status.ACTIVE, scope_department__isnull=False
        ).values_list("scope_department_id", flat=True)
    )
    # The public demo's lab and department, while the demo is off.
    from apps.demo.world import nightly_skipped_scopes

    skip_labs, skip_depts = nightly_skipped_scopes()
    active_lab_ids -= skip_labs
    active_dept_ids -= skip_depts
    labs = [
        lab
        for lab in Lab.objects.select_related("profile", "watch").order_by("id")
        if lab.id not in skip_labs
        and (lab.id in active_lab_ids or lab.department_id in active_dept_ids)
    ]

    # Collect the in-cap active project ids per scope owner. Each owner is only a
    # scoring owner if it currently holds a project cap (> 0), which mirrors the
    # creation gate exactly, so scoring and creation never disagree.
    keep_ids: set = set()
    for lab in labs:
        from apps.billing.entitlements import lab_project_cap

        keep_ids |= in_cap_ids("scope_lab", lab.id, lab_project_cap(lab))
    for dept_id in active_dept_ids:
        from apps.accounts.models import Department
        from apps.billing.entitlements import department_project_cap

        dept = Department.objects.filter(pk=dept_id).first()
        if dept is not None:
            keep_ids |= in_cap_ids(
                "scope_department", dept_id, department_project_cap(dept)
            )
    # Personal projects of scheduled-eligible users (Spore+): Free is on-demand
    # only, so its personal projects are seeded on create but never daily-pushed.
    for user in select_users(None):
        from apps.billing.entitlements import personal_project_cap

        keep_ids |= in_cap_ids("scope_user", user.id, personal_project_cap(user))

    projects = list(
        Project.objects.filter(id__in=keep_ids).order_by("id")
    )
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
    prune: bool = True,
) -> dict:
    """Prune the opportunity corpus, then match grants/conferences/fellowships per user.

    Covers grants, conferences, and fellowships.  Fellowships are matched via the
    deterministic rule engine (no LLM call) and are always included.

    The opportunity twin of :func:`run_daily_suggestions`. This task never
    scrapes: collection is its own scheduled stage (``tools.retrieval.collect``,
    plan Phase 12), invoked ahead of this one by ``manual_all.py``. It used to
    accept ``ingest``/``embed`` flags mirroring that scrape stage, but neither
    ever reached :func:`run_daily_opportunities_batch`'s prune branch or
    anything else in that function — they were dropped rather than kept as
    parameters with no effect.
    """
    users = select_users(usernames)
    labs, projects = select_targets(usernames)
    departments = select_departments(usernames)
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
            departments=departments,
            projects=projects,
            areas=("grants", "conferences", "fellowships"),
            prune=prune,
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

    Fired by :func:`tools.recommendation.scan_status.trigger_paper_scan` when a new
    user's
    latest-batch match was too thin. Runs
    :func:`~tools.recommendation.pipeline.run_for_user`
    (scan their topics → embed → recommend the fresh batch), then clears the
    "scanning" flag so the Research Papers page shows the results. The flag is
    cleared even on failure (it also TTLs out) so the page can never wedge on
    "scanning".
    """
    from apps.billing.entitlements import Feature, has_feature

    from tools.recommendation.pipeline import run_for_user
    from tools.recommendation.scan_status import clear_paper_scan_inflight

    user = (
        User.objects.filter(username=username).select_related("profile").first()
    )
    if user is None:
        return {"error": "user_not_found", "username": username}
    # Free keeps this on-demand signup scan (D6), but gets the deterministic,
    # semantic-only path: no LLM fit scoring. Topics are already capped on read.
    complete = None if has_feature(user, Feature.LLM_FIT_SCORING) else (lambda _p: None)
    try:
        return run_for_user(user, complete=complete).as_dict()
    finally:
        clear_paper_scan_inflight(user)


@shared_task(name="apps.content.seed_project_recommendations")
def seed_project_recommendations(project_id: str) -> dict:
    """Seed a freshly-created (or re-focused) project's recommendations.

    Runs a whole-corpus :func:`tools.recommendation.refitting.refit_project` — the same
    replace pass sign-up uses for a user — so the project's feed is populated from
    the existing corpus immediately (papers, grants, conferences, and
    interest-matched fellowships), with no scan/ingest. Clears the "seeding" flag
    when done (even on failure, so the page never wedges). Skips scoring for a
    project that has no declared focus (nothing to match).
    """
    from apps.research.models import Project

    from tools.recommendation.refitting import refit_project
    from tools.recommendation.scan_status import clear_project_seed_inflight

    project = Project.objects.filter(id=project_id).first()
    if project is None:
        return {"error": "project_not_found", "project_id": str(project_id)}
    try:
        from tools.recommendation.targets import project_interests

        if not project_interests(project)["areas"]:
            return {"skipped": "no_focus", "project_id": str(project_id)}
        return refit_project(project).as_dict()
    finally:
        clear_project_seed_inflight(project_id)


def enqueue_project_seed(project) -> bool:
    """Flag a project as seeding and hand the seed off to Celery (best-effort).

    Mirrors :func:`tools.recommendation.scan_status.trigger_paper_scan`: the flag lets
    the
    project page show a "Mylo is researching…" state, and a failed hand-off (no
    broker) clears it so the UI never promises a run that won't happen. A project
    with no declared focus is not seeded (nothing to match).
    """
    from tools.recommendation.scan_status import (
        clear_project_seed_inflight,
        mark_project_seed_inflight,
    )
    from tools.recommendation.targets import project_interests

    if not project_interests(project)["areas"]:
        return False
    mark_project_seed_inflight(project.id)
    try:
        seed_project_recommendations.delay(str(project.id))
        return True
    except Exception:
        logger.warning(
            "could not enqueue project seed for %s", project.id, exc_info=True
        )
        clear_project_seed_inflight(project.id)
        return False


@shared_task(name="apps.content.recompute_project_profiles")
def recompute_project_profiles(project_ids: list[str] | None = None) -> dict:
    """Recompute team profiles for the given projects, or all of them (Feature D).

    The nightly / on-demand batch arm of the team signal; embeds members whose
    profile vector is missing. A failure for one project never sinks the run.
    """
    from apps.research.models import Project

    from tools.recommendation.models import ProjectProfile
    from tools.recommendation.team_profile import recompute_project_profile

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
