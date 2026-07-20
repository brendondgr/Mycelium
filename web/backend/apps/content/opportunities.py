"""Per-user grant & conference matching — the opportunity twin of the paper daily.

For one user and one area (grants or conferences) this reuses the paper pipeline's
retrieval + multi-interest fusion (:func:`apps.content.pipeline.fuse_interests_pool`,
scoped by ``content_type``) over the Pivot corpus, scores the top slice with the
opportunity-aware model (:mod:`.opportunity_llm`), tags brand-new items
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
from dataclasses import asdict, dataclass, field
from datetime import date

from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone

from .digest_selection import new_content_ids, split_by_floor
from .fusion import DEFAULT_BETA
from .interests_query import SearchInterest, search_interests
from .models import ContentItem, RelevanceScore
from .opportunity_llm import (
    generate_fellowship_suggestions,
    generate_opportunity_suggestions,
    load_prior_llm_verdicts,
)
from .pinning import compute_pins
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


def _opportunity_min_match_percent() -> int:
    """The match-percent floor below which an LLM verdict stays hidden."""
    return getattr(settings, "OPPORTUNITY_MIN_MATCH_PERCENT", 60)


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
    hidden: int = 0  # scored below the match-percent floor; persisted, not surfaced
    note: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _force_fallback(_prompt: str) -> None:
    """A ``complete`` seam that always declines — forces the deterministic path (A3)."""
    return None


def _watch_topics(user: User) -> list[str]:
    """The user's watch topics, capped to their tier's cap (never deleted)."""
    from apps.billing.entitlements import effective_watch_topics

    return [str(topic) for topic in effective_watch_topics(user)]


def areas_for(user: User, requested: tuple[str, ...]) -> tuple[str, ...]:
    """The requested opportunity areas this user is entitled to, in order.

    Grants gate on ``GRANT_ALERTS``, conferences on ``CONFERENCE_ALERTS``, and
    fellowships on ``FELLOWSHIP_MATCHING`` — all Spore and up. A Free user resolves
    to the empty tuple (they never reach the daily batch anyway; this is the
    per-target gate the plan calls for).
    """
    from apps.billing.entitlements import Feature, has_feature

    gate = {
        "grants": Feature.GRANT_ALERTS,
        "conferences": Feature.CONFERENCE_ALERTS,
        "fellowships": Feature.FELLOWSHIP_MATCHING,
    }
    return tuple(
        area
        for area in requested
        if area in gate and has_feature(user, gate[area])
    )


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
    llm_limit: int
    surface_limit: int | None  # None => surface all (threshold-gated areas)
    prior: dict = field(default_factory=dict)  # carry-forward LLM verdicts
    new_ids: set = field(default_factory=set)  # freshly-seen cids (LLM-slot priority)
    # None => whole corpus (sign-up/refit, which *replaces* the feed); a date =>
    # only items ingested that day (the daily run, which *accumulates*).
    created_on: date | None = None


@dataclass
class _FellowshipMatchJob:
    """A prepared fellowship unit — eligibility (always) + embedding match (maybe).

    All fellowship items are loaded from the DB; the deterministic rule engine
    (:mod:`.fellowships`) gates them by eligibility and (when ``embed_by_id`` is
    populated) research-fit relevance, then the fellowship model
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
    llm_limit: int = DEFAULT_LLM_LIMIT
    match_threshold: float = 0.0     # min blended fit to surface (0 => all eligible)
    max_surface: int = DEFAULT_SURFACE  # backstop cap on surfaced fellowships
    today: str = ""
    prior: dict = None           # carry-forward LLM verdicts
    new_ids: set = None          # freshly-seen cids (LLM-slot priority)
    embed_by_id: dict | None = None   # {content_id: cosine}; None => rule-only
    has_interest_signal: bool = False  # user declared interests/watch topics
    embed_threshold: float = 0.0      # min cosine an eligible item must clear
    # None => whole corpus (sign-up/refit, *replaces* the feed); a date => only
    # fellowships ingested that day (the daily run, *accumulates*).
    created_on: date | None = None

    def __post_init__(self):
        if self.items is None:
            self.items = []
        if self.interests is None:
            self.interests = {}
        if self.profile_meta is None:
            self.profile_meta = {}
        if self.prior is None:
            self.prior = {}
        if self.new_ids is None:
            self.new_ids = set()


def _prepare_fellowship_match(
    user: User,
    *,
    today: str | None,
    reuse_prior: bool = True,
    created_on: date | None = None,
    log: Callable[[str], None] | None,
) -> tuple[_FellowshipMatchJob | None, OppRunResult | None]:
    """DB phase for fellowships — load items + build Elig (no embedding).

    ``created_on`` set (the daily run) restricts the candidate items to fellowships
    ingested that day, so the run only evaluates the day's new arrivals and appends
    them; ``None`` (sign-up/refit) evaluates the whole fellowship corpus.
    """
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

    queryset = ContentItem.objects.filter(type=ContentItem.Type.FELLOWSHIP)
    if created_on is not None:
        queryset = queryset.filter(created_at__date=created_on)
    items = list(queryset.only("id", "metadata"))
    if not items:
        scope = "new today" if created_on is not None else "in corpus"
        emit(f"no fellowship ContentItems {scope} yet")
        return None, OppRunResult(
            username, "fellowships", "no_results", note="no fellowship items in DB"
        )

    emit(f"loaded {len(items)} fellowship items")
    from django.utils import timezone as tz

    today_final = today or tz.now().date().isoformat()
    prior = (
        load_prior_llm_verdicts({"target_user": user}, ContentItem.Type.FELLOWSHIP)
        if reuse_prior
        else {}
    )
    embed_by_id, has_interest_signal = _fellowship_embed_by_id(
        user, profile, emit=emit, created_on=created_on
    )
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
        match_threshold=getattr(settings, "FELLOWSHIP_FIT_THRESHOLD", 0.0),
        max_surface=_opportunity_max_surface(),
        today=today_final,
        prior=prior,
        new_ids=new_content_ids(items, today=today_final),
        embed_by_id=embed_by_id,
        has_interest_signal=has_interest_signal,
        embed_threshold=getattr(settings, "FELLOWSHIP_MATCH_THRESHOLD", 0.4),
        created_on=created_on,
    )
    return job, None


def _fellowship_embed_by_id(
    user: User, profile, *, emit: Callable[[str], None], created_on: date | None = None
) -> tuple[dict[str, float] | None, bool]:
    """The researcher's embedding match to each fellowship, or ``(None, ...)``.

    Reuses the same multi-interest search-interest builder grants/conferences use
    (:func:`opportunity_search_interests`) and the shared retrieve+fuse step
    (:func:`~apps.content.pipeline.fuse_interests_pool`), scoped to the fellowship
    corpus. Called with ``match_threshold=0.0`` (not the real gate) so the fuse
    step's *threshold* branch runs — the only branch that records each surfaced
    item's raw cosine as ``embedding_match`` in its ``PersistRow`` extra (the same
    signal grants/conferences persist) — and every retrieved candidate survives to
    be looked up later; :func:`apps.content.fellowships.match_fellowships` applies
    the real ``embed_threshold`` gate itself.

    Returns ``(embed_by_id, has_interest_signal)``:

    - ``has_interest_signal`` is ``True`` whenever the user has declared
      interests/watch topics to search on, independent of whether retrieval
      actually produced anything — it only describes the user, not the corpus.
    - ``embed_by_id`` is ``None`` when there is nothing to gate on: no interest
      signal, no embedder configured, no embedded fellowships yet, or the
      retrieval step raised (pgvector unavailable, etc. — degrade, don't crash).
      A non-``None`` (possibly empty) dict means retrieval genuinely ran; a
      fellowship missing from it was retrieved-and-not-relevant, not "unknown".
    """
    search_ints = opportunity_search_interests(
        profile.interests or {}, _watch_topics(user)
    )
    has_interest_signal = bool(search_ints)
    if not has_interest_signal:
        return None, False

    try:
        _pairs, rows, pool = fuse_interests_pool(
            search_ints,
            content_type=ContentItem.Type.FELLOWSHIP,
            surface_limit=_opportunity_max_surface(),
            pool_per_interest=DEFAULT_POOL_PER_INTEREST,
            beta=DEFAULT_BETA,
            emit=emit,
            created_on=created_on,
            match_threshold=0.0,
        )
    except Exception:
        logger.exception(
            "fellowship embedding retrieval failed for %s; falling back to "
            "rule-only ranking",
            user.get_username(),
        )
        return None, True

    if pool == 0:
        # No embedder configured, or no embedded fellowships yet — not a real
        # "zero relevance" signal, so don't gate on it.
        emit("no embedded fellowships to retrieve yet; ranking on eligibility only")
        return None, True

    embed_by_id: dict[str, float] = {}
    for item, _score, extra in rows:
        match = extra.get("embedding_match")
        if match is not None:
            embed_by_id[str(item.id)] = float(match)
    return embed_by_id, True


def _score_fellowship_job(
    job: _FellowshipMatchJob, *, complete: Callable[[str], str | None] | None
) -> list[dict]:
    """Eligibility+relevance gate (rule engine) + LLM report — pure, safe in a pool.

    The rule engine decides eligibility, gates on research-fit relevance when an
    embedding signal is available (``job.embed_by_id``), and fit-ranks the
    survivors; the model then writes a tailored 2-4 sentence report for the top
    slice. A missing/flaky model degrades to the rule engine's own reason
    (``source="rules"``).
    """
    from .fellowships import match_fellowships

    ranked = match_fellowships(
        job.items,
        job.elig,
        job.today,
        match_threshold=job.match_threshold,
        max_surface=job.max_surface,
        embed_by_id=job.embed_by_id,
        embed_threshold=job.embed_threshold,
    )
    items_by_id = {str(item.id): item for item in job.items}
    return generate_fellowship_suggestions(
        job.interests,
        job.profile_meta,
        ranked,
        items_by_id,
        llm_limit=job.llm_limit,
        complete=complete,
        prior=job.prior,
        new_ids=job.new_ids,
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
    floor = _opportunity_min_match_percent()
    visible, hidden = split_by_floor(suggestions, floor)
    pins = compute_pins(visible, items_by_id, today=job.today)
    new_count = sum(1 for p in pins.values() if p["is_new"])
    llm = sum(1 for s in visible if s.get("source") == "llm")
    emit(
        f"scored {len(suggestions)} eligible fellowships "
        f"({llm} llm / {len(visible) - llm} rules), {new_count} new"
        + (f", {len(hidden)} hidden below floor" if hidden else "")
    )

    if persist:
        visible_ids = {s["content_id"] for s in visible}
        # Whole-corpus runs (sign-up/refit, created_on is None) replace the feed;
        # daily new-only runs accumulate.
        _persist_fellowships(
            {"target_user": job.user},
            suggestions,
            visible_ids,
            items_by_id,
            pins,
            today=job.today,
            replace=job.created_on is None,
        )

    return OppRunResult(
        job.username,
        "fellowships",
        "ok",
        retrieved=len(job.items),
        suggestions=len(visible),
        llm=llm,
        fallback=len(visible) - llm,
        new=new_count,
        hidden=len(hidden),
    )


def _persist_fellowships(
    persist_kwargs: dict,
    suggestions: list[dict],
    visible_ids: set[str],
    items_by_id: dict,
    pins: dict,
    *,
    today: str | None,
    replace: bool = False,
) -> None:
    """Upsert one RelevanceScore per fellowship under ``persist_kwargs``'s target.

    Every surfaced fellowship is persisted (so the carry-forward store remembers
    its verdict), but only those in ``visible_ids`` (cleared the match-percent
    floor) are flagged ``suggested`` — the rest are hidden from the feed. The
    target is polymorphic: ``{"target_user": user}`` for a person's eligible feed,
    ``{"target_project": project}`` for a project's interest-matched feed.

    ``replace`` (a whole-corpus sign-up/refit run) drops the target's prior
    fellowship scores that this run did not re-evaluate — so a profile edit that
    changes eligibility (or a project focus edit) clears the ones it no longer
    matches. A daily new-only run leaves ``replace`` false and accumulates.
    """
    run_at = timezone.now().isoformat()
    if replace:
        surfaced_ids = [s["content_id"] for s in suggestions]
        RelevanceScore.objects.filter(
            **persist_kwargs, content__type=ContentItem.Type.FELLOWSHIP
        ).exclude(content_id__in=surfaced_ids).delete()
    for s in suggestions:
        cid = s["content_id"]
        item = items_by_id.get(cid)
        meta = (item.metadata or {}) if item else {}
        pin = pins.get(cid, {})
        signals = {
            "area": ContentItem.Type.FELLOWSHIP,
            "run_at": run_at,
            "suggested": cid in visible_ids,
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
            "rule_fit": s.get("rule_fit", s.get("fit", 0.0)),
            "embedding_match": s.get("embedding_match"),
            "llm_scored_at": s.get("llm_scored_at", ""),
        }
        if item:
            RelevanceScore.objects.update_or_create(
                content=item,
                **persist_kwargs,
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
    reuse_prior: bool = True,
    created_on: date | None = None,
    today: str | None = None,
    log: Callable[[str], None] | None,
) -> tuple[_MatchJob | None, OppRunResult | None]:
    """DB phase — retrieve + fuse. Returns a job to score, or a short-circuit result.

    Target-agnostic: the interests / watch topics come off the :class:`MatchTarget`,
    so this prepares a unit for a person, a lab, or a project identically.

    ``created_on`` set (the daily run) scopes retrieval to opportunities ingested that
    day, so only the day's new arrivals are scored and appended; ``None``
    (sign-up/refit) scores the whole corpus and replaces the target's feed.
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
        created_on=created_on,
        match_threshold=threshold,
    )
    if not pairs:
        scope = "new today" if created_on is not None else "in corpus"
        emit(f"no embedded opportunities {scope} to retrieve")
        return None, OppRunResult(
            key, area, "no_results", note="no embedded opportunities yet"
        )

    prior = (
        load_prior_llm_verdicts(target.persist_kwargs, content_type)
        if reuse_prior
        else {}
    )
    today_iso = today or timezone.now().date().isoformat()
    new_ids = new_content_ids((item for item, _score in pairs), today=today_iso)

    job = _MatchJob(
        target=target,
        username=key,
        area=area,
        content_type=content_type,
        pairs=pairs,
        rows=rows,
        pool=pool,
        llm_limit=llm_limit,
        surface_limit=None if threshold is not None else surface_limit,
        prior=prior,
        new_ids=new_ids,
        created_on=created_on,
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
        prior=job.prior,
        new_ids=job.new_ids,
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
    floor = _opportunity_min_match_percent()
    visible, hidden = split_by_floor(suggestions, floor)
    pins = compute_pins(visible, items_by_id, today=today)
    new_count = sum(1 for p in pins.values() if p["is_new"])
    llm = sum(1 for s in visible if s["source"] == "llm")
    emit(
        f"scored {len(suggestions)} ({llm} llm / {len(visible) - llm} fallback), "
        f"{new_count} new over {job.pool} candidates"
        + (f", {len(hidden)} hidden below floor" if hidden else "")
    )
    if persist:
        # Store the singular content type as the signal's ``area`` so it lines up
        # with ``content.type`` and the API filter (grant/conference, not plural).
        # Whole-corpus runs (created_on is None) replace the feed; daily new-only
        # runs accumulate.
        visible_ids = {s["content_id"] for s in visible}
        _persist(
            job.target.persist_kwargs,
            job.content_type,
            job.rows,
            suggestions,
            visible_ids,
            pins,
            today=today,
            replace=job.created_on is None,
        )
    return OppRunResult(
        job.username,
        job.area,
        "ok",
        retrieved=job.pool,
        suggestions=len(visible),
        llm=llm,
        fallback=len(visible) - llm,
        new=new_count,
        hidden=len(hidden),
    )


def match_opportunities_for_target(
    target: MatchTarget,
    area: str,
    *,
    surface_limit: int = DEFAULT_SURFACE,
    llm_limit: int = DEFAULT_LLM_LIMIT,
    pool_per_interest: int = DEFAULT_POOL_PER_INTEREST,
    beta: float = DEFAULT_BETA,
    complete: Callable[[str], str | None] | None = None,
    persist: bool = True,
    reuse_prior: bool = True,
    created_on: date | None = None,
    today: str | None = None,
    log: Callable[[str], None] | None = None,
) -> OppRunResult:
    """Retrieve → fuse → score → pin → persist one area for *any* target (serial).

    The engine for a person, a lab, or a project; the score row lands under the
    target's ``persist_kwargs`` (``target_user`` / ``target_lab`` / ``target_project``).
    ``reuse_prior=False`` bypasses carry-forward, re-sending every surfaced item to
    the model (used by :mod:`.refitting` after a profile edit). ``created_on`` defaults
    to ``None`` (whole corpus, so this serial path — sign-up / refit — replaces the
    target's feed for the area); the daily batch passes the run date to score only
    that day's new items and accumulate.
    """
    job, short = _prepare_match(
        target,
        area,
        surface_limit=surface_limit,
        llm_limit=llm_limit,
        pool_per_interest=pool_per_interest,
        beta=beta,
        reuse_prior=reuse_prior,
        created_on=created_on,
        today=today,
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
    complete: Callable[[str], str | None] | None = None,
    persist: bool = True,
    reuse_prior: bool = True,
    created_on: date | None = None,
    today: str | None = None,
    log: Callable[[str], None] | None = None,
) -> OppRunResult:
    """Eligibility-gate + LLM-report fellowship matching for one user (serial).

    ``created_on`` defaults to ``None`` (whole corpus — this serial sign-up / refit
    path replaces the user's fellowship feed); the daily batch passes the run date to
    evaluate only that day's new fellowships and accumulate.
    """
    job, short = _prepare_fellowship_match(
        user, today=today, reuse_prior=reuse_prior, created_on=created_on, log=log
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
                    complete=kwargs.get("complete"),
                    persist=kwargs.get("persist", True),
                    reuse_prior=kwargs.get("reuse_prior", True),
                    today=kwargs.get("today"),
                    log=kwargs.get("log"),
                )
            )
        else:
            results.append(match_opportunities_for_user(user, area, **kwargs))
    return results


def _target_fellowship_embed_by_id(
    target: MatchTarget,
    *,
    emit: Callable[[str], None],
    created_on: date | None = None,
) -> dict[str, float] | None:
    """The target's embedding match to each fellowship (interest-only ranking).

    The institutional twin of :func:`_fellowship_embed_by_id`: it reuses the same
    multi-interest search-interest builder + retrieve/fuse step grants/conferences
    use, but reads the interests off the :class:`MatchTarget` (a project's focus)
    rather than a user Profile. Returns ``None`` when there is nothing to rank on
    (no declared interests, no embedder, no embedded fellowships, or retrieval
    raised) — the caller then surfaces no project fellowships rather than guessing.
    """
    search_ints = opportunity_search_interests(target.interests, target.watch_topics)
    if not search_ints:
        return None
    try:
        _pairs, rows, pool = fuse_interests_pool(
            search_ints,
            content_type=ContentItem.Type.FELLOWSHIP,
            surface_limit=_opportunity_max_surface(),
            pool_per_interest=DEFAULT_POOL_PER_INTEREST,
            beta=DEFAULT_BETA,
            emit=emit,
            created_on=created_on,
            match_threshold=0.0,
        )
    except Exception:
        logger.exception(
            "fellowship embedding retrieval failed for target %s", target.key
        )
        return None
    if pool == 0:
        emit("no embedded fellowships to retrieve yet")
        return None
    embed_by_id: dict[str, float] = {}
    for item, _score, extra in rows:
        match = extra.get("embedding_match")
        if match is not None:
            embed_by_id[str(item.id)] = float(match)
    return embed_by_id


def match_fellowships_for_target(
    target: MatchTarget,
    *,
    llm_limit: int = DEFAULT_LLM_LIMIT,
    complete: Callable[[str], str | None] | None = None,
    persist: bool = True,
    reuse_prior: bool = True,
    created_on: date | None = None,
    today: str | None = None,
    log: Callable[[str], None] | None = None,
) -> OppRunResult:
    """Interest-based fellowship matching for a project target (no eligibility gate).

    A project has no citizenship or career stage, so its fellowships are ranked
    purely on research fit to the project's interests — the same embedding signal
    grants/conferences use — then the top slice gets an LLM report. Scores persist
    under ``target.persist_kwargs`` (``target_project``). ``created_on`` ``None``
    (sign-up/refit) replaces the feed; a run date appends the day's new arrivals.
    """
    key = target.key

    def emit(message: str) -> None:
        if log is not None:
            log(f"[{key}:fellowships] {message}")

    from django.utils import timezone as tz

    from .fellowships import match_fellowships

    today_final = today or tz.now().date().isoformat()
    queryset = ContentItem.objects.filter(type=ContentItem.Type.FELLOWSHIP)
    if created_on is not None:
        queryset = queryset.filter(created_at__date=created_on)
    items = list(queryset.only("id", "metadata"))
    if not items:
        return OppRunResult(
            key, "fellowships", "no_results", note="no fellowship items in DB"
        )

    embed_by_id = _target_fellowship_embed_by_id(
        target, emit=emit, created_on=created_on
    )
    if not embed_by_id:
        emit("no interest embedding signal; skipping project fellowships")
        return OppRunResult(
            key, "fellowships", "no_results", note="no interest signal"
        )

    ranked = match_fellowships(
        items,
        None,
        today_final,
        match_threshold=getattr(settings, "FELLOWSHIP_FIT_THRESHOLD", 0.0),
        max_surface=_opportunity_max_surface(),
        embed_by_id=embed_by_id,
        embed_threshold=getattr(settings, "FELLOWSHIP_MATCH_THRESHOLD", 0.4),
        skip_eligibility=True,
    )
    items_by_id = {str(item.id): item for item in items}
    prior = (
        load_prior_llm_verdicts(target.persist_kwargs, ContentItem.Type.FELLOWSHIP)
        if reuse_prior
        else {}
    )
    suggestions = generate_fellowship_suggestions(
        target.interests,
        target.profile_meta,
        ranked,
        items_by_id,
        llm_limit=llm_limit,
        complete=complete,
        prior=prior,
        new_ids=new_content_ids(items, today=today_final),
    )
    floor = _opportunity_min_match_percent()
    visible, hidden = split_by_floor(suggestions, floor)
    pins = compute_pins(visible, items_by_id, today=today_final)
    new_count = sum(1 for p in pins.values() if p["is_new"])
    llm = sum(1 for s in visible if s.get("source") == "llm")
    emit(
        f"scored {len(suggestions)} project fellowships "
        f"({llm} llm / {len(visible) - llm} fallback), {new_count} new"
    )
    if persist:
        visible_ids = {s["content_id"] for s in visible}
        _persist_fellowships(
            target.persist_kwargs,
            suggestions,
            visible_ids,
            items_by_id,
            pins,
            today=today_final,
            replace=created_on is None,
        )
    return OppRunResult(
        key,
        "fellowships",
        "ok",
        retrieved=len(items),
        suggestions=len(visible),
        llm=llm,
        fallback=len(visible) - llm,
        new=new_count,
        hidden=len(hidden),
    )


def run_opportunities_for_target(
    target: MatchTarget,
    *,
    areas: tuple[str, ...] = ("grants", "conferences"),
    **kwargs,
) -> list[OppRunResult]:
    """Match opportunities for a lab or project target.

    Grants + conferences run for any institutional target. **Fellowships** run only
    for a **project** target, ranked on the project's research interests (no
    eligibility gate — a project has no citizenship or career stage). A lab still
    excludes fellowships: at lab scope they are surfaced as the union of members'
    *personal* eligibility, not scored to the lab.
    """
    results: list[OppRunResult] = []
    for area in areas:
        if area == "fellowships":
            if target.kind == "project":
                results.append(
                    match_fellowships_for_target(
                        target,
                        complete=kwargs.get("complete"),
                        persist=kwargs.get("persist", True),
                        reuse_prior=kwargs.get("reuse_prior", True),
                        created_on=kwargs.get("created_on"),
                        today=kwargs.get("today"),
                        log=kwargs.get("log"),
                    )
                )
            # Labs: fellowships are the member-eligibility union, handled at read
            # time — skip here.
            continue
        results.append(match_opportunities_for_target(target, area, **kwargs))
    return results


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
    concurrency: int | None = None,
    complete: Callable[[str], str | None] | None = None,
    today: str | None = None,
    log: Callable[[str], None] | None = None,
) -> OppBatchResult:
    """Best-effort ingest + prune once, then match every area for every target.

    Phase 1 (ingest, best-effort): try a Playwright refresh of the Pivot corpus —
    a no-op that logs and continues when no saved session exists — then prune
    expired items so the pool stays current even on nights with no fresh scrape.
    Phase 2 (match): the daily run is the **new-items-only** process — each
    ``(target, area)`` unit is *prepared* (retrieve + fuse, **scoped to that day's
    freshly-ingested items** via ``created_on``), then all prepared units are
    **scored by the model concurrently** (up to ``concurrency`` at once — the LLM
    call is the slow step and shouldn't be issued one at a time), then *finalized*
    (New/pin + **append**, serial DB writes). The passers are added to each target's
    accumulating feed; older matches stay until pruned. A failure for one unit is
    caught so it never sinks the run. (Sign-up / refit take the serial paths above,
    which score the whole corpus and replace the feed instead.)

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

    # The daily run is the *new-items-only* process: it scores just the opportunities
    # ingested today (a fresh ContentItem has ``created_at`` == today) and appends the
    # passers to each target's accumulating feed. Sign-up / refit (the serial paths)
    # leave ``created_on`` None and score the whole corpus instead.
    run_date = date.fromisoformat(today) if today else timezone.now().date()

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

    # Per-user entitlement gates, resolved in bulk (no N+1). Each user matches only
    # the areas their tier unlocks (A2 pipeline layer), and a user without LLM fit
    # scoring gets the deterministic report (A3). Institutional targets are already
    # filtered to active-subscription labs upstream, so they use the batch complete.
    from apps.billing.entitlements import Feature, users_with_feature

    uids = [user.id for user in users]
    grant_users = users_with_feature(Feature.GRANT_ALERTS, uids)
    conf_users = users_with_feature(Feature.CONFERENCE_ALERTS, uids)
    fellow_users = users_with_feature(Feature.FELLOWSHIP_MATCHING, uids)
    llm_users = users_with_feature(Feature.LLM_FIT_SCORING, uids)
    area_gate = {
        "grants": grant_users,
        "conferences": conf_users,
        "fellowships": fellow_users,
    }

    def _user_areas(user):
        return tuple(
            area
            for area in areas
            if area in area_gate and user.id in area_gate[area]
        )

    user_complete = {
        user.get_username(): (
            complete if user.id in llm_users else _force_fallback
        )
        for user in users
    }

    # Phase 2a — prepare every unit (serial DB reads: retrieve + fuse + embed).
    # Fellowship units go into a separate list; they score via rule engine, not LLM.
    llm_jobs: list[_MatchJob] = []
    fellowship_jobs: list[_FellowshipMatchJob] = []

    for user in users:
        for area in _user_areas(user):
            if area == "fellowships":
                try:
                    job, short = _prepare_fellowship_match(
                        user, today=today, created_on=run_date, log=log
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
                        created_on=run_date,
                        today=today,
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

    # Lab + project targets: grants + conferences only (no fellowships here). A
    # project only runs the areas it has opted into (``goals.watch_categories``);
    # a lab runs them all (its own watch config gates upstream).
    from .targets import target_for_lab, target_for_project, project_watch_categories

    inst_areas = tuple(a for a in areas if a != "fellowships")
    inst_units = [(target_for_lab(lab), inst_areas) for lab in labs]
    for project in projects:
        chosen = set(project_watch_categories(project))
        inst_units.append(
            (
                target_for_project(project),
                tuple(a for a in inst_areas if a in chosen),
            )
        )
    for target, target_areas in inst_units:
        for area in target_areas:
            try:
                job, short = _prepare_match(
                    target,
                    area,
                    surface_limit=DEFAULT_SURFACE,
                    llm_limit=DEFAULT_LLM_LIMIT,
                    pool_per_interest=DEFAULT_POOL_PER_INTEREST,
                    beta=DEFAULT_BETA,
                    created_on=run_date,
                    today=today,
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
                # A user job carries its user's LLM gate (keyed by the target key =
                # username); institutional jobs fall back to the batch complete.
                job_complete = user_complete.get(job.username, complete)
                if isinstance(job, _FellowshipMatchJob):
                    futures[
                        executor.submit(
                            _score_fellowship_job, job, complete=job_complete
                        )
                    ] = idx
                else:
                    futures[
                        executor.submit(_score_job, job, complete=job_complete)
                    ] = idx
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

    # Project fellowships (interest-matched, no eligibility gate) — appended for the
    # day's new arrivals. Serial (the LLM slice is small; a project's new-fellowship
    # count on any given day is tiny), keeping this out of the eligibility-coupled
    # pool above. Labs are intentionally excluded — their fellowships are the
    # member-eligibility union surfaced at read time.
    if "fellowships" in areas and projects:
        from .targets import project_watch_categories, target_for_project

        for project in projects:
            if "fellowships" not in project_watch_categories(project):
                continue
            target = target_for_project(project)
            try:
                results.append(
                    match_fellowships_for_target(
                        target,
                        complete=complete,
                        persist=persist,
                        created_on=run_date,
                        today=today,
                        log=log,
                    )
                )
            except Exception:
                logger.exception(
                    "project fellowship match failed for %s", target.key
                )
                results.append(
                    OppRunResult(target.key, "fellowships", "error", note="failed")
                )

    return OppBatchResult(ingest=ingest_summary, results=results)


def _persist(
    persist_kwargs: dict,
    area: str,
    rows: list[PersistRow],
    suggestions: list[dict],
    visible_ids: set[str],
    pins: dict[str, dict],
    *,
    today: str | None,
    replace: bool = False,
) -> None:
    """Upsert one RelevanceScore per surfaced item, with opportunity signals.

    ``persist_kwargs`` is the single ``target_*`` FK the rows are written under
    (a user, a lab, or a project). Mirrors the paper pipeline's persist but adds
    the area discriminator, the New/pin fields, and a deadline snapshot the API /
    deadlines / notifications read back. Each surfaced item carries a ``run_at``
    stamp; the accumulate read layer keeps every run's suggested rows. Every surfaced
    item is persisted (so carry-forward remembers its verdict), but only those in
    ``visible_ids`` (cleared the match-percent floor) are flagged ``suggested``.

    ``replace`` (a whole-corpus sign-up/refit run) drops this target's prior scores
    for the area that this run did not re-surface — so an interest edit re-establishes
    the feed from the full corpus rather than leaving stale matches behind. A daily
    new-only run leaves ``replace`` false and appends.
    """
    run_at = timezone.now().isoformat()
    if replace:
        surfaced_ids = [item.id for item, _score, _extra in rows]
        RelevanceScore.objects.filter(
            **persist_kwargs, content__type=area
        ).exclude(content_id__in=surfaced_ids).delete()
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
            "suggested": promoted is not None and cid in visible_ids,
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
                llm_scored_at=promoted.get("llm_scored_at", ""),
            )
        RelevanceScore.objects.update_or_create(
            content=item,
            **persist_kwargs,
            defaults={"score": round(score, 6), "signals": signals},
        )
