"""Per-user grant & conference matching — the opportunity twin of the paper daily.

For one user and one area (grants or conferences) this reuses the paper pipeline's
retrieval + multi-interest fusion (:func:`apps.content.pipeline.fuse_interests_pool`,
scoped by ``content_type``) over the Pivot corpus, scores the top slice with the
opportunity-aware model (:mod:`.opportunity_llm`), tags brand-new high-fit items
(:mod:`.pinning`), and persists one :class:`RelevanceScore` per item — the same
store the paper digest uses, discriminated by ``content.type`` and a ``signals.area``.

Scope is the personal workspace only (labs are out of scope): the query is built
from the user's ``Profile.interests`` (research focus + keywords) broadened by their
``WatchPreference.topics``. Every seam degrades to a clear status instead of a crash.
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
from .opportunity_llm import generate_opportunity_suggestions
from .pinning import DEFAULT_PERCENTILE, compute_pins
from .pipeline import PersistRow, fuse_interests_pool

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
}


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
    """A prepared per-(user, area) unit, ready for the (parallel) LLM scoring step.

    The retrieve+fuse work (DB + embedder) is already done; scoring reads only
    these in-memory fields, so it touches no ORM/embedder and is safe to run in a
    worker thread alongside other units.
    """

    user: User
    username: str
    area: str
    content_type: str
    interests: dict
    profile_meta: dict
    pairs: list
    rows: list
    pool: int
    percentile: float
    llm_limit: int
    surface_limit: int


def _prepare_match(
    user: User,
    area: str,
    *,
    surface_limit: int,
    llm_limit: int,
    pool_per_interest: int,
    beta: float,
    percentile: float,
    log: Callable[[str], None] | None,
) -> tuple[_MatchJob | None, OppRunResult | None]:
    """DB phase — retrieve + fuse. Returns a job to score, or a short-circuit result."""
    if area not in AREAS:
        raise ValueError(f"unknown opportunity area {area!r}")
    content_type = AREAS[area]
    username = user.get_username()

    def emit(message: str) -> None:
        if log is not None:
            log(f"[{username}:{area}] {message}")

    profile = getattr(user, "profile", None)
    if profile is None:
        emit("no profile; skipping")
        return None, OppRunResult(
            username, area, "no_profile", note="user has no profile"
        )

    interests = profile.interests or {}
    search_ints = opportunity_search_interests(interests, _watch_topics(user))
    if not search_ints:
        emit("no research interests or watch topics; skipping")
        return None, OppRunResult(
            username, area, "no_interests", note="no interests/topics to match on"
        )

    pairs, rows, pool = fuse_interests_pool(
        search_ints,
        content_type=content_type,
        surface_limit=surface_limit,
        pool_per_interest=pool_per_interest,
        beta=beta,
        emit=emit,
    )
    if not pairs:
        emit("no embedded opportunities to retrieve yet")
        return None, OppRunResult(
            username, area, "no_results", note="no embedded opportunities yet"
        )

    job = _MatchJob(
        user=user,
        username=username,
        area=area,
        content_type=content_type,
        interests=interests,
        profile_meta={
            "academic_title": getattr(profile, "academic_title", ""),
            "institution": getattr(profile, "institution", ""),
        },
        pairs=pairs,
        rows=rows,
        pool=pool,
        percentile=percentile,
        llm_limit=llm_limit,
        surface_limit=surface_limit,
    )
    return job, None


def _score_job(
    job: _MatchJob, *, complete: Callable[[str], str | None] | None
) -> list[dict]:
    """LLM phase — pure (no ORM / embedder), so it is safe to run in a thread pool."""
    return generate_opportunity_suggestions(
        job.content_type,
        job.interests,
        job.profile_meta,
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
        _persist(job.user, job.content_type, job.rows, suggestions, pins, today=today)
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


def match_opportunities_for_user(
    user: User,
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
    """Retrieve → fuse → score → pin → persist one area for one user (serial)."""
    job, short = _prepare_match(
        user,
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


def run_opportunities_for_user(
    user: User,
    *,
    areas: tuple[str, ...] = ("grants", "conferences"),
    **kwargs,
) -> list[OppRunResult]:
    """Match every requested area for one user (grants + conferences by default)."""
    return [match_opportunities_for_user(user, area, **kwargs) for area in areas]


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
    areas: tuple[str, ...] = ("grants", "conferences"),
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
    """Best-effort ingest + prune once, then match every area per user.

    Phase 1 (ingest, best-effort): try a Playwright refresh of the Pivot corpus —
    a no-op that logs and continues when no saved session exists — then prune
    expired items so the pool stays current even on nights with no fresh scrape.
    Phase 2 (match): each ``(user, area)`` unit is *prepared* (retrieve + fuse,
    serial DB work), then all prepared units are **scored by the model
    concurrently** (up to ``concurrency`` at once — the LLM call is the slow step
    and shouldn't be issued one at a time), then *finalized* (New/pin + persist,
    serial DB writes). A failure for one unit is caught so it never sinks the run.
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
    jobs: list[_MatchJob] = []
    for user in users:
        for area in areas:
            try:
                job, short = _prepare_match(
                    user,
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
                jobs.append(job)

    # Phase 2b — score the prepared units with the model CONCURRENTLY (the slow
    # step). Pure LLM I/O, no ORM, so a thread pool is safe.
    scored: dict[int, list[dict] | None] = {}
    if jobs:
        workers = max(1, min(concurrency, len(jobs)))
        emit(f"scoring {len(jobs)} unit(s), up to {workers} concurrent LLM call(s)…")
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(_score_job, job, complete=complete): idx
                for idx, job in enumerate(jobs)
            }
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    scored[idx] = future.result()
                except Exception:
                    logger.exception(
                        "scoring failed for %s:%s", jobs[idx].username, jobs[idx].area
                    )
                    scored[idx] = None

    # Phase 2c — finalize (serial DB writes: New/pin + persist).
    for idx, job in enumerate(jobs):
        suggestions = scored.get(idx)
        if suggestions is None:
            results.append(
                OppRunResult(job.username, job.area, "error", note="scoring failed")
            )
            continue
        try:
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
    user: User,
    area: str,
    rows: list[PersistRow],
    suggestions: list[dict],
    pins: dict[str, dict],
    *,
    today: str | None,
) -> None:
    """Upsert one RelevanceScore per surfaced item, with opportunity signals.

    Mirrors the paper pipeline's persist but adds the area discriminator, the
    New/pin fields, and a deadline snapshot the API / deadlines / notifications
    read back. A shared ``run_at`` lets the read layer show only the latest run.
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
            target_user=user,
            defaults={"score": round(score, 6), "signals": signals},
        )
