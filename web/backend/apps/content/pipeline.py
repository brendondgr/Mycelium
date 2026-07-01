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
from .models import RelevanceScore
from .ranking import DEFAULT_FOCUS_WEIGHT, RankedHit, rerank_by_focus
from .retrieval import retrieve_for_vector
from .suggest import CompleteFn, generate_suggestions

logger = logging.getLogger(__name__)

# Sensible defaults for a daily run; the command/task can override them. The
# window is intentionally tight — a daily run only needs the freshest papers, so
# it scans the last couple of days plus the next week of ahead-of-print records
# (a months-wide window pulls tens of thousands of papers to surface a handful).
DEFAULT_QUERY_LIMIT = 6
DEFAULT_TOP_K = 20
DEFAULT_SUGGESTIONS = 10
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
    focus_weight: float | None = None,
    embed: bool = True,
    persist: bool = True,
    complete: CompleteFn | None = None,
    search_fn: SearchFn | None = None,
    scan_embedder=None,
    log: Callable[[str], None] | None = None,
) -> RunResult:
    """Run the scan → RAG → re-rank → suggest pipeline for one user and store it."""
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

    hits = retrieve_for_vector(profile_vector, limit=top_k)
    if not hits:
        emit("no embedded papers to retrieve yet")
        return RunResult(
            username,
            "no_results",
            queries=queries,
            scanned_new=summary.new,
            embedded=summary.embedded,
            note="no embedded papers to retrieve yet",
        )

    # Re-rank the semantic hits by research focus: a paper that names one of the
    # user's focus areas is nudged up. With no areas this is an order-preserving
    # no-op, so retrieval order survives unchanged.
    areas = interests.get("areas") or []
    ranked = rerank_by_focus(hits, areas, weight=focus_weight)
    boosted = sum(1 for hit in ranked if hit.focus_overlap > 0)
    emit(
        f"retrieved {len(ranked)} papers (top_k={top_k}); "
        f"{boosted} focus-boosted (weight={focus_weight})"
    )

    suggestions = generate_suggestions(
        interests,
        [(hit.item, hit.similarity) for hit in ranked],
        limit=suggestion_limit,
        complete=complete,
    )
    llm = sum(1 for s in suggestions if s["source"] == "llm")
    emit(
        f"suggestions: {len(suggestions)} ({llm} llm / "
        f"{len(suggestions) - llm} fallback)"
    )

    if persist:
        _persist(user, ranked, suggestions)

    return RunResult(
        username,
        "ok",
        queries=queries,
        scanned_new=summary.new,
        embedded=summary.embedded,
        retrieved=len(ranked),
        suggestions=len(suggestions),
        llm=llm,
        fallback=len(suggestions) - llm,
    )


def _persist(user: User, ranked: list[RankedHit], suggestions) -> None:
    """Upsert one RelevanceScore per retrieved item; flag the suggested subset.

    The persisted ``score`` is the blended focus-weighted score the digest ranks
    by; ``signals`` keeps the raw similarity and focus boost alongside it so the
    ranking stays auditable. A single ``run_at`` stamp marks this run so the
    daily-report endpoint can show the latest run's suggestions and ignore items
    promoted by earlier runs.
    """
    run_at = timezone.now().isoformat()
    suggested = {s["content_id"]: s for s in suggestions}
    for hit in ranked:
        item = hit.item
        promoted = suggested.get(str(item.id))
        signals = {
            "similarity": round(hit.similarity, 4),
            "focus_overlap": round(hit.focus_overlap, 4),
            "focus_areas": hit.matched_areas,
            "run_at": run_at,
            "suggested": promoted is not None,
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
            defaults={"score": round(hit.score, 6), "signals": signals},
        )
