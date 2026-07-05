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
from collections.abc import Callable
from dataclasses import asdict, dataclass, field

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
from .retrieval import Hit, retrieve_for_vector
from .suggest import CompleteFn, generate_suggestions

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
    status: str  # ok | no_profile | no_watch_topics | no_embedder | no_results
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
    """Run the scan → retrieve → fuse → suggest pipeline for one user and store it.

    When the profile declares research ``areas`` these become per-interest search
    queries: each is retrieved via a pgvector channel and a BM25 channel, fused
    with RRF, normalized, and combined across interests so papers matching several
    interests are preferred (see :mod:`apps.content.fusion`). With no ``areas`` the
    run falls back to the original single-vector retrieval unchanged. Either way the
    top ``surface_limit`` papers are surfaced and the top ``suggestion_limit`` are
    handed to the LLM for bespoke ranking.
    """
    username = user.get_username()
    if focus_weight is None:
        focus_weight = getattr(settings, "AREA_FOCUS_WEIGHT", DEFAULT_FOCUS_WEIGHT)

    def emit(message: str) -> None:
        if log is not None:
            log(f"[{username}] {message}")

    profile = getattr(user, "profile", None)
    if profile is None:
        emit("no profile; skipping")
        return RunResult(username, "no_profile", note="user has no profile")

    interests = profile.interests or {}

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

    # Embed the profile into the *same* space as the papers and persist it so a
    # later scoring phase finds the interest vector ready.
    profile_vector = embeddings.embed_text(canonical_text(profile))
    if profile_vector is None:
        emit(
            "no embedder; stopping "
            f"({summary.embedding_skipped_reason or 'unavailable'})"
        )
        return RunResult(
            username,
            "no_embedder",
            queries=queries,
            scanned_new=summary.new,
            embedded=summary.embedded,
            note=summary.embedding_skipped_reason or "no embedder available",
        )
    if persist:
        type(profile).objects.filter(pk=profile.pk).update(embedding=profile_vector)
        profile.embedding = profile_vector

    # The declared research focus (``interests.areas``) becomes the set of search
    # interests. With areas present we run the multi-interest fusion; with none we
    # fall back to the original single-vector retrieval so those users are
    # unaffected.
    search_ints = search_interests(interests)
    retrieved_count = 0
    if search_ints:
        pairs, rows, retrieved_count = _fuse_interests(
            search_ints,
            surface_limit=surface_limit,
            pool_per_interest=pool_per_interest,
            beta=beta,
            emit=emit,
        )
    else:
        pairs, rows, retrieved_count = _single_vector(
            profile_vector,
            interests,
            top_k=max(top_k, surface_limit),
            surface_limit=surface_limit,
            focus_weight=focus_weight,
            emit=emit,
        )

    if not pairs:
        emit("no embedded papers to retrieve yet")
        return RunResult(
            username,
            "no_results",
            queries=queries,
            scanned_new=summary.new,
            embedded=summary.embedded,
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
        _persist(user, rows, suggestions)

    return RunResult(
        username,
        "ok",
        queries=queries,
        scanned_new=summary.new,
        embedded=summary.embedded,
        retrieved=retrieved_count,
        interests=len(search_ints),
        suggestions=len(suggestions),
        llm=llm,
        fallback=len(suggestions) - llm,
    )


#: A row to persist: the item, its ranking score, and the signal breakdown to
#: store under it (the ``run_at``/``suggested`` keys are added by :func:`_persist`).
PersistRow = tuple[ContentItem, float, dict]


def _fuse_interests(
    search_ints: list[SearchInterest],
    *,
    surface_limit: int,
    pool_per_interest: int,
    beta: float,
    emit: Callable[[str], None],
) -> tuple[list[Hit], list[PersistRow], int]:
    """Retrieve + fuse per interest; return suggest-pairs, persist-rows, pool size.

    Builds one candidate pool (the union of each interest's vector ANN pull),
    indexes it once for BM25, fuses the two channels per interest, combines across
    interests, and reserves each interest's best paper before truncating to
    ``surface_limit``.
    """
    pool: dict[str, ContentItem] = {}
    vector_hits: dict[str, list[Hit]] = {}
    for interest in search_ints:
        vector = embeddings.embed_text(interest.embed_text)
        if vector is None:
            continue
        unified: list[Hit] = []
        for item, similarity in retrieve_for_vector(vector, limit=pool_per_interest):
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
) -> tuple[list[Hit], list[PersistRow], int]:
    """The original single-vector path, unchanged, for profiles with no ``areas``.

    Retrieves the papers nearest the whole-profile vector and applies the lexical
    focus re-rank (a no-op with no areas). Kept so users who never declared
    research areas see exactly the behaviour they saw before this change.
    """
    hits = retrieve_for_vector(profile_vector, limit=top_k)
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


def _persist(user: User, rows: list[PersistRow], suggestions) -> None:
    """Upsert one RelevanceScore per surfaced item; flag the suggested subset.

    Each row carries its own signal breakdown (fusion's per-interest scores or the
    single-vector similarity/focus boost); this adds the shared ``run_at`` stamp,
    the ``suggested`` flag, and the promoted suggestion's rank/headline/reason/match
    so the ranking stays auditable. The single ``run_at`` stamp lets the daily
    report show only the latest run's suggestions and ignore earlier ones.
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
            target_user=user,
            defaults={"score": round(score, 6), "signals": signals},
        )
