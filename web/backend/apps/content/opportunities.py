"""Per-user grant & conference matching — the opportunity twin of the paper daily.

For one user and one area (grants or conferences) this reuses the paper pipeline's
retrieval + multi-interest fusion (:func:`apps.content.pipeline.fuse_interests_pool`,
scoped by ``content_type``) over the Pivot corpus, scores the top slice with the
opportunity-aware model (:mod:`.opportunity_llm`), tags brand-new high-fit items
(:mod:`.pinning`), and persists one :class:`RelevanceScore` per item — the same
store the paper digest uses, discriminated by ``content.type`` and a ``signals.area``.

The scoring *target* is a :class:`~apps.content.targets.MatchTarget` — a person, a
lab, or a lab project — so the same engine matches grants + conferences for any of
them; the query is built from the target's interests (research focus + keywords)
broadened by its watch topics. Fellowships stay user-only (individual eligibility).
Every seam degrades to a clear status instead of a crash.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass

from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone

from .fusion import DEFAULT_BETA
from .interests_query import SearchInterest, search_interests
from .models import ContentItem, RelevanceScore
from .opportunity_llm import (
    generate_fellowship_suggestions,
    generate_opportunity_suggestions,
)
from .pinning import DEFAULT_PERCENTILE, compute_pins
from .pipeline import PersistRow, fuse_interests_pool
from .targets import MatchTarget, target_for_user

logger = logging.getLogger(__name__)

DEFAULT_SURFACE = 25
DEFAULT_LLM_LIMIT = 10
DEFAULT_POOL_PER_INTEREST = 100
# How many per-(user, area) LLM scoring calls run at once. The model call is the
# slow step (a self-hosted vLLM can be ~100s/request), so scoring units serially
# is the dominant cost; the endpoint handles many at once. Overridable via
# settings.OPPORTUNITY_LLM_CONCURRENCY.
DEFAULT_LLM_CONCURRENCY = 12

# area -> ContentItem.type
AREAS: dict[str, str] = {
    "grants": ContentItem.Type.GRANT,
    "conferences": ContentItem.Type.CONFERENCE,
    "fellowships": ContentItem.Type.FELLOWSHIP,
}

# Which content types are surfaced by an embedding-match threshold (variable-length
# feed) instead of the legacy fixed top-``DEFAULT_SURFACE`` slice, and the setting
# that supplies each threshold. A type absent here keeps the fixed-slice behaviour.
_AREA_THRESHOLD_SETTING: dict[str, str] = {
    ContentItem.Type.GRANT: "GRANT_MATCH_THRESHOLD",
    ContentItem.Type.CONFERENCE: "CONFERENCE_MATCH_THRESHOLD",
    # Fellowships gate on the rule engine (fellowships.py), not this embedding path.
}


def _area_match_threshold(content_type: str) -> float | None:
    """The embedding-match floor for a content type, or ``None`` if it isn't gated.

    ``None`` keeps the old fixed top-``DEFAULT_SURFACE`` behaviour; a float switches
    the type to the variable-length threshold feed.
    """
    name = _AREA_THRESHOLD_SETTING.get(content_type)
    if name is None:
        return None
    return getattr(settings, name, 0.4)


def _opportunity_max_surface() -> int:
    """Backstop cap on how many opportunities a threshold feed may surface."""
    return getattr(settings, "OPPORTUNITY_MATCH_MAX_SURFACE", 250)


@dataclass
class OppRunResult:
    """A JSON-able report of one user's opportunity run for one area."""

    username: str
    area: str
    status: str  # ok | no_profile | no_interests | no_results
    retrieved: int = 0
    suggestions: int = 0
    llm: int = 0
    fallback: int = 0
    new: int = 0
    note: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _watch_topics(user: User) -> list[str]:
    watch = getattr(user, "watch", None)
    topics = getattr(watch, "topics", None) or []
    return [str(topic) for topic in topics]


def opportunity_search_interests(
    interests: dict, watch_topics: list[str]
) -> list[SearchInterest]:
    """Search interests for opportunity matching.

    Reuses the paper multi-interest builder but broadens it for opportunities: the
    user's declared ``areas`` drive the interests (as for papers), and their watch
    topics both stand in as interests when no areas are declared and sharpen every
    interest's lexical net.
    """
    interests = dict(interests or {})
    areas = interests.get("areas") or []
    if not areas and watch_topics:
        interests["areas"] = list(watch_topics)
    merged_keywords = list(interests.get("keywords") or []) + list(watch_topics)
    if merged_keywords:
        interests["keywords"] = merged_keywords
    return search_interests(interests)


@dataclass
class _MatchJob:
    """A prepared per-(target, area) unit, ready for the (parallel) LLM scoring step.

    The retrieve+fuse work (DB + embedder) is already done; scoring reads only
    these in-memory fields (the target carries the interests / profile_meta the
    model needs), so it touches no ORM/embedder and is safe to run in a worker
    thread alongside other units. ``username`` is the target's key (a username for
    a person, a slug/id for a lab or project) kept flat for the result label.
    """

    target: MatchTarget
    username: str
    area: str
    content_type: str
    pairs: list
    rows: list
    pool: int
    percentile: float
    llm_limit: int
    surface_limit: int | None  # None => surface all (threshold-gated areas)


@dataclass
class _FellowshipMatchJob:
    """A prepared fellowship unit — no embeddings.

    All fellowship items are loaded from the DB; the deterministic rule engine
    (:mod:`.fellowships`) gates them by eligibility, then the fellowship model
    (:mod:`.opportunity_llm`) writes a tailored report for the top slice. Safe to
    run in the same thread pool as the grant/conference LLM jobs.
    """

    user: User
    username: str
    area: str = "fellowships"
    content_type: str = ContentItem.Type.FELLOWSHIP
    items: list = None           # list[ContentItem]
    elig: object = None          # Elig dataclass
    interests: dict = None       # Profile.interests (for the LLM report)
    profile_meta: dict = None    # career stage / institution (for the LLM report)
    percentile: float = DEFAULT_PERCENTILE
    llm_limit: int = DEFAULT_LLM_LIMIT
    match_threshold: float = 0.0     # min fit to surface (0 => all eligible)
    max_surface: int = DEFAULT_SURFACE  # backstop cap on surfaced fellowships
    today: str = ""

    def __post_init__(self):
        if self.items is None:
            self.items = []
        if self.interests is None:
            self.interests = {}
        if self.profile_meta is None:
            self.profile_meta = {}


def _prepare_fellowship_match(
    user: User,
    *,
    percentile: float,
    today: str | None,
    log: Callable[[str], None] | None,
) -> tuple[_FellowshipMatchJob | None, OppRunResult | None]:
    """DB phase for fellowships — load all items + build Elig (no embedding)."""
    username = user.get_username()

    def emit(message: str) -> None:
        if log is not None:
            log(f"[{username}:fellowships] {message}")

    profile = getattr(user, "profile", None)
    if profile is None:
        emit("no profile; skipping")
        return None, OppRunResult(
            username, "fellowships", "no_profile", note="user has no profile"
        )

    from .fellowships import eligibility_from_profile

    elig = eligibility_from_profile(profile)

    items = list(
        ContentItem.objects.filter(type=ContentItem.Type.FELLOWSHIP).only(
            "id", "metadata"
        )
    )
    if not items:
        emit("no fellowship ContentItems in corpus yet")
        return None, OppRunResult(
            username, "fellowships", "no_results", note="no fellowship items in DB"
        )

    emit(f"loaded {len(items)} fellowship items")
    from django.utils import timezone as tz

    job = _FellowshipMatchJob(
        user=user,
        username=username,
        items=items,
        elig=elig,
        interests=profile.interests or {},
        profile_meta={
            "academic_title": getattr(profile, "academic_title", ""),
            "institution": getattr(profile, "institution", ""),
        },
        percentile=percentile,
        match_threshold=getattr(settings, "FELLOWSHIP_FIT_THRESHOLD", 0.0),
        max_surface=_opportunity_max_surface(),
        today=today or tz.now().date().isoformat(),
    )
    return job, None


def _score_fellowship_job(
    job: _FellowshipMatchJob, *, complete: Callable[[str], str | None] | None
) -> list[dict]:
    """Eligibility gate (rule engine) + LLM report — pure, safe in the thread pool.

    The rule engine decides eligibility and fit-ranks the survivors; the model
    then writes a tailored 2-4 sentence report for the top slice. A missing/flaky
    model degrades to the rule engine's own reason (``source="rules"``).
    """
    from .fellowships import match_fellowships

    ranked = match_fellowships(
        job.items,
        job.elig,
        job.today,
        match_threshold=job.match_threshold,
        max_surface=job.max_surface,
    )
    items_by_id = {str(item.id): item for item in job.items}
    return generate_fellowship_suggestions(
        job.interests,
        job.profile_meta,
        ranked,
        items_by_id,
        llm_limit=job.llm_limit,
        complete=complete,
    )


def _finalize_fellowship_match(
    job: _FellowshipMatchJob,
    suggestions: list[dict],
    *,
    persist: bool,
    log: Callable[[str], None] | None,
) -> OppRunResult:
    """DB phase — compute pins + persist RelevanceScore rows for fellowships."""

    def emit(message: str) -> None:
        if log is not None:
            log(f"[{job.username}:fellowships] {message}")

    items_by_id = {str(item.id): item for item in job.items}
    pins = compute_pins(
        suggestions, items_by_id, today=job.today, percentile=job.percentile
    )
    new_count = sum(1 for p in pins.values() if p["is_new"])
    llm = sum(1 for s in suggestions if s.get("source") == "llm")
    emit(
        f"scored {len(suggestions)} eligible fellowships "
        f"({llm} llm / {len(suggestions) - llm} rules), {new_count} new"
    )

    if persist:
        _persist_fellowships(job.user, suggestions, items_by_id, pins, today=job.today)

    return OppRunResult(
        job.username,
        "fellowships",
        "ok",
        retrieved=len(job.items),
        suggestions=len(suggestions),
        llm=llm,
        fallback=len(suggestions) - llm,
        new=new_count,
    )


def _persist_fellowships(
    user: User,
    suggestions: list[dict],
    items_by_id: dict,
    pins: dict,
    *,
    today: str | None,
) -> None:
    """Upsert one RelevanceScore per surfaced fellowship, with eligibility signals."""
    run_at = timezone.now().isoformat()
    for s in suggestions:
        cid = s["content_id"]
        item = items_by_id.get(cid)
        meta = (item.metadata or {}) if item else {}
        pin = pins.get(cid, {})
        signals = {
            "area": ContentItem.Type.FELLOWSHIP,
            "run_at": run_at,
            "suggested": True,
            "is_new": pin.get("is_new", False),
            "pinned_until": pin.get("pinned_until"),
            "first_seen": pin.get("first_seen", meta.get("first_seen", "")),
            "deadline_date": meta.get("deadline_date", ""),
            "next_kind": meta.get("next_kind", ""),
            "status": s.get("status", ""),
            "status_summary": s.get("status_summary", ""),
            "rank": s["rank"],
            "headline": s["headline"],
            "reason": s["reason"],
            "match_percent": s["match_percent"],
            "source": s["source"],
            "tier": s["tier"],
            "gates_failed": s.get("gates_failed", []),
            "reasons": s.get("reasons", []),
            "fit": s.get("fit", 0.0),
        }
        if item:
            RelevanceScore.objects.update_or_create(
                content=item,
                target_user=user,
                defaults={"score": round(s.get("fit", 0.0), 6), "signals": signals},
            )


def _prepare_match(
    target: MatchTarget,
    area: str,
    *,
    surface_limit: int,
    llm_limit: int,
    pool_per_interest: int,
    beta: float,
    percentile: float,
    log: Callable[[str], None] | None,
) -> tuple[_MatchJob | None, OppRunResult | None]:
    """DB phase — retrieve + fuse. Returns a job to score, or a short-circuit result.

    Target-agnostic: the interests / watch topics come off the :class:`MatchTarget`,
    so this prepares a unit for a person, a lab, or a project identically.
    """
    if area not in AREAS:
        raise ValueError(f"unknown opportunity area {area!r}")
    content_type = AREAS[area]
    key = target.key

    def emit(message: str) -> None:
        if log is not None:
            log(f"[{key}:{area}] {message}")

    search_ints = opportunity_search_interests(target.interests, target.watch_topics)
    if not search_ints:
        emit("no research interests or watch topics; skipping")
        return None, OppRunResult(
            key, area, "no_interests", note="no interests/topics to match on"
        )

    # Threshold-gated areas (grants/conferences) surface *every* opportunity whose
    # embedding match clears the floor, capped by the backstop; ungated areas keep
    # the fixed top-``surface_limit`` slice. ``job.surface_limit`` becomes ``None``
    # in threshold mode so the scorer surfaces the whole pre-filtered list.
    threshold = _area_match_threshold(content_type)
    cap = _opportunity_max_surface() if threshold is not None else surface_limit

    pairs, rows, pool = fuse_interests_pool(
        search_ints,
        content_type=content_type,
        surface_limit=cap,
        pool_per_interest=pool_per_interest,
        beta=beta,
        emit=emit,
        match_threshold=threshold,
    )
    if not pairs:
        emit("no embedded opportunities to retrieve yet")
        return None, OppRunResult(
            key, area, "no_results", note="no embedded opportunities yet"
        )

    job = _MatchJob(
        target=target,
        username=key,
        area=area,
        content_type=content_type,
        pairs=pairs,
        rows=rows,
        pool=pool,
        percentile=percentile,
        llm_limit=llm_limit,
        surface_limit=None if threshold is not None else surface_limit,
    )
    return job, None


def _score_job(
    job: _MatchJob, *, complete: Callable[[str], str | None] | None
) -> list[dict]:
    """LLM phase — pure (no ORM / embedder), so it is safe to run in a thread pool."""
    return generate_opportunity_suggestions(
        job.content_type,
        job.target.interests,
        job.target.profile_meta,
        job.pairs,
        llm_limit=job.llm_limit,
        surface_limit=job.surface_limit,
        complete=complete,
    )


def _finalize_match(
    job: _MatchJob,
    suggestions: list[dict],
    *,
    persist: bool,
    today: str | None,
    log: Callable[[str], None] | None,
) -> OppRunResult:
    """DB phase — New/pin + persist. Runs on the main thread (own connection)."""

    def emit(message: str) -> None:
        if log is not None:
            log(f"[{job.username}:{job.area}] {message}")

    items_by_id = {str(item.id): item for item, _score in job.pairs}
    pins = compute_pins(
        suggestions, items_by_id, today=today, percentile=job.percentile
    )
    new_count = sum(1 for p in pins.values() if p["is_new"])
    llm = sum(1 for s in suggestions if s["source"] == "llm")
    emit(
        f"scored {len(suggestions)} ({llm} llm / {len(suggestions) - llm} fallback), "
        f"{new_count} new over {job.pool} candidates"
    )
    if persist:
        # Store the singular content type as the signal's ``area`` so it lines up
        # with ``content.type`` and the API filter (grant/conference, not plural).
        _persist(
            job.target.persist_kwargs,
            job.content_type,
            job.rows,
            suggestions,
            pins,
            today=today,
        )
    return OppRunResult(
        job.username,
        job.area,
        "ok",
        retrieved=job.pool,
        suggestions=len(suggestions),
        llm=llm,
        fallback=len(suggestions) - llm,
        new=new_count,
    )


def match_opportunities_for_target(
    target: MatchTarget,
    area: str,
    *,
    surface_limit: int = DEFAULT_SURFACE,
    llm_limit: int = DEFAULT_LLM_LIMIT,
    pool_per_interest: int = DEFAULT_POOL_PER_INTEREST,
    beta: float = DEFAULT_BETA,
    percentile: float = DEFAULT_PERCENTILE,
    complete: Callable[[str], str | None] | None = None,
    persist: bool = True,
    today: str | None = None,
    log: Callable[[str], None] | None = None,
) -> OppRunResult:
    """Retrieve → fuse → score → pin → persist one area for *any* target (serial).

    The engine for a person, a lab, or a project; the score row lands under the
    target's ``persist_kwargs`` (``target_user`` / ``target_lab`` / ``target_project``).
    """
    job, short = _prepare_match(
        target,
        area,
        surface_limit=surface_limit,
        llm_limit=llm_limit,
        pool_per_interest=pool_per_interest,
        beta=beta,
        percentile=percentile,
        log=log,
    )
    if short is not None:
        return short
    suggestions = _score_job(job, complete=complete)
    return _finalize_match(job, suggestions, persist=persist, today=today, log=log)


def match_opportunities_for_user(
    user: User, area: str, **kwargs
) -> OppRunResult:
    """Retrieve → fuse → score → pin → persist one area for one user (serial)."""
    return match_opportunities_for_target(target_for_user(user), area, **kwargs)


def match_fellowships_for_user(
    user: User,
    *,
    percentile: float = DEFAULT_PERCENTILE,
    complete: Callable[[str], str | None] | None = None,
    persist: bool = True,
    today: str | None = None,
    log: Callable[[str], None] | None = None,
) -> OppRunResult:
    """Eligibility-gate + LLM-report fellowship matching for one user (serial)."""
    job, short = _prepare_fellowship_match(
        user, percentile=percentile, today=today, log=log
    )
    if short is not None:
        return short
    suggestions = _score_fellowship_job(job, complete=complete)
    return _finalize_fellowship_match(job, suggestions, persist=persist, log=log)


def run_opportunities_for_user(
    user: User,
    *,
    areas: tuple[str, ...] = ("grants", "conferences"),
    **kwargs,
) -> list[OppRunResult]:
    """Match every requested area for one user (grants + conferences by default)."""
    results = []
    for area in areas:
        if area == "fellowships":
            # fellowships gate on the rule engine, then get an LLM report — but
            # they skip the retrieve/fuse embedding pipeline grants/conferences use.
            results.append(
                match_fellowships_for_user(
                    user,
                    percentile=kwargs.get("percentile", DEFAULT_PERCENTILE),
                    complete=kwargs.get("complete"),
                    persist=kwargs.get("persist", True),
                    today=kwargs.get("today"),
                    log=kwargs.get("log"),
                )
            )
        else:
            results.append(match_opportunities_for_user(user, area, **kwargs))
    return results


def run_opportunities_for_target(
    target: MatchTarget,
    *,
    areas: tuple[str, ...] = ("grants", "conferences"),
    **kwargs,
) -> list[OppRunResult]:
    """Match grants + conferences for a lab or project target.

    Fellowships are intentionally excluded: they gate on an *individual's*
    eligibility (citizenship, career stage, demographic restrictions), which has no
    meaning for a lab or a project, so institutional targets match funding and
    conferences only.
    """
    return [
        match_opportunities_for_target(target, area, **kwargs)
        for area in areas
        if area != "fellowships"
    ]


def run_opportunities_for_lab(lab, **kwargs) -> list[OppRunResult]:
    """Match grants + conferences for a lab's aggregate interests."""
    from .targets import target_for_lab

    return run_opportunities_for_target(target_for_lab(lab), **kwargs)


def run_opportunities_for_project(project, **kwargs) -> list[OppRunResult]:
    """Match grants + conferences for one project's declared focus."""
    from .targets import target_for_project

    return run_opportunities_for_target(target_for_project(project), **kwargs)


@dataclass
class OppBatchResult:
    """One daily opportunity run: ingest stats plus each user's per-area result."""

    ingest: dict
    results: list[OppRunResult]

    def as_dict(self) -> dict:
        return {"ingest": self.ingest, "users": [r.as_dict() for r in self.results]}


def _union_watch_topics(users) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for user in users:
        for topic in _watch_topics(user):
            text = " ".join(topic.split())
            fold = text.casefold()
            if text and fold not in seen:
                seen.add(fold)
                out.append(text)
    return out


def run_daily_opportunities_batch(
    users,
    *,
    labs=(),
    projects=(),
    areas: tuple[str, ...] = ("grants", "conferences", "fellowships"),
    ingest: bool = True,
    prune: bool = True,
    embed: bool = True,
    persist: bool = True,
    percentile: float = DEFAULT_PERCENTILE,
    concurrency: int | None = None,
    complete: Callable[[str], str | None] | None = None,
    today: str | None = None,
    log: Callable[[str], None] | None = None,
) -> OppBatchResult:
    """Best-effort ingest + prune once, then match every area for every target.

    Phase 1 (ingest, best-effort): try a Playwright refresh of the Pivot corpus —
    a no-op that logs and continues when no saved session exists — then prune
    expired items so the pool stays current even on nights with no fresh scrape.
    Phase 2 (match): each ``(target, area)`` unit is *prepared* (retrieve + fuse,
    serial DB work), then all prepared units are **scored by the model
    concurrently** (up to ``concurrency`` at once — the LLM call is the slow step
    and shouldn't be issued one at a time), then *finalized* (New/pin + persist,
    serial DB writes). A failure for one unit is caught so it never sinks the run.

    Users match every requested area; labs and projects match grants + conferences
    only (fellowships gate on individual eligibility, so they never apply to a lab
    or project).
    """
    if concurrency is None:
        concurrency = getattr(
            settings, "OPPORTUNITY_LLM_CONCURRENCY", DEFAULT_LLM_CONCURRENCY
        )

    def emit(message: str) -> None:
        if log is not None:
            log(message)

    ingest_summary: dict = {}
    if ingest:
        from apps.scraper.pivot.ingest import ingest_pivot

        topics = _union_watch_topics(users)
        try:
            from apps.scraper.pivot.scrape import refresh

            pairs = list(refresh(topics=topics, log=log))
        except Exception:
            logger.exception("Pivot refresh failed; matching existing corpus")
            emit("ingest: refresh failed (see log); matching existing corpus")
            pairs = []
        summary = ingest_pivot(
            pairs, embed=embed, prune=prune, today=today, log=log
        )
        ingest_summary = summary.as_dict()
    elif prune:
        from apps.scraper.pivot.ingest import prune_expired

        ingest_summary = {"pruned": prune_expired(today=today, log=log)}

    results: list[OppRunResult] = []

    # Phase 2a — prepare every unit (serial DB reads: retrieve + fuse + embed).
    # Fellowship units go into a separate list; they score via rule engine, not LLM.
    llm_jobs: list[_MatchJob] = []
    fellowship_jobs: list[_FellowshipMatchJob] = []

    for user in users:
        for area in areas:
            if area == "fellowships":
                try:
                    job, short = _prepare_fellowship_match(
                        user, percentile=percentile, today=today, log=log
                    )
                except Exception:
                    logger.exception(
                        "prepare failed for %s:fellowships", user.get_username()
                    )
                    results.append(
                        OppRunResult(
                            user.get_username(), "fellowships", "error",
                            note="prepare failed",
                        )
                    )
                    continue
                if short is not None:
                    results.append(short)
                elif job is not None:
                    fellowship_jobs.append(job)
            else:
                try:
                    job, short = _prepare_match(
                        target_for_user(user),
                        area,
                        surface_limit=DEFAULT_SURFACE,
                        llm_limit=DEFAULT_LLM_LIMIT,
                        pool_per_interest=DEFAULT_POOL_PER_INTEREST,
                        beta=DEFAULT_BETA,
                        percentile=percentile,
                        log=log,
                    )
                except Exception:
                    logger.exception(
                        "prepare failed for %s:%s", user.get_username(), area
                    )
                    results.append(
                        OppRunResult(
                            user.get_username(), area, "error", note="prepare failed"
                        )
                    )
                    continue
                if short is not None:
                    results.append(short)
                elif job is not None:
                    llm_jobs.append(job)

    # Lab + project targets: grants + conferences only (no fellowships).
    from .targets import target_for_lab, target_for_project

    inst_targets = [target_for_lab(lab) for lab in labs]
    inst_targets += [target_for_project(project) for project in projects]
    inst_areas = tuple(a for a in areas if a != "fellowships")
    for target in inst_targets:
        for area in inst_areas:
            try:
                job, short = _prepare_match(
                    target,
                    area,
                    surface_limit=DEFAULT_SURFACE,
                    llm_limit=DEFAULT_LLM_LIMIT,
                    pool_per_interest=DEFAULT_POOL_PER_INTEREST,
                    beta=DEFAULT_BETA,
                    percentile=percentile,
                    log=log,
                )
            except Exception:
                logger.exception("prepare failed for %s:%s", target.key, area)
                results.append(
                    OppRunResult(target.key, area, "error", note="prepare failed")
                )
                continue
            if short is not None:
                results.append(short)
            elif job is not None:
                llm_jobs.append(job)

    # Phase 2b — score prepared units concurrently.  Grant/conference jobs run
    # retrieve→fuse then the model; fellowship jobs gate on the rule engine then
    # run the model for the tailored report — both submitted to the same pool so
    # all model calls run in parallel.
    all_jobs: list = llm_jobs + fellowship_jobs
    scored: dict[int, list[dict] | None] = {}
    if all_jobs:
        workers = max(1, min(concurrency, len(all_jobs)))
        emit(
            f"scoring {len(llm_jobs)} LLM + {len(fellowship_jobs)} fellowship "
            f"unit(s), up to {workers} concurrent…"
        )
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {}
            for idx, job in enumerate(all_jobs):
                if isinstance(job, _FellowshipMatchJob):
                    futures[
                        executor.submit(_score_fellowship_job, job, complete=complete)
                    ] = idx
                else:
                    futures[executor.submit(_score_job, job, complete=complete)] = idx
            for future in as_completed(futures):
                idx = futures[future]
                j = all_jobs[idx]
                try:
                    scored[idx] = future.result()
                except Exception:
                    logger.exception(
                        "scoring failed for %s:%s", j.username, j.area
                    )
                    scored[idx] = None

    # Phase 2c — finalize (serial DB writes: New/pin + persist).
    for idx, job in enumerate(all_jobs):
        suggestions = scored.get(idx)
        if suggestions is None:
            results.append(
                OppRunResult(job.username, job.area, "error", note="scoring failed")
            )
            continue
        try:
            if isinstance(job, _FellowshipMatchJob):
                results.append(
                    _finalize_fellowship_match(
                        job, suggestions, persist=persist, log=log
                    )
                )
            else:
                results.append(
                    _finalize_match(
                        job, suggestions, persist=persist, today=today, log=log
                    )
                )
        except Exception:
            logger.exception(
                "finalize failed for %s:%s", job.username, job.area
            )
            results.append(
                OppRunResult(job.username, job.area, "error", note="finalize failed")
            )
    return OppBatchResult(ingest=ingest_summary, results=results)


def _persist(
    persist_kwargs: dict,
    area: str,
    rows: list[PersistRow],
    suggestions: list[dict],
    pins: dict[str, dict],
    *,
    today: str | None,
) -> None:
    """Upsert one RelevanceScore per surfaced item, with opportunity signals.

    ``persist_kwargs`` is the single ``target_*`` FK the rows are written under
    (a user, a lab, or a project). Mirrors the paper pipeline's persist but adds
    the area discriminator, the New/pin fields, and a deadline snapshot the API /
    deadlines / notifications read back. A shared ``run_at`` lets the read layer
    show only the latest run.
    """
    run_at = timezone.now().isoformat()
    promoted_by_id = {s["content_id"]: s for s in suggestions}
    for item, score, extra in rows:
        cid = str(item.id)
        meta = item.metadata or {}
        promoted = promoted_by_id.get(cid)
        pin = pins.get(cid, {})
        signals = {
            **extra,
            "area": area,
            "run_at": run_at,
            "suggested": promoted is not None,
            "is_new": pin.get("is_new", False),
            "pinned_until": pin.get("pinned_until"),
            "first_seen": pin.get("first_seen", meta.get("first_seen", "")),
            "deadline_date": meta.get("deadline_date", ""),
            "next_kind": meta.get("next_kind", ""),
            "status": meta.get("status", ""),
            "status_summary": meta.get("status_summary", ""),
        }
        if promoted is not None:
            signals.update(
                rank=promoted["rank"],
                headline=promoted["headline"],
                reason=promoted["reason"],
                match_percent=promoted["match_percent"],
                source=promoted["source"],
            )
        RelevanceScore.objects.update_or_create(
            content=item,
            **persist_kwargs,
            defaults={"score": round(score, 6), "signals": signals},
        )
