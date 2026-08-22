"""The per-user daily research pipeline.

For one user this strings the existing pieces into the daily loop the product has
been building toward:

    watch topics      ─► literature scan (ingest fresh papers + embed them)
    profile interests ─► embed the profile (statement + keywords) into that space
                      ─► pgvector retrieve the nearest papers (RAG)
                      ─► re-rank by research focus (weighted areas boost)
                      ─► language-model suggestions (with a deterministic fallback)
                      ─► persist as RelevanceScore rows (score + digest signals)

The two halves draw on *different* parts of the profile, by design:

- The **search** is driven solely by the user's :class:`WatchPreference` topics —
  the one place that decides what literature gets pulled in at all.
- The **ranking** uses the profile's semantic vector (statement + keywords) for
  retrieval, then the declared research focus (``interests.areas``) as a weighted
  re-rank boost; the focus and keywords are also handed to the language model so
  it can judge and explain why a paper matters to *this* researcher.

It runs for *every* user (see :mod:`apps.content.tasks`); a single run is scoped
here so it can be tested and triggered in isolation. Every external seam — the
search, the embedder, the language model — is injectable so the suite runs
offline, and every missing capability degrades to a clear status instead of a
crash.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date

from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone

from apps.accounts.embedding import canonical_text
from apps.scraper.ingest import SearchFn, scan
from apps.scraper.window import ScanWindow

from . import embeddings, reranking
from .clustering import Cluster, cluster_interests
from .digest_selection import renumber, split_by_floor
from .fusion import (
    DEFAULT_BETA,
    DEFAULT_RRF_K,
    ClusteredHit,
    CombinedHit,
    SpreadPolicy,
    apply_spread,
    cap_clusters,
    cluster_relative_pass,
    combine_clusters,
    combine_interests,
    fuse_interest,
    top_per_cluster,
    with_floor_guarantee,
)
from .interests_query import SearchInterest, search_interests
from .lexical import build_bm25_index, rank_bm25_over
from .models import ContentItem, RelevanceScore
from .opportunity_llm import load_prior_llm_verdicts
from .pinning import compute_pins
from .protocols import Retrievable, VectorIndex
from .ranking import DEFAULT_FOCUS_WEIGHT, rerank_by_focus
from .retrieval import (
    Hit,
    PgVectorIndex,
    latest_gather_date,
    retrieve_for_vector,
)
from .suggest import CompleteFn, generate_suggestions
from .targets import target_for_lab, target_for_project
from .top_feed import compute_top, merge_top_signals, prior_top_ids, top_n

logger = logging.getLogger(__name__)

# Sensible defaults for a daily run; the command/task can override them. The
# window is intentionally tight — a daily run only needs the freshest papers, so
# it scans the last couple of days plus the next week of ahead-of-print records
# (a months-wide window pulls tens of thousands of papers to surface a handful).
DEFAULT_QUERY_LIMIT = 6
DEFAULT_TOP_K = 20
DEFAULT_SUGGESTIONS = 10  # top papers handed to the LLM for bespoke ranking
DEFAULT_POOL_PER_INTEREST = 100  # vector ANN width per interest for the pool
DEFAULT_DAYS_BACK = 2
DEFAULT_DAYS_FORWARD = 7

# Fallback paper-feed sizing when the settings are absent (tests, bare configs).
# In production these come from PAPER_MATCH_THRESHOLD / PAPER_MATCH_MAX_SURFACE.
_FALLBACK_MATCH_THRESHOLD = 0.5
_FALLBACK_MAX_SURFACE = 250
# Papers each theme of an institutional target contributes (PAPER_CLUSTER_TOP_N).
_FALLBACK_CLUSTER_TOP_N = 10


def _paper_match_threshold() -> float:
    """The embedding-match floor for surfacing a paper (settings-tunable)."""
    return getattr(settings, "PAPER_MATCH_THRESHOLD", _FALLBACK_MATCH_THRESHOLD)


def _paper_max_surface() -> int:
    """The backstop cap on how many papers a run may surface (settings-tunable)."""
    return getattr(settings, "PAPER_MATCH_MAX_SURFACE", _FALLBACK_MAX_SURFACE)


def _paper_min_match_percent() -> int:
    """The match-percent floor below which an LLM verdict stays hidden."""
    return getattr(settings, "PAPER_MIN_MATCH_PERCENT", 60)


def _paper_cluster_top_n() -> int:
    """How many papers each of an institutional target's themes contributes."""
    return getattr(settings, "PAPER_CLUSTER_TOP_N", _FALLBACK_CLUSTER_TOP_N)


@dataclass
class RunResult:
    """A JSON-able report of one user's run."""

    username: str
    # ok | no_profile | no_watch_topics | no_interests | no_embedder | no_results
    status: str
    queries: list[str] = field(default_factory=list)
    scanned_new: int = 0
    embedded: int = 0
    retrieved: int = 0
    interests: int = 0  # search interests fused (0 = single-vector fallback path)
    suggestions: int = 0
    llm: int = 0
    fallback: int = 0
    hidden: int = 0  # scored below the match-percent floor; persisted, not surfaced
    note: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def build_queries(topics: list[str], *, limit: int = DEFAULT_QUERY_LIMIT) -> list[str]:
    """Dedupe and cap the user's watch topics into literature-scan queries.

    The watch topics are the *sole* source of search terms — nothing in the
    interests profile drives the scan. Order is preserved (the user's stated
    priority); duplicates collapse case-insensitively.
    """
    terms: list[str] = []
    seen: set[str] = set()
    for value in topics or []:
        text = " ".join(str(value).split())
        fold = text.casefold()
        if text and fold not in seen:
            seen.add(fold)
            terms.append(text)
    return terms[:limit]


def _force_fallback(_prompt: str) -> None:
    """A ``complete`` seam that always declines — forces the deterministic path.

    The Free tier's "semantic only" is exactly this: surface the same rows, but skip
    the reasoned LLM verdict (A3). Reused wherever a target lacks LLM_FIT_SCORING.
    """
    return None


def _watch_topics(user: User) -> list[str]:
    """The user's watch topics, capped to their tier's cap (never deleted).

    Reading through the entitlement helper means a downgraded user's overflow
    topics are ignored here, not acted on — the excess is preserved in storage and
    only the first N drive the scan / recommend.
    """
    from apps.billing.entitlements import effective_watch_topics

    return [str(topic) for topic in effective_watch_topics(user)]


def gather_scan_queries(
    users: Sequence[User],
    *,
    per_user_limit: int = DEFAULT_QUERY_LIMIT,
    global_limit: int | None = None,
    log: Callable[[str], None] | None = None,
) -> list[str]:
    """The deduped union of every user's watch topics — the global scan term set.

    Phase 1 of the batch run searches this union *once* instead of re-searching
    each user's overlapping topics per user. Each user contributes up to
    ``per_user_limit`` normalized topics (their stated priority); across users the
    terms collapse case-insensitively, order-preserving. ``global_limit`` caps the
    total (logged, never silent) to bound a pathological run.
    """
    terms: list[str] = []
    seen: set[str] = set()
    for user in users:
        for term in build_queries(_watch_topics(user), limit=per_user_limit):
            fold = term.casefold()
            if fold not in seen:
                seen.add(fold)
                terms.append(term)
    if global_limit is not None and len(terms) > global_limit:
        if log is not None:
            log(f"gathered {len(terms)} unique terms; capping to {global_limit}")
        terms = terms[:global_limit]
    return terms


def run_for_user(
    user: User,
    *,
    days_back: int = DEFAULT_DAYS_BACK,
    days_forward: int = DEFAULT_DAYS_FORWARD,
    sources: list[str] | None = None,
    query_limit: int = DEFAULT_QUERY_LIMIT,
    top_k: int = DEFAULT_TOP_K,
    suggestion_limit: int = DEFAULT_SUGGESTIONS,
    match_threshold: float | None = None,
    max_surface: int | None = None,
    pool_per_interest: int = DEFAULT_POOL_PER_INTEREST,
    beta: float = DEFAULT_BETA,
    focus_weight: float | None = None,
    embed: bool = True,
    persist: bool = True,
    complete: CompleteFn | None = None,
    search_fn: SearchFn | None = None,
    scan_embedder=None,
    log: Callable[[str], None] | None = None,
) -> RunResult:
    """Scan *this* user's watch topics, then recommend — the single-user path.

    Convenience for the ``--user`` CLI and tests: it ingests just this user's
    topics and then recommends. The batch daily run (:func:`run_daily_batch`)
    instead ingests every user's topics *once* and then recommends per user; both
    share :func:`recommend_for_user` for the recommend half.
    """
    username = user.get_username()

    def emit(message: str) -> None:
        if log is not None:
            log(f"[{username}] {message}")

    profile = getattr(user, "profile", None)
    if profile is None:
        emit("no profile; skipping")
        return RunResult(username, "no_profile", note="user has no profile")

    # The search is driven *only* by the user's watch topics — the profile's
    # areas/keywords shape ranking, never the scan query set.
    queries = build_queries(_watch_topics(user), limit=query_limit)
    if not queries:
        emit("no watch topics set; skipping (nothing to search for)")
        return RunResult(
            username, "no_watch_topics", note="user has no watch topics to search"
        )

    emit(
        f"start: {len(queries)} queries, "
        f"window {days_back}d back / {days_forward}d fwd"
    )
    summary = scan(
        queries,
        window=ScanWindow.around_today_days(days_back, days_forward),
        sources=sources,
        embed=embed,
        search_fn=search_fn,
        embedder=scan_embedder,
        log=log,
    )

    return recommend_for_user(
        user,
        query_limit=query_limit,
        top_k=top_k,
        suggestion_limit=suggestion_limit,
        match_threshold=match_threshold,
        max_surface=max_surface,
        pool_per_interest=pool_per_interest,
        beta=beta,
        focus_weight=focus_weight,
        complete=complete,
        persist=persist,
        log=log,
        scan_summary=summary,
    )


def recommend_for_user(
    user: User,
    *,
    query_limit: int = DEFAULT_QUERY_LIMIT,
    top_k: int = DEFAULT_TOP_K,
    suggestion_limit: int = DEFAULT_SUGGESTIONS,
    match_threshold: float | None = None,
    max_surface: int | None = None,
    pool_per_interest: int = DEFAULT_POOL_PER_INTEREST,
    beta: float = DEFAULT_BETA,
    focus_weight: float | None = None,
    complete: CompleteFn | None = None,
    persist: bool = True,
    reuse_prior: bool = True,
    log: Callable[[str], None] | None = None,
    scan_summary=None,
) -> RunResult:
    """Retrieve → fuse → suggest for one user against the *already-populated* store.

    The recommend half of the pipeline, with **no scanning of its own** — it reads
    whatever papers the ingest phase already stored. When the profile declares
    research ``areas`` these become per-interest queries fused via BM25 + pgvector
    RRF so papers matching several interests are preferred; with no ``areas`` it
    falls back to single-vector retrieval. ``scan_summary`` (when a caller just
    scanned for this user) only feeds the reported ``scanned_new``/``embedded``
    counts; the batch path leaves it ``None`` since ingestion was global.
    ``reuse_prior=False`` bypasses carry-forward, re-sending every surfaced paper to
    the model (used by :mod:`.refitting` after a profile edit).
    """
    username = user.get_username()
    if focus_weight is None:
        focus_weight = getattr(settings, "AREA_FOCUS_WEIGHT", DEFAULT_FOCUS_WEIGHT)
    if match_threshold is None:
        match_threshold = _paper_match_threshold()
    if max_surface is None:
        max_surface = _paper_max_surface()

    def emit(message: str) -> None:
        if log is not None:
            log(f"[{username}] {message}")

    scanned_new = scan_summary.new if scan_summary is not None else 0
    embedded = scan_summary.embedded if scan_summary is not None else 0
    skip_reason = (
        scan_summary.embedding_skipped_reason if scan_summary is not None else None
    )

    profile = getattr(user, "profile", None)
    if profile is None:
        emit("no profile; skipping")
        return RunResult(username, "no_profile", note="user has no profile")

    interests = profile.interests or {}

    # Only recommend to users who opted into monitoring (have watch topics) —
    # identical to the single-user gate, so batch and CLI stay consistent.
    queries = build_queries(_watch_topics(user), limit=query_limit)
    if not queries:
        emit("no watch topics set; skipping (nothing to recommend against)")
        return RunResult(
            username, "no_watch_topics", note="user has no watch topics"
        )

    # Embed the profile into the *same* space as the papers and persist it so a
    # later scoring phase finds the interest vector ready.
    profile_vector = embeddings.embed_text(canonical_text(profile))
    if profile_vector is None:
        emit(f"no embedder; stopping ({skip_reason or 'unavailable'})")
        return RunResult(
            username,
            "no_embedder",
            queries=queries,
            scanned_new=scanned_new,
            embedded=embedded,
            note=skip_reason or "no embedder available",
        )
    if persist:
        type(profile).objects.filter(pk=profile.pk).update(embedding=profile_vector)
        profile.embedding = profile_vector

    # The declared research focus (``interests.areas``) becomes the set of search
    # interests. With areas present we run the multi-interest fusion; with none we
    # fall back to the original single-vector retrieval so those users are
    # unaffected.
    # Papers are the daily-search exception: the Research Papers page shows only the
    # *freshest gather batch* — "what is new for the search that day" — never items
    # from a previous day's search. So retrieval is scoped to ``latest_gather_date``
    # (the freshest day any paper was gathered); a quiet scan day shows the last good
    # batch rather than an empty page, but old and new are never mixed. Opportunities
    # accumulate instead (see :mod:`.opportunities`); papers deliberately do not.
    created_on = latest_gather_date(content_type=ContentItem.Type.PAPER)
    search_ints = search_interests(interests)
    # Cluster-scoped scoring kicks in only with >= 2 clusters; with one (implicit or
    # a lone named cluster) it is identical to the flat path, so those users and all
    # v1 profiles score byte-identically to today (no cluster attribution).
    clusters = cluster_interests(interests)
    retrieved_count = 0
    if search_ints and len(clusters) >= 2:
        # A person's own feed keeps the global ranking (no ``cluster_top_n``): their
        # areas are specific enough that the strongest papers already spread across
        # them. The per-cluster slate exists for institutional targets, whose areas
        # are broad theme names — see :func:`recommend_for_target`.
        pairs, rows, retrieved_count, _slate = fuse_clusters_pool(
            search_ints,
            clusters,
            content_type=ContentItem.Type.PAPER,
            surface_limit=max_surface,
            pool_per_interest=pool_per_interest,
            beta=beta,
            emit=emit,
            created_on=created_on,
            match_threshold=match_threshold,
        )
    elif search_ints:
        pairs, rows, retrieved_count = fuse_interests_pool(
            search_ints,
            content_type=ContentItem.Type.PAPER,
            surface_limit=max_surface,
            pool_per_interest=pool_per_interest,
            beta=beta,
            emit=emit,
            created_on=created_on,
            match_threshold=match_threshold,
        )
    else:
        pairs, rows, retrieved_count = _single_vector(
            profile_vector,
            interests,
            top_k=max(top_k, max_surface),
            surface_limit=max_surface,
            focus_weight=focus_weight,
            emit=emit,
            created_on=created_on,
            match_threshold=match_threshold,
        )

    if not pairs:
        emit("no embedded papers to retrieve yet")
        return RunResult(
            username,
            "no_results",
            queries=queries,
            scanned_new=scanned_new,
            embedded=embedded,
            interests=len(search_ints),
            note="no embedded papers to retrieve yet",
        )

    # The pipeline has already filtered ``pairs`` by the embedding-match threshold,
    # so surface all of them; only the top ``suggestion_limit`` go to the model.
    prior = (
        load_prior_llm_verdicts({"target_user": user}, ContentItem.Type.PAPER)
        if reuse_prior
        else {}
    )
    today_iso = timezone.now().date().isoformat()
    # The slate this run is about to establish, and the one it replaces. The model's
    # budget goes to papers that just entered — the reader is seeing those for the
    # first time — not to whatever happened to be ingested most recently.
    was_top = prior_top_ids({"target_user": user}, ContentItem.Type.PAPER)
    entering = {str(item.id) for item, _score in pairs[: top_n()]} - was_top
    suggestions = generate_suggestions(
        interests,
        pairs,
        llm_limit=suggestion_limit,
        complete=complete,
        prior=prior,
        priority_ids=entering,
        cluster_by_id=_cluster_by_id(rows),
    )
    floor = _paper_min_match_percent()
    visible, hidden = split_by_floor(suggestions, floor)
    # Ranks were handed out over the pre-floor list; close the gaps the hidden
    # papers leave behind so the feed numbers what it actually shows.
    renumber(visible)
    llm = sum(1 for s in visible if s["source"] == "llm")
    emit(
        f"suggestions: {len(visible)} ({llm} llm / "
        f"{len(visible) - llm} fallback)"
        + (f", {len(hidden)} hidden below floor" if hidden else "")
    )

    if persist:
        visible_ids = {s["content_id"] for s in visible}
        _persist(
            {"target_user": user},
            ContentItem.Type.PAPER,
            rows,
            suggestions,
            visible_ids,
            today=today_iso,
        )

    return RunResult(
        username,
        "ok",
        queries=queries,
        scanned_new=scanned_new,
        embedded=embedded,
        retrieved=retrieved_count,
        interests=len(search_ints),
        suggestions=len(visible),
        llm=llm,
        fallback=len(visible) - llm,
        hidden=len(hidden),
    )


def recommend_for_target(
    target,
    *,
    top_k: int = DEFAULT_TOP_K,
    suggestion_limit: int = DEFAULT_SUGGESTIONS,
    match_threshold: float | None = None,
    max_surface: int | None = None,
    pool_per_interest: int = DEFAULT_POOL_PER_INTEREST,
    beta: float = DEFAULT_BETA,
    focus_weight: float | None = None,
    complete: CompleteFn | None = None,
    persist: bool = True,
    reuse_prior: bool = True,
    cluster_top_n: int | None = None,
    log: Callable[[str], None] | None = None,
) -> RunResult:
    """Retrieve → fuse → suggest research papers for *any* target (lab / project).

    The institutional twin of :func:`recommend_for_user`, over the
    already-populated store (no scanning). It shares the whole engine —
    per-interest BM25 + pgvector fusion when the target declares ``areas``, else a
    single-vector fallback — but drops the user-only bits (the watch-topic opt-in
    gate and persisting the profile's own vector) and writes each score under the
    target's ``persist_kwargs`` (``target_lab`` / ``target_project``). A target
    with no interests at all short-circuits to ``no_interests`` rather than
    scanning the whole corpus. ``reuse_prior=False`` bypasses carry-forward (used by
    :mod:`.refitting` after a profile edit).

    **One deliberate divergence from the personal path.** A lab that has organised
    its work into themes gets its papers chosen **per theme**: each cluster's own
    best ``cluster_top_n`` candidates form a slate that Mylo reads theme by theme,
    and every slate member is surfaced. Two reasons the global ranking was the
    wrong instrument here:

    * A lab's areas are broad theme names, not a person's specific keywords, so one
      theme's vocabulary consistently sits closer to the day's literature. Ranked
      globally, that theme takes the whole model budget and the rest of the lab
      reads as though nothing was found for it.
    * Because the model only ever judged the global top slice, the feed was
      ``{papers the model liked} ∪ {papers it never saw}`` — which is why a lab
      could end up with seven papers, two of them explained. Choosing per theme and
      judging everything chosen makes the feed one coherent set.

    A slate member is therefore never withheld by ``PAPER_MIN_MATCH_PERCENT``: the
    pipeline picked it as one of that theme's best, and hiding it would leave the
    same gap-riddled list the split was meant to fix. The floor still applies to
    everything outside the slate.
    """
    key = target.key
    if focus_weight is None:
        focus_weight = getattr(settings, "AREA_FOCUS_WEIGHT", DEFAULT_FOCUS_WEIGHT)
    if match_threshold is None:
        match_threshold = _paper_match_threshold()
    if max_surface is None:
        max_surface = _paper_max_surface()
    if cluster_top_n is None:
        cluster_top_n = _paper_cluster_top_n()

    def emit(message: str) -> None:
        if log is not None:
            log(f"[{key}] {message}")

    # Same fresh-only rule as the personal feed: a lab/project paper feed shows only
    # the freshest gather batch (scoped by ``latest_gather_date``), never a previous
    # day's search. Opportunities accumulate; papers do not.
    created_on = latest_gather_date(content_type=ContentItem.Type.PAPER)
    interests = target.interests or {}
    search_ints = search_interests(interests)
    clusters = cluster_interests(interests)
    retrieved_count = 0
    slate_groups: list[list[Hit]] = []
    if search_ints and len(clusters) >= 2:
        pairs, rows, retrieved_count, slate_groups = fuse_clusters_pool(
            search_ints,
            clusters,
            content_type=ContentItem.Type.PAPER,
            surface_limit=max_surface,
            pool_per_interest=pool_per_interest,
            beta=beta,
            emit=emit,
            created_on=created_on,
            match_threshold=match_threshold,
            cluster_top_n=cluster_top_n,
        )
    elif search_ints:
        pairs, rows, retrieved_count = fuse_interests_pool(
            search_ints,
            content_type=ContentItem.Type.PAPER,
            surface_limit=max_surface,
            pool_per_interest=pool_per_interest,
            beta=beta,
            emit=emit,
            created_on=created_on,
            match_threshold=match_threshold,
        )
    elif target.stored_vector or target.embedding_text.strip():
        # A project with a recomputed team profile (Feature D) carries its blended
        # team vector on the target; prefer it over embedding the focus text.
        vector = target.stored_vector or embeddings.embed_text(target.embedding_text)
        if vector is None:
            emit("no embedder; stopping")
            return RunResult(key, "no_embedder", note="no embedder available")
        pairs, rows, retrieved_count = _single_vector(
            vector,
            interests,
            top_k=max(top_k, max_surface),
            surface_limit=max_surface,
            focus_weight=focus_weight,
            emit=emit,
            created_on=created_on,
            match_threshold=match_threshold,
        )
    else:
        emit("no interests to recommend on; skipping")
        return RunResult(key, "no_interests", note="no interests/areas to match on")

    if not pairs:
        emit("no embedded papers to retrieve yet")
        return RunResult(
            key,
            "no_results",
            interests=len(search_ints),
            note="no embedded papers to retrieve yet",
        )

    prior = (
        load_prior_llm_verdicts(target.persist_kwargs, ContentItem.Type.PAPER)
        if reuse_prior
        else {}
    )
    today_iso = timezone.now().date().isoformat()
    was_top = prior_top_ids(target.persist_kwargs, ContentItem.Type.PAPER)
    entering = {str(item.id) for item, _score in pairs[: top_n()]} - was_top
    suggestions = generate_suggestions(
        interests,
        pairs,
        # With a per-theme slate the budget is per group, not one global slice.
        llm_limit=cluster_top_n if slate_groups else suggestion_limit,
        complete=complete,
        prior=prior,
        priority_ids=entering,
        cluster_by_id=_cluster_by_id(rows),
        llm_groups=slate_groups or None,
    )
    floor = _paper_min_match_percent()
    visible, hidden = split_by_floor(suggestions, floor)
    slate_ids = {str(item.id) for group in slate_groups for item, _score in group}
    reinstated = [s for s in hidden if s["content_id"] in slate_ids]
    if reinstated:
        # A paper this run chose as one of its theme's best is shown with Mylo's
        # honest percent rather than withheld — see the docstring. Rebuilding from
        # ``suggestions`` keeps everything in its already-correct position.
        hidden = [s for s in hidden if s["content_id"] not in slate_ids]
        shown = {s["content_id"] for s in visible + reinstated}
        visible = [s for s in suggestions if s["content_id"] in shown]
    renumber(visible)
    llm = sum(1 for s in visible if s["source"] == "llm")
    emit(
        f"suggestions: {len(visible)} ({llm} llm / "
        f"{len(visible) - llm} fallback)"
        + (f", {len(hidden)} hidden below floor" if hidden else "")
    )
    if persist:
        visible_ids = {s["content_id"] for s in visible}
        _persist(
            target.persist_kwargs,
            ContentItem.Type.PAPER,
            rows,
            suggestions,
            visible_ids,
            today=today_iso,
        )
    return RunResult(
        key,
        "ok",
        retrieved=retrieved_count,
        interests=len(search_ints),
        suggestions=len(visible),
        llm=llm,
        fallback=len(visible) - llm,
        hidden=len(hidden),
    )


def recommend_for_lab(lab, **kwargs) -> RunResult:
    """Recommend research papers for a lab's aggregate interests."""
    from .targets import target_for_lab

    return recommend_for_target(target_for_lab(lab), **kwargs)


def recommend_for_project(project, **kwargs) -> RunResult:
    """Recommend research papers for one project's declared focus."""
    from .targets import target_for_project

    return recommend_for_target(target_for_project(project), **kwargs)


@dataclass
class BatchResult:
    """One batch run: the global ingest stats plus each user's recommend result."""

    ingest: dict = field(default_factory=dict)
    results: list[RunResult] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"ingest": self.ingest, "users": [r.as_dict() for r in self.results]}


def run_daily_batch(
    users: Sequence[User],
    *,
    labs: Sequence = (),
    projects: Sequence = (),
    days_back: int = DEFAULT_DAYS_BACK,
    days_forward: int = DEFAULT_DAYS_FORWARD,
    sources: list[str] | None = None,
    query_limit: int = DEFAULT_QUERY_LIMIT,
    global_query_limit: int | None = None,
    top_k: int = DEFAULT_TOP_K,
    suggestion_limit: int = DEFAULT_SUGGESTIONS,
    match_threshold: float | None = None,
    max_surface: int | None = None,
    pool_per_interest: int = DEFAULT_POOL_PER_INTEREST,
    beta: float = DEFAULT_BETA,
    focus_weight: float | None = None,
    embed: bool = True,
    persist: bool = True,
    complete: CompleteFn | None = None,
    search_fn: SearchFn | None = None,
    scan_embedder=None,
    log: Callable[[str], None] | None = None,
) -> BatchResult:
    """Two-phase daily run: ingest once, then recommend for every target.

    **Phase 1 (ingest, once):** gather the deduped union of all targets' watch
    topics — the users' plus any labs' and projects' — and run a single
    :func:`~apps.scraper.ingest.scan` over it, so a shared topic is searched once
    and all new papers are embedded together in one batched pass.

    **Phase 2 (recommend):** retrieve + fuse + suggest against the now-populated
    store, with no scanning per target — first each user (the watch-gated personal
    path), then each lab and project (their aggregate / declared focus). A failure
    for one target is caught and logged so it never sinks the batch.
    """
    from .targets import project_watch_categories

    lab_targets = [target_for_lab(lab) for lab in labs]
    # A project only gets daily paper recommendations if it opted into the papers
    # category (default on); an off-papers project is skipped so neither its scan
    # terms nor a paper feed are produced for it.
    project_targets = [
        target_for_project(project)
        for project in projects
        if "papers" in project_watch_categories(project)
    ]

    def emit(message: str) -> None:
        if log is not None:
            log(message)

    queries = gather_scan_queries(
        users, per_user_limit=query_limit, global_limit=global_query_limit, log=log
    )
    # Fold the labs' and projects' watch topics into the same shared scan so the
    # corpus covers their focus too (users still drive the bulk of the terms).
    queries = _extend_queries(
        queries,
        (t.watch_topics for t in (*lab_targets, *project_targets)),
        per_limit=query_limit,
        global_limit=global_query_limit,
        log=log,
    )
    summary = None
    if queries:
        emit(
            f"ingest: {len(queries)} unique term(s) across {len(users)} user(s), "
            f"window {days_back}d back / {days_forward}d fwd"
        )
        summary = scan(
            queries,
            window=ScanWindow.around_today_days(days_back, days_forward),
            sources=sources,
            embed=embed,
            search_fn=search_fn,
            embedder=scan_embedder,
            log=log,
        )
        emit(
            f"ingest done: {summary.new} new / {summary.embedded} embedded / "
            f"{summary.upserted} upserted"
        )
    else:
        emit("ingest: no watch topics across any user; nothing to scan")

    # LLM gate (A3): a user without LLM fit scoring gets the deterministic path,
    # not the model verdict. Resolved in bulk to avoid an N+1 over users.
    from apps.billing.entitlements import Feature, users_with_feature

    llm_users = users_with_feature(
        Feature.LLM_FIT_SCORING, [user.id for user in users]
    )

    results: list[RunResult] = []
    for user in users:
        username = user.get_username()
        user_complete = complete if user.id in llm_users else _force_fallback
        try:
            results.append(
                recommend_for_user(
                    user,
                    query_limit=query_limit,
                    top_k=top_k,
                    suggestion_limit=suggestion_limit,
                    match_threshold=match_threshold,
                    max_surface=max_surface,
                    pool_per_interest=pool_per_interest,
                    beta=beta,
                    focus_weight=focus_weight,
                    complete=user_complete,
                    persist=persist,
                    log=log,
                )
            )
        except Exception:
            logger.exception("recommend failed for %s", username)
            emit(f"[{username}] ERROR (see worker log)")
            results.append(RunResult(username, "error", note="recommend failed"))

    # Labs and projects recommend over the *same* store — no scan of their own.
    for target in (*lab_targets, *project_targets):
        try:
            results.append(
                recommend_for_target(
                    target,
                    top_k=top_k,
                    suggestion_limit=suggestion_limit,
                    match_threshold=match_threshold,
                    max_surface=max_surface,
                    pool_per_interest=pool_per_interest,
                    beta=beta,
                    focus_weight=focus_weight,
                    complete=complete,
                    persist=persist,
                    log=log,
                )
            )
        except Exception:
            logger.exception("recommend failed for %s %s", target.kind, target.key)
            emit(f"[{target.key}] ERROR (see worker log)")
            results.append(RunResult(target.key, "error", note="recommend failed"))

    return BatchResult(ingest=_ingest_summary(queries, summary), results=results)


def _extend_queries(
    base: list[str],
    topics_lists,
    *,
    per_limit: int,
    global_limit: int | None,
    log: Callable[[str], None] | None,
) -> list[str]:
    """Append more targets' watch topics to the scan union (deduped, capped)."""
    seen = {term.casefold() for term in base}
    out = list(base)
    for topics in topics_lists:
        for term in build_queries(list(topics), limit=per_limit):
            fold = term.casefold()
            if fold not in seen:
                seen.add(fold)
                out.append(term)
    if global_limit is not None and len(out) > global_limit:
        if log is not None:
            log(f"gathered {len(out)} unique terms; capping to {global_limit}")
        out = out[:global_limit]
    return out


def _ingest_summary(queries: list[str], summary) -> dict:
    """The global ingest stats as a JSON-able dict for the batch return/log."""
    data: dict = {"unique_queries": len(queries)}
    if summary is not None:
        data.update(
            new=summary.new,
            embedded=summary.embedded,
            upserted=summary.upserted,
            embedding_skipped_reason=summary.embedding_skipped_reason,
        )
    return data


#: A row to persist: the item, its ranking score, and the signal breakdown to
#: store under it (the ``run_at``/``suggested`` keys are added by :func:`_persist`).
PersistRow = tuple[ContentItem, float, dict]


def fuse_interests_pool(
    search_ints: list[SearchInterest],
    *,
    content_type: str = ContentItem.Type.PAPER,
    surface_limit: int,
    pool_per_interest: int,
    beta: float,
    emit: Callable[[str], None],
    created_on: date | None = None,
    exclude_ids: Sequence | None = None,
    match_threshold: float | None = None,
    index: VectorIndex | None = None,
) -> tuple[list[Hit], list[PersistRow], int]:
    """Retrieve + fuse per interest; return suggest-pairs, persist-rows, pool size.

    Builds one candidate pool (the union of each interest's vector ANN pull),
    indexes it once for BM25, fuses the two channels per interest, and combines
    across interests. ``content_type`` scopes retrieval to papers (default) or
    grants/conferences, so the grants/conferences matcher reuses this unchanged.
    ``created_on`` (papers only) restricts the pool to the freshest gather day; the
    opportunity matchers leave it ``None`` so grants/conferences span their corpus.
    ``exclude_ids`` drops candidates the caller has already handled — the daily
    opportunity run passes the ids it has already scored for this target, so the
    pool is exactly the target's unscored backlog.

    Two surfacing modes:

    - ``match_threshold is None`` (grants/conferences): reserve each interest's best
      paper, then truncate to a fixed ``surface_limit`` — the original behaviour,
      unchanged, so the opportunity matcher is unaffected.
    - ``match_threshold`` set (the paper feed): surface *every* candidate whose best
      transformer (embedding) cosine match across the interests clears the threshold
      — a variable-length list — capped only by ``surface_limit`` as a backstop. Each
      surfaced row records that cosine as ``embedding_match`` for the UI.

    ``index`` overrides the vector channel (default: pgvector over the content
    store). It is the sole seam an offline evaluation harness needs — see
    :mod:`apps.content.protocols`.
    """
    pool, per_interest_scores, best_cosine = _build_pool(
        search_ints,
        content_type=content_type,
        pool_per_interest=pool_per_interest,
        created_on=created_on,
        exclude_ids=exclude_ids,
        index=index,
    )
    if not pool:
        return [], [], 0

    combined = combine_interests(per_interest_scores, pool, beta=beta)
    combined, rerank_rank = _apply_rerank(
        combined,
        search_ints=search_ints,
        per_interest_scores=per_interest_scores,
        pool=pool,
        content_type=content_type,
        emit=emit,
    )
    if match_threshold is None:
        surfaced = with_floor_guarantee(
            combined, per_interest_scores, limit=surface_limit
        )
        emit(
            f"fused {len(search_ints)} interest(s) over {len(pool)} candidates; "
            f"surfaced {len(surfaced)}"
        )
        pairs = [(hit.item, hit.combined_score) for hit in surfaced]
        rows = [_fusion_row(hit, rerank_rank=rerank_rank) for hit in surfaced]
        return pairs, rows, len(pool)

    # Threshold mode: keep everything above the embedding-match floor (combined is
    # already best-first), capped at surface_limit as a backstop.
    passing = [
        hit
        for hit in combined
        if best_cosine.get(str(hit.item.id), 0.0) >= match_threshold
    ]
    surfaced = passing[:surface_limit]
    emit(
        f"fused {len(search_ints)} interest(s) over {len(pool)} candidates; "
        f"{len(passing)} cleared the {round(match_threshold * 100)}% match threshold"
        f"{f' (capped to {surface_limit})' if len(passing) > surface_limit else ''}"
    )
    pairs = [(hit.item, hit.combined_score) for hit in surfaced]
    rows = [
        _fusion_row(
            hit,
            match=best_cosine.get(str(hit.item.id)),
            rerank_rank=rerank_rank,
        )
        for hit in surfaced
    ]
    return pairs, rows, len(pool)


def _apply_rerank(
    hits: list,
    *,
    search_ints: list[SearchInterest],
    per_interest_scores: dict[str, dict[str, float]],
    pool: dict[str, Retrievable],
    content_type: str | None,
    emit: Callable[[str], None],
) -> tuple[list, dict[str, int]]:
    """Reorder ``hits`` with the cross-encoder, or return them untouched.

    The one place the rerank stage enters the deployed pipeline. It sits here —
    the tail of the *shared* fusion path — so the personal, lab and project feeds
    get it from one implementation rather than three, and so the pool it reorders
    is exactly the pool production already built.

    Returns ``(hits, rank_by_id)``; ``rank_by_id`` is empty when the stage did not
    run, and is written into the persist rows so the audit trail shows what moved.

    Off unless ``RERANK_ENABLED`` and the content type is listed — and a missing
    model, a missing extra or a failed batch all return the fused order rather
    than raising. See :mod:`apps.content.reranking` for what the evidence behind
    this stage is and, more importantly, what it is not.
    """
    if not hits or not reranking.enabled_for(content_type):
        return hits, {}
    scorer = reranking.get_scorer()
    if scorer is None:
        return hits, {}

    before = [str(hit.item.id) for hit in hits]
    order = reranking.rerank_order(
        before,
        items_by_id=pool,
        per_interest_scores=per_interest_scores,
        queries={i.label: i.query_text for i in search_ints},
        score=scorer,
        rrf_k=DEFAULT_RRF_K,
    )
    if order == before:
        return hits, {}

    by_id = {str(hit.item.id): hit for hit in hits}
    reordered = [by_id[key] for key in order if key in by_id]
    moved = sum(1 for a, b in zip(before, order, strict=True) if a != b)
    emit(f"reranked {len(before)} candidate(s); {moved} changed position")
    return reordered, {key: index + 1 for index, key in enumerate(order)}


def _build_pool(
    search_ints: list[SearchInterest],
    *,
    content_type: str,
    pool_per_interest: int,
    created_on: date | None,
    exclude_ids: Sequence | None = None,
    index: VectorIndex | None = None,
) -> tuple[dict[str, Retrievable], dict[str, dict[str, float]], dict[str, float]]:
    """Retrieve one shared candidate pool and fuse every interest over it.

    Shared by the flat (:func:`fuse_interests_pool`) and cluster-scoped
    (:func:`fuse_clusters_pool`) paths: build the union of each interest's vector
    ANN pull, index it once for BM25, and fuse the two channels per interest.
    Returns ``(pool, per_interest_scores, best_cosine)`` — ``per_interest_scores``
    maps ``interest_label -> {item_id: [0,1] fused score}`` and ``best_cosine``
    the best raw transformer cosine each candidate earned in any interest's vector
    channel (the paper feed thresholds on it). An empty pool returns empties.

    ``index`` is the vector channel. It defaults to
    :class:`apps.content.retrieval.PgVectorIndex` scoped by ``content_type`` and
    ``created_on`` — i.e. production is unchanged — and is the single parameter an
    offline evaluation harness overrides to score this same code against an
    external collection without a database. When it is supplied, ``content_type``
    and ``created_on`` are the index's business, not this function's.
    """
    if index is None:
        index = PgVectorIndex(content_type=content_type, created_on=created_on)
    pool: dict[str, Retrievable] = {}
    vector_hits: dict[str, list[Hit]] = {}
    best_cosine: dict[str, float] = {}
    for interest in search_ints:
        vector = embeddings.embed_text(interest.embed_text)
        if vector is None:
            continue
        unified: list[Hit] = []
        for item, similarity in index.search(
            vector,
            limit=pool_per_interest,
            exclude_ids=exclude_ids,
        ):
            key = str(item.id)
            pool.setdefault(key, item)
            unified.append((pool[key], similarity))
            if similarity > best_cosine.get(key, 0.0):
                best_cosine[key] = similarity
        vector_hits[interest.label] = unified

    if not pool:
        return {}, {}, {}

    bm25_index = build_bm25_index(list(pool.values()))
    per_interest_scores: dict[str, dict[str, float]] = {}
    for interest in search_ints:
        fused = fuse_interest(
            rank_bm25_over(interest.query_text, bm25_index),
            vector_hits.get(interest.label, []),
        )
        if fused:
            per_interest_scores[interest.label] = fused
    return pool, per_interest_scores, best_cosine


def fuse_clusters_pool(
    search_ints: list[SearchInterest],
    clusters: list[Cluster],
    *,
    content_type: str = ContentItem.Type.PAPER,
    surface_limit: int,
    pool_per_interest: int,
    beta: float,
    emit: Callable[[str], None],
    created_on: date | None = None,
    exclude_ids: Sequence | None = None,
    match_threshold: float | None = None,
    cluster_top_n: int = 0,
    spread: SpreadPolicy | None = None,
    index: VectorIndex | None = None,
) -> tuple[list[Hit], list[PersistRow], int, list[list[Hit]]]:
    """Cluster-scoped twin of :func:`fuse_interests_pool` (papers, >= 2 clusters).

    Builds the same shared pool and per-interest scores, then combines **within
    each cluster** (:func:`.fusion.combine_clusters`) so the breadth bonus never
    spans clusters. A paper's final score is the max over its cluster scores and
    its attribution is the argmax cluster; a >= 2-cluster paper carries the others
    as bridges. Surfacing mirrors the flat path but the truncation guarantee is
    per-cluster (:func:`.fusion.cap_clusters` reserves each cluster's best), and
    each row records the cluster attribution for the UI/report.

    With ``cluster_top_n`` set, it additionally returns **slate groups** — each
    cluster's own best ``cluster_top_n`` candidates (:func:`.fusion.top_per_cluster`),
    one group per cluster. Any slate member the global surfacing missed is folded
    into the surfaced set, so the slate is always a subset of what is persisted.
    That union may exceed ``surface_limit`` by at most ``cluster_top_n`` per
    cluster: a deliberate, bounded overshoot, because the whole point of the slate
    is that a theme's ten best must survive whatever the global cut does.
    Returns ``[]`` for the slate when ``cluster_top_n`` is 0.

    ``spread`` (default ``None``) replaces the surfacing step with one of the
    theme-spread policies in :mod:`.fusion`. When it is ``None`` — every deployed
    caller today — not a line of that code runs and this function behaves exactly
    as described above. When it is set, the returned ``pairs``/``rows`` are **in
    the policy's order and must not be re-sorted**: re-sorting by ``final_score``
    is precisely what makes the slate inert, since a rescued candidate is by
    definition below the global cut. The slate is not folded in under a spread
    policy, because the policy is itself the theme protection.

    ``index`` overrides the vector channel exactly as in
    :func:`fuse_interests_pool`.
    """
    pool, per_interest_scores, best_cosine = _build_pool(
        search_ints,
        content_type=content_type,
        pool_per_interest=pool_per_interest,
        created_on=created_on,
        exclude_ids=exclude_ids,
        index=index,
    )
    if not pool:
        return [], [], 0, []

    cluster_areas = {cluster.id: cluster.areas for cluster in clusters}
    labels_by_id = {cluster.id: cluster.label for cluster in clusters}
    clustered = combine_clusters(
        per_interest_scores,
        cluster_areas,
        pool,
        beta=beta,
        merge="max" if spread is None else spread.merge,
        rrf_k=DEFAULT_RRF_K if spread is None else spread.rrf_k,
    )
    # Reordered once, ahead of both branches, so the global ranking, the
    # threshold cut and the per-theme slate all read the same order. Reranking
    # only the global list would let a theme's "best" paper disagree with the
    # feed's.
    clustered, rerank_rank = _apply_rerank(
        clustered,
        search_ints=search_ints,
        per_interest_scores=per_interest_scores,
        pool=pool,
        content_type=content_type,
        emit=emit,
    )

    if spread is not None:
        return _surface_with_spread(
            clustered,
            spread=spread,
            rerank_rank=rerank_rank,
            best_cosine=best_cosine,
            match_threshold=match_threshold,
            surface_limit=surface_limit,
            labels_by_id=labels_by_id,
            n_clusters=len(clusters),
            pool_size=len(pool),
            emit=emit,
        )

    if match_threshold is None:
        surfaced = cap_clusters(clustered, limit=surface_limit)
        note = ""
    else:
        passing = [
            hit
            for hit in clustered
            if best_cosine.get(str(hit.item.id), 0.0) >= match_threshold
        ]
        # cap_clusters is a no-op below surface_limit (the common case) and otherwise
        # reserves each cluster's best paper before the backstop truncation.
        surfaced = cap_clusters(passing, limit=surface_limit)
        note = (
            f"{len(passing)} cleared the {round(match_threshold * 100)}% match "
            "threshold"
            f"{f' (capped to {surface_limit})' if len(passing) > surface_limit else ''}"
        )

    slate = top_per_cluster(clustered, limit=cluster_top_n) if cluster_top_n else {}
    if slate:
        seen = {str(hit.item.id) for hit in surfaced}
        added = 0
        for hits in slate.values():
            for hit in hits:
                key = str(hit.item.id)
                if key not in seen:
                    seen.add(key)
                    surfaced.append(hit)
                    added += 1
        surfaced.sort(key=lambda hit: hit.final_score, reverse=True)
        note += (
            f"{'; ' if note else ''}top {cluster_top_n} per cluster over "
            f"{len(slate)} cluster(s) (+{added} beyond the global cut)"
        )

    emit(
        f"fused {len(clusters)} cluster(s) over {len(pool)} candidates; "
        + (note or f"surfaced {len(surfaced)}")
    )
    def _match_of(hit: ClusteredHit) -> float | None:
        # The opportunity matchers run threshold-free and record no cosine.
        if match_threshold is None:
            return None
        return best_cosine.get(str(hit.item.id))

    pairs = [(hit.item, hit.final_score) for hit in surfaced]
    rows = [
        _cluster_row(
            hit, labels_by_id, match=_match_of(hit), rerank_rank=rerank_rank
        )
        for hit in surfaced
    ]
    slate_groups = [
        [(hit.item, hit.final_score) for hit in hits] for hits in slate.values()
    ]
    return pairs, rows, len(pool), slate_groups


def _surface_with_spread(
    clustered: list[ClusteredHit],
    *,
    spread: SpreadPolicy,
    best_cosine: dict[str, float],
    match_threshold: float | None,
    surface_limit: int,
    labels_by_id: dict[str, str],
    n_clusters: int,
    pool_size: int,
    emit: Callable[[str], None],
    rerank_rank: dict[str, int] | None = None,
) -> tuple[list[Hit], list[PersistRow], int, list[list[Hit]]]:
    """The surfacing half of :func:`fuse_clusters_pool` under a spread policy.

    Split out rather than branched inline so the deployed path above stays
    literally untouched — the whole point of the ``spread=None`` default is that
    a reader can see today's behaviour is not merely *equivalent* but *identical*.

    Two differences from the deployed path, both deliberate:

    - Admission may be widened per theme (``admit="per_cluster"``), because one
      absolute cosine threshold across a whole profile silently excludes a theme
      whose vocabulary sits further from the corpus.
    - The selected list is returned in the policy's order and never re-sorted.

    No slate: under a spread policy the ordering rule *is* the theme protection,
    and folding a slate in on top would confound the thing being measured.
    """
    if match_threshold is None:
        passing = list(clustered)
        note = "threshold-free"
    else:
        admitted = {
            str(hit.item.id)
            for hit in clustered
            if best_cosine.get(str(hit.item.id), 0.0) >= match_threshold
        }
        global_n = len(admitted)
        if spread.admit == "per_cluster":
            admitted |= cluster_relative_pass(clustered, frac=spread.admit_frac)
        elif spread.admit != "global":
            raise ValueError(f"unknown admit {spread.admit!r}")
        passing = [hit for hit in clustered if str(hit.item.id) in admitted]
        note = f"{global_n} cleared the {round(match_threshold * 100)}% match threshold"
        if len(passing) > global_n:
            note += f" (+{len(passing) - global_n} by per-theme relative floor)"

    surfaced = apply_spread(passing, policy=spread, limit=surface_limit)
    emit(
        f"fused {n_clusters} cluster(s) over {pool_size} candidates; {note}; "
        f"spread merge={spread.merge} select={spread.select or 'none'} "
        f"admit={spread.admit} surfaced {len(surfaced)} of {len(passing)}"
    )

    def _match_of(hit: ClusteredHit) -> float | None:
        if match_threshold is None:
            return None
        return best_cosine.get(str(hit.item.id))

    pairs = [(hit.item, hit.final_score) for hit in surfaced]
    rows = [
        _cluster_row(
            hit, labels_by_id, match=_match_of(hit), rerank_rank=rerank_rank
        )
        for hit in surfaced
    ]
    return pairs, rows, pool_size, []


def _cluster_row(
    hit: ClusteredHit,
    labels_by_id: dict[str, str],
    *,
    match: float | None = None,
    rerank_rank: dict[str, int] | None = None,
) -> PersistRow:
    """A persist row for a cluster-scoped hit — the flat signals plus attribution.

    Keeps ``per_interest``/``focus_areas`` (so the chips and the report's theme
    roll-up keep working unchanged) and adds ``cluster_id``/``cluster_label``,
    the ``per_cluster`` score map, and ``bridge_cluster_ids`` — the attribution the
    serializers surface as "% match · Cluster" and the secondary bridge badge.
    """
    signals = {
        "combined_score": round(hit.final_score, 6),
        "per_interest": {label: round(v, 4) for label, v in hit.per_interest.items()},
        "n_matched": hit.n_matched,
        "focus_areas": list(hit.per_interest.keys()),
        "cluster_id": hit.cluster_id,
        "cluster_label": labels_by_id.get(hit.cluster_id, ""),
        "per_cluster": {cid: round(v, 4) for cid, v in hit.per_cluster.items()},
        "bridge_cluster_ids": list(hit.bridge_cluster_ids),
    }
    if match is not None:
        signals["embedding_match"] = round(match, 4)
    _record_rerank(signals, hit, rerank_rank)
    return (hit.item, hit.final_score, signals)


def _record_rerank(
    signals: dict, hit, rerank_rank: dict[str, int] | None
) -> None:
    """Note the cross-encoder's placement on a persist row, when it ran.

    Absent entirely when the stage is off, so an un-reranked row is byte-identical
    to what this pipeline wrote before the stage existed — which is what makes
    "flag off changes nothing" checkable rather than asserted.
    """
    if not rerank_rank:
        return
    position = rerank_rank.get(str(hit.item.id))
    if position is not None:
        signals["rerank_rank"] = position


def _cluster_by_id(rows: list[PersistRow]) -> dict[str, str]:
    """Map ``content_id -> attributed cluster label`` from the persist rows.

    Only cluster-scoped rows carry ``cluster_label``; the flat / single-cluster
    path yields an empty map, so :func:`.suggest.generate_suggestions` writes its
    rationale exactly as before for those users.
    """
    return {
        str(item.id): extra["cluster_label"]
        for item, _score, extra in rows
        if extra.get("cluster_label")
    }


def _fusion_row(
    hit: CombinedHit,
    *,
    match: float | None = None,
    rerank_rank: dict[str, int] | None = None,
) -> PersistRow:
    signals = {
        "combined_score": round(hit.combined_score, 6),
        "per_interest": {label: round(v, 4) for label, v in hit.per_interest.items()},
        "n_matched": hit.n_matched,
        # The matched interest labels double as the report's focus themes, so the
        # daily summary's theme roll-up keeps working unchanged.
        "focus_areas": list(hit.per_interest.keys()),
    }
    # The paper feed records the transformer cosine match so the UI can show it on
    # the cross-embedding tail (which carries no language-model percent).
    if match is not None:
        signals["embedding_match"] = round(match, 4)
    _record_rerank(signals, hit, rerank_rank)
    return (hit.item, hit.combined_score, signals)


def _single_vector(
    profile_vector: list[float],
    interests: dict,
    *,
    top_k: int,
    surface_limit: int,
    focus_weight: float,
    emit: Callable[[str], None],
    created_on: date | None = None,
    match_threshold: float | None = None,
) -> tuple[list[Hit], list[PersistRow], int]:
    """The single-vector path for profiles with no ``areas``.

    Retrieves the papers nearest the whole-profile vector and applies the lexical
    focus re-rank (a no-op with no areas). Kept so users who never declared
    research areas see the same behaviour, now scoped (like every paper path) to the
    freshest gather day via ``created_on``. With ``match_threshold`` set, surfaces
    every paper whose cosine ``similarity`` clears it (variable count, backstopped by
    ``surface_limit``) and records that cosine as ``embedding_match``; otherwise it
    truncates to a fixed ``surface_limit``.
    """
    hits = retrieve_for_vector(profile_vector, limit=top_k, created_on=created_on)
    if not hits:
        return [], [], 0

    areas = interests.get("areas") or []
    ranked = rerank_by_focus(hits, areas, weight=focus_weight)
    if match_threshold is None:
        surfaced = ranked[:surface_limit]
        emit(f"retrieved {len(ranked)} papers (single-vector, top_k={top_k})")
    else:
        passing = [hit for hit in ranked if hit.similarity >= match_threshold]
        surfaced = passing[:surface_limit]
        emit(
            f"retrieved {len(ranked)} papers (single-vector, top_k={top_k}); "
            f"{len(passing)} cleared the {round(match_threshold * 100)}% match "
            f"threshold"
        )

    pairs = [(hit.item, hit.similarity) for hit in surfaced]
    rows: list[PersistRow] = [
        (
            hit.item,
            hit.score,
            {
                "similarity": round(hit.similarity, 4),
                "focus_overlap": round(hit.focus_overlap, 4),
                "focus_areas": hit.matched_areas,
                **(
                    {"embedding_match": round(hit.similarity, 4)}
                    if match_threshold is not None
                    else {}
                ),
            },
        )
        for hit in surfaced
    ]
    return pairs, rows, len(ranked)


def _persist(
    persist_kwargs: dict,
    content_type: str,
    rows: list[PersistRow],
    suggestions,
    visible_ids: set[str],
    *,
    today: str | None = None,
) -> None:
    """Upsert one RelevanceScore per surfaced item; flag the suggested subset.

    ``persist_kwargs`` is the single ``target_*`` FK the rows are written under
    (``{"target_user": user}`` for the daily pipeline, ``{"target_lab": lab}`` /
    ``{"target_project": project}`` for the institutional targets). Each row carries
    its own signal breakdown (fusion's per-interest scores or the single-vector
    similarity/focus boost); this adds the shared ``run_at`` stamp, the ``suggested``
    flag, the New/pin state, and the promoted suggestion's rank/headline/reason/match
    so the ranking stays auditable. The single ``run_at`` stamp lets the daily report
    show only the latest run's suggestions and ignore earlier ones. Every surfaced
    paper is persisted (so carry-forward remembers its verdict), but only those in
    ``visible_ids`` (cleared the match-percent floor) are flagged ``suggested``.

    The paper feed is scoped to the freshest gather batch (see the fresh-only note in
    :func:`recommend_for_user`), so each surfaced paper is from the latest day's
    search; those gathered within the last week are tagged New and pinned to the top.
    Papers carry no ``metadata.first_seen``, so :func:`.pinning.compute_pins` falls
    back to the item's ingest date (``created_at``) as the first-seen date. Pins are
    computed only for the visible (above-floor) items — a hidden paper never shows a
    New badge.

    It also records each row's place in the target's Top-25 slate and whether it
    entered on this run (:func:`apps.content.top_feed.compute_top`, read against the
    slate this write is about to replace). That is what the daily report reads: the
    pin above is the *feed's* week-long New badge, a different question that keeps
    its own answer.
    """
    run_at = timezone.now().isoformat()
    slate = compute_top(
        persist_kwargs,
        content_type,
        [s["content_id"] for s in suggestions if s["content_id"] in visible_ids],
        today=today,
    )
    suggested = {s["content_id"]: s for s in suggestions}
    items_by_id = {str(item.id): item for item, _score, _extra in rows}
    pins = compute_pins(
        [{"content_id": cid} for cid in items_by_id if cid in visible_ids],
        items_by_id,
    )
    for item, score, extra in rows:
        cid = str(item.id)
        promoted = suggested.get(cid)
        pin = pins.get(cid, {})
        signals = {
            **extra,
            "run_at": run_at,
            "suggested": promoted is not None and cid in visible_ids,
            "is_new": pin.get("is_new", False),
            "pinned_until": pin.get("pinned_until"),
            "first_seen": pin.get("first_seen", ""),
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
