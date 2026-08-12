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

from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone

from .clustering import cluster_interests
from .digest_selection import split_by_floor
from .fusion import DEFAULT_BETA
from .interests_query import SearchInterest, search_interests
from .models import ContentItem, RelevanceScore
from .opportunity_llm import (
    generate_fellowship_suggestions,
    generate_opportunity_suggestions,
    load_prior_llm_verdicts,
)
from .pinning import compute_pins
from .pipeline import (
    PersistRow,
    fuse_clusters_pool,
    fuse_interests_pool,
)
from .targets import MatchTarget, target_for_user
from .top_feed import compute_top, merge_top_signals, prior_top_ids, top_n

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


def _scored_content_ids(persist_kwargs: dict, content_type: str) -> list:
    """Ids of the ``content_type`` items this target has already been scored on.

    The gate for an **append-only** run (``unscored_only=True``): score what this
    target has never been scored on and add it to the feed, leaving everything
    already there untouched.

    The nightly run no longer works this way. Scoring only the unscored meant a
    target's ranking was a historical accumulation — whatever each past run happened
    to see, in the order it then had — so changing a research focus could not change
    what the reader was shown, and an item's position reflected the day it arrived.
    The nightly run now re-ranks the whole corpus against the target's *current*
    profile (``unscored_only=False``); carry-forward means already-written verdicts
    are reused rather than re-billed, so the cost of doing so is retrieval, not the
    model. This path is kept for callers that genuinely want a pure append.
    """
    return list(
        RelevanceScore.objects.filter(
            **persist_kwargs, content__type=content_type
        ).values_list("content_id", flat=True)
    )


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
    # Cids entering the target's Top-25 on this run — where the model budget goes.
    priority_ids: set = field(default_factory=set)
    # False => whole corpus (the daily re-rank, and sign-up/refit); True => only
    # items this target has never been scored on (the legacy append-only mode).
    unscored_only: bool = False


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
    prior_top: set = None        # the Top-25 as of the last run (entrant diff)
    embed_by_id: dict | None = None   # {content_id: cosine}; None => rule-only
    has_interest_signal: bool = False  # user declared interests/watch topics
    embed_threshold: float = 0.0      # min cosine an eligible item must clear
    withhold_unverified: bool = False  # drop scrape-miss records instead of labelling
    # False => whole corpus (the daily re-rank, and sign-up/refit); True => only
    # fellowships this user has never been scored on (the legacy append-only mode).
    unscored_only: bool = False

    def __post_init__(self):
        if self.items is None:
            self.items = []
        if self.interests is None:
            self.interests = {}
        if self.profile_meta is None:
            self.profile_meta = {}
        if self.prior is None:
            self.prior = {}
        if self.prior_top is None:
            self.prior_top = set()


def _prepare_fellowship_match(
    user: User,
    *,
    today: str | None,
    reuse_prior: bool = True,
    unscored_only: bool = False,
    log: Callable[[str], None] | None,
) -> tuple[_FellowshipMatchJob | None, OppRunResult | None]:
    """DB phase for fellowships — load items + build Elig (no embedding).

    ``unscored_only`` (the daily run) restricts the candidate items to fellowships
    this user has never been scored on, so the run evaluates the day's new arrivals
    *plus any earlier backlog a missed run left behind*, and appends them; ``False``
    (sign-up/refit) evaluates the whole fellowship corpus and replaces the feed.
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

    scored_ids: list = []
    queryset = ContentItem.objects.filter(type=ContentItem.Type.FELLOWSHIP)
    if unscored_only:
        scored_ids = _scored_content_ids(
            {"target_user": user}, ContentItem.Type.FELLOWSHIP
        )
        queryset = queryset.exclude(id__in=scored_ids)
    items = list(queryset.only("id", "metadata"))
    if not items:
        scope = "not yet scored for this user" if unscored_only else "in corpus"
        emit(f"no fellowship ContentItems {scope}")
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
        user, profile, emit=emit, exclude_ids=scored_ids
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
        prior_top=prior_top_ids(
            {"target_user": user}, ContentItem.Type.FELLOWSHIP
        ),
        embed_by_id=embed_by_id,
        has_interest_signal=has_interest_signal,
        embed_threshold=getattr(settings, "FELLOWSHIP_MATCH_THRESHOLD", 0.4),
        withhold_unverified=getattr(
            settings, "FELLOWSHIP_WITHHOLD_UNVERIFIED", False
        ),
        unscored_only=unscored_only,
    )
    return job, None


def _fellowship_embed_by_id(
    user: User, profile, *, emit: Callable[[str], None], exclude_ids: list | None = None
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
            exclude_ids=exclude_ids,
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
        withhold_unverified=job.withhold_unverified,
    )
    items_by_id = {str(item.id): item for item in job.items}
    # The slate the rule engine just produced, minus the one it replaces: the model
    # writes up fellowships the reader is about to see for the first time.
    entering = {s["content_id"] for s in ranked[: top_n()]} - job.prior_top
    return generate_fellowship_suggestions(
        job.interests,
        job.profile_meta,
        ranked,
        items_by_id,
        llm_limit=job.llm_limit,
        complete=complete,
        prior=job.prior,
        priority_ids=entering,
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
        # Whole-corpus runs (the nightly one, sign-up, refit) re-establish the feed;
        # append-only runs leave what is already there alone.
        _persist_fellowships(
            {"target_user": job.user},
            suggestions,
            visible_ids,
            items_by_id,
            pins,
            today=job.today,
            retire_missing=not job.unscored_only,
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
    retire_missing: bool = False,
) -> None:
    """Upsert one RelevanceScore per fellowship under ``persist_kwargs``'s target.

    Every surfaced fellowship is persisted (so the carry-forward store remembers
    its verdict), but only those in ``visible_ids`` (cleared the match-percent
    floor) are flagged ``suggested`` — the rest are hidden from the feed. The
    target is polymorphic: ``{"target_user": user}`` for a person's eligible feed,
    ``{"target_project": project}`` for a project's interest-matched feed.

    ``retire_missing`` (a whole-corpus run — the nightly re-rank, sign-up, or a
    refit) takes the target's prior fellowship scores that this run did not
    re-evaluate *out of the feed*: they lose ``suggested`` and their slate place, so
    a profile edit that changes eligibility stops surfacing what it no longer
    matches. The rows themselves stay, because they hold verdicts the model was paid
    for; deleting them meant a fellowship that dipped out for a day and came back
    had to be written up from scratch. An append-only run leaves it false.
    """
    run_at = timezone.now().isoformat()
    ordered = [s["content_id"] for s in suggestions if s["content_id"] in visible_ids]
    slate = compute_top(
        persist_kwargs, ContentItem.Type.FELLOWSHIP, ordered, today=today
    )
    if retire_missing:
        _retire(
            persist_kwargs,
            ContentItem.Type.FELLOWSHIP,
            keep={s["content_id"] for s in suggestions},
        )
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
        merge_top_signals(signals, slate, cid)
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
    unscored_only: bool = False,
    today: str | None = None,
    log: Callable[[str], None] | None,
) -> tuple[_MatchJob | None, OppRunResult | None]:
    """DB phase — retrieve + fuse. Returns a job to score, or a short-circuit result.

    Target-agnostic: the interests / watch topics come off the :class:`MatchTarget`,
    so this prepares a unit for a person, a lab, or a project identically.

    ``unscored_only=False`` (the nightly re-rank, sign-up, and refit) ranks the whole
    corpus against the target's current profile and re-establishes its feed from
    that; ``True`` scopes retrieval to opportunities this target has never been
    scored on and appends them, which no scheduled stage does any more.
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

    # Daily (append) mode: retrieve only what this target has never been scored on.
    exclude_ids = (
        _scored_content_ids(target.persist_kwargs, content_type)
        if unscored_only
        else None
    )

    # Cluster-scoped when the target declares >= 2 real research themes, exactly as
    # papers have been since the cluster sprint. ``fuse_clusters_pool`` was already
    # generic over ``content_type``; grants and conferences simply never dispatched
    # to it, which is why an opportunity carried no cluster attribution and the
    # cluster badge on its card stayed dark. One or no cluster keeps the flat path
    # byte-for-byte — the invariant every cluster feature in this codebase preserves.
    clusters = cluster_interests(target.interests or {})
    if len(clusters) >= 2:
        # No ``cluster_top_n``: the per-theme slate is a paper-feed concern. Grants
        # and conferences accumulate across runs rather than being re-picked from
        # one gather day, so they are not starved the way papers were.
        pairs, rows, pool, _slate = fuse_clusters_pool(
            search_ints,
            clusters,
            content_type=content_type,
            surface_limit=cap,
            pool_per_interest=pool_per_interest,
            beta=beta,
            emit=emit,
            exclude_ids=exclude_ids,
            match_threshold=threshold,
        )
    else:
        pairs, rows, pool = fuse_interests_pool(
            search_ints,
            content_type=content_type,
            surface_limit=cap,
            pool_per_interest=pool_per_interest,
            beta=beta,
            emit=emit,
            exclude_ids=exclude_ids,
            match_threshold=threshold,
        )
    if not pairs:
        scope = "not yet scored" if unscored_only else "in corpus"
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
    # The slate this run establishes, minus the one it replaces. The model's budget
    # goes to what just entered the reader's Top-25, not to what was ingested most
    # recently — an item is worth writing up when it is good enough to displace
    # something the reader was already being shown.
    entering = {str(item.id) for item, _score in pairs[: top_n()]} - prior_top_ids(
        target.persist_kwargs, content_type
    )

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
        priority_ids=entering,
        unscored_only=unscored_only,
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
        priority_ids=job.priority_ids,
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
        # Whole-corpus runs (including the nightly one) re-establish the feed;
        # append-only runs leave what is already there alone.
        visible_ids = {s["content_id"] for s in visible}
        _persist(
            job.target.persist_kwargs,
            job.content_type,
            job.rows,
            suggestions,
            visible_ids,
            pins,
            today=today,
            retire_missing=not job.unscored_only,
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
    unscored_only: bool = False,
    today: str | None = None,
    log: Callable[[str], None] | None = None,
) -> OppRunResult:
    """Retrieve → fuse → score → pin → persist one area for *any* target (serial).

    The engine for a person, a lab, or a project; the score row lands under the
    target's ``persist_kwargs`` (``target_user`` / ``target_lab`` / ``target_project``).
    ``reuse_prior=False`` bypasses carry-forward, re-sending every surfaced item to
    the model (used by :mod:`.refitting` after a profile edit). ``unscored_only``
    defaults to ``False`` (whole corpus, so this serial path — sign-up / refit —
    re-establishes the target's feed for the area from the whole corpus) — the same
    mode the nightly batch runs in. ``True`` scores only what the target has not been
    scored on yet and appends it, which no scheduled stage does any more.
    """
    job, short = _prepare_match(
        target,
        area,
        surface_limit=surface_limit,
        llm_limit=llm_limit,
        pool_per_interest=pool_per_interest,
        beta=beta,
        reuse_prior=reuse_prior,
        unscored_only=unscored_only,
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
    unscored_only: bool = False,
    today: str | None = None,
    log: Callable[[str], None] | None = None,
) -> OppRunResult:
    """Eligibility-gate + LLM-report fellowship matching for one user (serial).

    ``unscored_only`` defaults to ``False`` (whole corpus — re-establishing the
    user's fellowship feed), which is also how the nightly batch runs it. ``True``
    evaluates only the fellowships this user has not been scored on and appends.
    """
    job, short = _prepare_fellowship_match(
        user, today=today, reuse_prior=reuse_prior, unscored_only=unscored_only, log=log
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
                    unscored_only=kwargs.get("unscored_only", False),
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
    exclude_ids: list | None = None,
) -> dict[str, float] | None:
    """The target's embedding match to each fellowship (interest-only ranking).

    The institutional twin of :func:`_fellowship_embed_by_id`: it reuses the same
    multi-interest search-interest builder + retrieve/fuse step grants/conferences
    use, but reads the interests off the :class:`MatchTarget` (a lab's aggregate
    interests, a project's focus) rather than a user Profile. Returns ``None`` when
    there is nothing to rank on (no declared interests, no embedder, no embedded
    fellowships, or retrieval raised) — the caller then surfaces nothing for that
    target rather than guessing.
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
            exclude_ids=exclude_ids,
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
    unscored_only: bool = False,
    today: str | None = None,
    log: Callable[[str], None] | None = None,
) -> OppRunResult:
    """Interest-based fellowship matching for an institutional target.

    Neither a lab nor a project has a citizenship or career stage, so their
    fellowships are ranked purely on research fit to the target's interests — the
    same embedding signal grants/conferences use — then the top slice gets an LLM
    report. Scores persist under ``target.persist_kwargs`` (``target_lab`` /
    ``target_project``). ``unscored_only`` ``False`` (sign-up/refit) replaces the
    feed; ``True`` appends whatever the target has not been scored on yet.

    Who in a lab each fellowship actually *suits* — including who is personally
    eligible — is the separate recommendation layer
    (:mod:`apps.content.member_fit`); it never gates what the lab feed contains.
    """
    key = target.key

    def emit(message: str) -> None:
        if log is not None:
            log(f"[{key}:fellowships] {message}")

    from django.utils import timezone as tz

    from .fellowships import match_fellowships

    today_final = today or tz.now().date().isoformat()
    scored_ids: list = []
    queryset = ContentItem.objects.filter(type=ContentItem.Type.FELLOWSHIP)
    if unscored_only:
        scored_ids = _scored_content_ids(
            target.persist_kwargs, ContentItem.Type.FELLOWSHIP
        )
        queryset = queryset.exclude(id__in=scored_ids)
    items = list(queryset.only("id", "metadata"))
    if not items:
        return OppRunResult(
            key, "fellowships", "no_results", note="no fellowship items in DB"
        )

    embed_by_id = _target_fellowship_embed_by_id(
        target, emit=emit, exclude_ids=scored_ids
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
    entering = {s["content_id"] for s in ranked[: top_n()]} - prior_top_ids(
        target.persist_kwargs, ContentItem.Type.FELLOWSHIP
    )
    suggestions = generate_fellowship_suggestions(
        target.interests,
        target.profile_meta,
        ranked,
        items_by_id,
        llm_limit=llm_limit,
        complete=complete,
        prior=prior,
        priority_ids=entering,
    )
    floor = _opportunity_min_match_percent()
    visible, hidden = split_by_floor(suggestions, floor)
    pins = compute_pins(visible, items_by_id, today=today_final)
    new_count = sum(1 for p in pins.values() if p["is_new"])
    llm = sum(1 for s in visible if s.get("source") == "llm")
    emit(
        f"scored {len(suggestions)} {target.kind} fellowships "
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
            retire_missing=not unscored_only,
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

    All three areas run for any institutional target. **Fellowships** are ranked on
    the target's research interests with no eligibility gate — neither a lab nor a
    project has a citizenship or career stage — which is what lets a lab's
    Fellowships page be the same feed, with the same filters and cards, as the
    personal one. Personal eligibility did not disappear: it is one basis in the
    per-item member-recommendation layer (:mod:`apps.content.member_fit`).
    """
    results: list[OppRunResult] = []
    for area in areas:
        if area == "fellowships":
            results.append(
                match_fellowships_for_target(
                    target,
                    complete=kwargs.get("complete"),
                    persist=kwargs.get("persist", True),
                    reuse_prior=kwargs.get("reuse_prior", True),
                    unscored_only=kwargs.get("unscored_only", False),
                    today=kwargs.get("today"),
                    log=kwargs.get("log"),
                )
            )
            continue
        results.append(match_opportunities_for_target(target, area, **kwargs))
    return results


def run_opportunities_for_lab(lab, **kwargs) -> list[OppRunResult]:
    """Match grants + conferences (+ fellowships) for a lab's aggregate interests."""
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
    Phase 2 (match): each ``(target, area)`` unit is *prepared* — retrieve + fuse
    over the **whole corpus**, against that target's current profile — then all
    prepared units are **scored by the model concurrently** (up to ``concurrency``
    at once — the model call is the slow step and shouldn't be issued one at a
    time), then *finalized* (slate diff + New/pin + serial DB writes). A failure for
    one unit is caught so it never sinks the run.

    Re-ranking the whole corpus nightly is the point, not an expense to be optimised
    away. A feed built by appending each day's arrivals can only ever reflect the
    profile each past run happened to see, so a reader who changed their focus,
    their clusters, or their search terms kept the old list; and an item's position
    recorded when it arrived rather than how well it fits. The model is not re-billed
    for it: carry-forward reuses every verdict already written, and only items that
    newly entered a target's Top-25 are sent for a write-up.

    Every target matches every requested area — a lab's fellowships rank on its
    research interests, not on anyone's citizenship (see
    :func:`run_opportunities_for_target`). Phase 3 then re-annotates each
    institutional target's feeds with who the items are for
    (:func:`apps.content.member_fit.annotate_for_target`), best-effort: it runs
    after the day's papers have already been appended by the paper pipeline, so one
    pass covers all four areas.
    """
    if concurrency is None:
        concurrency = getattr(
            settings, "OPPORTUNITY_LLM_CONCURRENCY", DEFAULT_LLM_CONCURRENCY
        )

    def emit(message: str) -> None:
        if log is not None:
            log(message)

    # Every unit below runs with ``unscored_only=False``: the whole corpus, ranked
    # against the target's profile as it stands tonight. Items that fall out of the
    # ranking are retired from the feed but keep their verdict, so an item that dips
    # out and returns is neither re-billed nor silently re-announced.
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
                        user, today=today, unscored_only=False, log=log
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
                        unscored_only=False,
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
    from .targets import project_watch_categories, target_for_lab, target_for_project

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
                    unscored_only=False,
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

    # Institutional fellowships (interest-matched, no eligibility gate) — appended
    # for the day's new arrivals. Serial (the LLM slice is small; a target's
    # new-fellowship count on any given day is tiny), keeping this out of the
    # eligibility-coupled pool above.
    if "fellowships" in areas and (labs or projects):
        from .targets import (
            project_watch_categories,
            target_for_lab,
            target_for_project,
        )

        fellowship_targets = [target_for_lab(lab) for lab in labs]
        for project in projects:
            if "fellowships" not in project_watch_categories(project):
                continue
            fellowship_targets.append(target_for_project(project))
        for target in fellowship_targets:
            try:
                results.append(
                    match_fellowships_for_target(
                        target,
                        complete=complete,
                        persist=persist,
                        unscored_only=False,
                        today=today,
                        log=log,
                    )
                )
            except Exception:
                logger.exception(
                    "%s fellowship match failed for %s", target.kind, target.key
                )
                results.append(
                    OppRunResult(target.key, "fellowships", "error", note="failed")
                )

    # Phase 3 — who is each item for? Re-annotated over the whole feed (papers
    # included: the paper pipeline ran earlier in the daily chain), never fatal.
    if persist and (labs or projects):
        from .member_fit import annotate_for_target
        from .targets import target_for_lab, target_for_project

        for target in [
            *(target_for_lab(lab) for lab in labs),
            *(target_for_project(project) for project in projects),
        ]:
            annotate_for_target(target, complete=complete, log=log)

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
    retire_missing: bool = False,
) -> None:
    """Upsert one RelevanceScore per surfaced item, with opportunity signals.

    ``persist_kwargs`` is the single ``target_*`` FK the rows are written under
    (a user, a lab, or a project). Mirrors the paper pipeline's persist but adds
    the area discriminator, the New/pin fields, and a deadline snapshot the API /
    deadlines / notifications read back. Each surfaced item carries a ``run_at``
    stamp; the accumulate read layer keeps every run's suggested rows. Every surfaced
    item is persisted (so carry-forward remembers its verdict), but only those in
    ``visible_ids`` (cleared the match-percent floor) are flagged ``suggested``.

    ``retire_missing`` (a whole-corpus run — the nightly re-rank, sign-up, or a
    refit) takes this target's prior scores for the area that this run did not
    re-surface *out of the feed*: they lose ``suggested`` and their slate place, so
    an interest edit re-establishes the feed from the full corpus rather than
    leaving stale matches behind. The rows stay, because they hold verdicts the
    model was paid for — an item that dips below the threshold for a day and comes
    back should not have to be written up again. An append-only run leaves it false.

    Each row also records its Top-25 slate position and whether it entered on this
    run; that is what the daily report is built from.
    """
    run_at = timezone.now().isoformat()
    ordered = [s["content_id"] for s in suggestions if s["content_id"] in visible_ids]
    slate = compute_top(persist_kwargs, area, ordered, today=today)
    if retire_missing:
        _retire(persist_kwargs, area, keep={str(item.id) for item, _s, _e in rows})
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
        merge_top_signals(signals, slate, cid)
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


def _retire(persist_kwargs: dict, area: str, *, keep: set[str]) -> None:
    """Drop out of the feed every stored row for ``area`` this run did not re-surface.

    Not a delete. A retired row keeps its ``signals`` — above all the language-model
    verdict, which the carry-forward store reads back — and only loses the two things
    that mean "the reader is being shown this": ``suggested`` and its slate place.

    Deleting was the previous behaviour and it cost real work: an opportunity that
    slipped under the match threshold on one run and cleared it again on the next had
    to be sent back to the model as though it had never been seen, and it re-entered
    the report announced as new. Retiring makes both correct — re-entry is free, and
    it is reported as new because it genuinely left the reader's list and returned.
    """
    stale = RelevanceScore.objects.filter(
        **persist_kwargs, content__type=area
    ).exclude(content_id__in=list(keep))
    for row in stale:
        signals = row.signals or {}
        if not signals.get("suggested") and "top_rank" not in signals:
            continue
        signals["suggested"] = False
        signals.pop("top_rank", None)
        signals["entered_top_on"] = ""
        signals["is_new_top"] = False
        RelevanceScore.objects.filter(pk=row.pk).update(signals=signals)
