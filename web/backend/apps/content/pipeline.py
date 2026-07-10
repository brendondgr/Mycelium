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

from . import embeddings
from .fusion import (
    DEFAULT_BETA,
    CombinedHit,
    combine_interests,
    fuse_interest,
    with_floor_guarantee,
)
from .interests_query import SearchInterest, search_interests
from .lexical import build_bm25_index, rank_bm25_over
from .models import ContentItem, RelevanceScore
from .ranking import DEFAULT_FOCUS_WEIGHT, rerank_by_focus
from .retrieval import Hit, latest_gather_date, retrieve_for_vector
from .suggest import CompleteFn, generate_suggestions
from .targets import target_for_lab, target_for_project

logger = logging.getLogger(__name__)

# Sensible defaults for a daily run; the command/task can override them. The
# window is intentionally tight — a daily run only needs the freshest papers, so
# it scans the last couple of days plus the next week of ahead-of-print records
# (a months-wide window pulls tens of thousands of papers to surface a handful).
DEFAULT_QUERY_LIMIT = 6
DEFAULT_TOP_K = 20
DEFAULT_SUGGESTIONS = 10  # top papers handed to the LLM for bespoke ranking
DEFAULT_SURFACE = 25  # total papers surfaced in the daily report
DEFAULT_POOL_PER_INTEREST = 100  # vector ANN width per interest for the pool
DEFAULT_DAYS_BACK = 2
DEFAULT_DAYS_FORWARD = 7


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


def _watch_topics(user: User) -> list[str]:
    """The user's watch topics, or an empty list if they never set any."""
    watch = getattr(user, "watch", None)
    topics = getattr(watch, "topics", None) or []
    return [str(topic) for topic in topics]


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
    surface_limit: int = DEFAULT_SURFACE,
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
        surface_limit=surface_limit,
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
    surface_limit: int = DEFAULT_SURFACE,
    pool_per_interest: int = DEFAULT_POOL_PER_INTEREST,
    beta: float = DEFAULT_BETA,
    focus_weight: float | None = None,
    complete: CompleteFn | None = None,
    persist: bool = True,
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
    """
    username = user.get_username()
    if focus_weight is None:
        focus_weight = getattr(settings, "AREA_FOCUS_WEIGHT", DEFAULT_FOCUS_WEIGHT)

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
    # Papers are recommended from the freshest batch only: the most recent day any
    # paper was gathered. This is what keeps the Research Papers page day-to-day —
    # without it the same best-matching older papers resurface run after run.
    gathered_on = latest_gather_date()

    search_ints = search_interests(interests)
    retrieved_count = 0
    if search_ints:
        pairs, rows, retrieved_count = fuse_interests_pool(
            search_ints,
            content_type=ContentItem.Type.PAPER,
            surface_limit=surface_limit,
            pool_per_interest=pool_per_interest,
            beta=beta,
            emit=emit,
            created_on=gathered_on,
        )
    else:
        pairs, rows, retrieved_count = _single_vector(
            profile_vector,
            interests,
            top_k=max(top_k, surface_limit),
            surface_limit=surface_limit,
            focus_weight=focus_weight,
            emit=emit,
            created_on=gathered_on,
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

    suggestions = generate_suggestions(
        interests,
        pairs,
        llm_limit=suggestion_limit,
        surface_limit=surface_limit,
        complete=complete,
    )
    llm = sum(1 for s in suggestions if s["source"] == "llm")
    emit(
        f"suggestions: {len(suggestions)} ({llm} llm / "
        f"{len(suggestions) - llm} fallback)"
    )

    if persist:
        _persist({"target_user": user}, rows, suggestions)

    return RunResult(
        username,
        "ok",
        queries=queries,
        scanned_new=scanned_new,
        embedded=embedded,
        retrieved=retrieved_count,
        interests=len(search_ints),
        suggestions=len(suggestions),
        llm=llm,
        fallback=len(suggestions) - llm,
    )


def recommend_for_target(
    target,
    *,
    top_k: int = DEFAULT_TOP_K,
    suggestion_limit: int = DEFAULT_SUGGESTIONS,
    surface_limit: int = DEFAULT_SURFACE,
    pool_per_interest: int = DEFAULT_POOL_PER_INTEREST,
    beta: float = DEFAULT_BETA,
    focus_weight: float | None = None,
    complete: CompleteFn | None = None,
    persist: bool = True,
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
    scanning the whole corpus.
    """
    key = target.key
    if focus_weight is None:
        focus_weight = getattr(settings, "AREA_FOCUS_WEIGHT", DEFAULT_FOCUS_WEIGHT)

    def emit(message: str) -> None:
        if log is not None:
            log(f"[{key}] {message}")

    # Same freshness gate as the personal feed: a lab/project paper feed also only
    # surfaces the most recently gathered batch, not the whole historical corpus.
    gathered_on = latest_gather_date()

    interests = target.interests or {}
    search_ints = search_interests(interests)
    retrieved_count = 0
    if search_ints:
        pairs, rows, retrieved_count = fuse_interests_pool(
            search_ints,
            content_type=ContentItem.Type.PAPER,
            surface_limit=surface_limit,
            pool_per_interest=pool_per_interest,
            beta=beta,
            emit=emit,
            created_on=gathered_on,
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
            top_k=max(top_k, surface_limit),
            surface_limit=surface_limit,
            focus_weight=focus_weight,
            emit=emit,
            created_on=gathered_on,
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

    suggestions = generate_suggestions(
        interests,
        pairs,
        llm_limit=suggestion_limit,
        surface_limit=surface_limit,
        complete=complete,
    )
    llm = sum(1 for s in suggestions if s["source"] == "llm")
    emit(
        f"suggestions: {len(suggestions)} ({llm} llm / "
        f"{len(suggestions) - llm} fallback)"
    )
    if persist:
        _persist(target.persist_kwargs, rows, suggestions)
    return RunResult(
        key,
        "ok",
        retrieved=retrieved_count,
        interests=len(search_ints),
        suggestions=len(suggestions),
        llm=llm,
        fallback=len(suggestions) - llm,
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
    surface_limit: int = DEFAULT_SURFACE,
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
    lab_targets = [target_for_lab(lab) for lab in labs]
    project_targets = [target_for_project(project) for project in projects]

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

    results: list[RunResult] = []
    for user in users:
        username = user.get_username()
        try:
            results.append(
                recommend_for_user(
                    user,
                    query_limit=query_limit,
                    top_k=top_k,
                    suggestion_limit=suggestion_limit,
                    surface_limit=surface_limit,
                    pool_per_interest=pool_per_interest,
                    beta=beta,
                    focus_weight=focus_weight,
                    complete=complete,
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
                    surface_limit=surface_limit,
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
) -> tuple[list[Hit], list[PersistRow], int]:
    """Retrieve + fuse per interest; return suggest-pairs, persist-rows, pool size.

    Builds one candidate pool (the union of each interest's vector ANN pull),
    indexes it once for BM25, fuses the two channels per interest, combines across
    interests, and reserves each interest's best item before truncating to
    ``surface_limit``. ``content_type`` scopes retrieval to papers (default) or
    grants/conferences, so the grants/conferences matcher reuses this unchanged.
    ``created_on`` (papers only) restricts the pool to the freshest gather day; the
    opportunity matchers leave it ``None`` so grants/conferences span their corpus.
    """
    pool: dict[str, ContentItem] = {}
    vector_hits: dict[str, list[Hit]] = {}
    for interest in search_ints:
        vector = embeddings.embed_text(interest.embed_text)
        if vector is None:
            continue
        unified: list[Hit] = []
        for item, similarity in retrieve_for_vector(
            vector,
            content_type=content_type,
            limit=pool_per_interest,
            created_on=created_on,
        ):
            key = str(item.id)
            pool.setdefault(key, item)
            unified.append((pool[key], similarity))
        vector_hits[interest.label] = unified

    if not pool:
        return [], [], 0

    index = build_bm25_index(list(pool.values()))
    per_interest_scores: dict[str, dict[str, float]] = {}
    for interest in search_ints:
        fused = fuse_interest(
            rank_bm25_over(interest.query_text, index),
            vector_hits.get(interest.label, []),
        )
        if fused:
            per_interest_scores[interest.label] = fused

    combined = combine_interests(per_interest_scores, pool, beta=beta)
    surfaced = with_floor_guarantee(combined, per_interest_scores, limit=surface_limit)
    emit(
        f"fused {len(search_ints)} interest(s) over {len(pool)} candidates; "
        f"surfaced {len(surfaced)}"
    )

    pairs = [(hit.item, hit.combined_score) for hit in surfaced]
    rows = [_fusion_row(hit) for hit in surfaced]
    return pairs, rows, len(pool)


def _fusion_row(hit: CombinedHit) -> PersistRow:
    signals = {
        "combined_score": round(hit.combined_score, 6),
        "per_interest": {label: round(v, 4) for label, v in hit.per_interest.items()},
        "n_matched": hit.n_matched,
        # The matched interest labels double as the report's focus themes, so the
        # daily summary's theme roll-up keeps working unchanged.
        "focus_areas": list(hit.per_interest.keys()),
    }
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
) -> tuple[list[Hit], list[PersistRow], int]:
    """The single-vector path for profiles with no ``areas``.

    Retrieves the papers nearest the whole-profile vector and applies the lexical
    focus re-rank (a no-op with no areas). Kept so users who never declared
    research areas see the same behaviour, now scoped (like every paper path) to the
    freshest gather day via ``created_on``.
    """
    hits = retrieve_for_vector(profile_vector, limit=top_k, created_on=created_on)
    if not hits:
        return [], [], 0

    areas = interests.get("areas") or []
    ranked = rerank_by_focus(hits, areas, weight=focus_weight)
    surfaced = ranked[:surface_limit]
    emit(f"retrieved {len(ranked)} papers (single-vector, top_k={top_k})")

    pairs = [(hit.item, hit.similarity) for hit in surfaced]
    rows: list[PersistRow] = [
        (
            hit.item,
            hit.score,
            {
                "similarity": round(hit.similarity, 4),
                "focus_overlap": round(hit.focus_overlap, 4),
                "focus_areas": hit.matched_areas,
            },
        )
        for hit in surfaced
    ]
    return pairs, rows, len(ranked)


def _persist(
    persist_kwargs: dict, rows: list[PersistRow], suggestions
) -> None:
    """Upsert one RelevanceScore per surfaced item; flag the suggested subset.

    ``persist_kwargs`` is the single ``target_*`` FK the rows are written under
    (``{"target_user": user}`` for the daily pipeline, ``{"target_lab": lab}`` /
    ``{"target_project": project}`` for the institutional targets). Each row carries
    its own signal breakdown (fusion's per-interest scores or the single-vector
    similarity/focus boost); this adds the shared ``run_at`` stamp, the ``suggested``
    flag, and the promoted suggestion's rank/headline/reason/match so the ranking
    stays auditable. The single ``run_at`` stamp lets the daily report show only the
    latest run's suggestions and ignore earlier ones.
    """
    run_at = timezone.now().isoformat()
    suggested = {s["content_id"]: s for s in suggestions}
    for item, score, extra in rows:
        promoted = suggested.get(str(item.id))
        signals = {**extra, "run_at": run_at, "suggested": promoted is not None}
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
