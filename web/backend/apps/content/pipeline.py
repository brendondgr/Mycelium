"""The per-user daily research pipeline.

For one user this strings the existing pieces into the daily loop the product has
been building toward:

    profile interests ─► literature scan (ingest fresh papers + embed them)
                      ─► embed the profile into the same space
                      ─► pgvector retrieve the nearest papers (RAG)
                      ─► language-model suggestions (with a deterministic fallback)
                      ─► persist as RelevanceScore rows (score + digest signals)

It runs for *every* user (see :mod:`apps.content.tasks`); a single run is scoped
here so it can be tested and triggered in isolation. Every external seam — the
search, the embedder, the language model — is injectable so the suite runs
offline, and every missing capability degrades to a clear status instead of a
crash.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field

from django.contrib.auth.models import User
from django.utils import timezone

from apps.accounts.embedding import canonical_text
from apps.scraper.ingest import SearchFn, scan
from apps.scraper.window import ScanWindow

from . import embeddings
from .models import RelevanceScore
from .retrieval import retrieve_for_vector
from .suggest import CompleteFn, generate_suggestions

logger = logging.getLogger(__name__)

# Sensible defaults for a daily run; the command/task can override them. The
# window is intentionally tight — a daily run only needs the freshest papers, so
# it scans the last couple of days plus the next week of ahead-of-print records
# (a months-wide window pulls tens of thousands of papers to surface a handful).
DEFAULT_QUERY_LIMIT = 6
DEFAULT_TOP_K = 20
DEFAULT_SUGGESTIONS = 5
DEFAULT_DAYS_BACK = 2
DEFAULT_DAYS_FORWARD = 7


@dataclass
class RunResult:
    """A JSON-able report of one user's run."""

    username: str
    status: str  # ok | no_profile | no_interests | no_embedder | no_results
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


def build_queries(interests: dict, *, limit: int = DEFAULT_QUERY_LIMIT) -> list[str]:
    """Search terms for a profile: its research areas then specific keywords."""
    interests = interests or {}
    terms: list[str] = []
    seen: set[str] = set()
    for key in ("areas", "keywords"):
        for value in interests.get(key) or []:
            text = " ".join(str(value).split())
            fold = text.casefold()
            if text and fold not in seen:
                seen.add(fold)
                terms.append(text)
    return terms[:limit]


def run_for_user(
    user: User,
    *,
    days_back: int = DEFAULT_DAYS_BACK,
    days_forward: int = DEFAULT_DAYS_FORWARD,
    sources: list[str] | None = None,
    query_limit: int = DEFAULT_QUERY_LIMIT,
    top_k: int = DEFAULT_TOP_K,
    suggestion_limit: int = DEFAULT_SUGGESTIONS,
    embed: bool = True,
    persist: bool = True,
    complete: CompleteFn | None = None,
    search_fn: SearchFn | None = None,
    scan_embedder=None,
) -> RunResult:
    """Run the scan → RAG → suggest pipeline for one user and store the result."""
    profile = getattr(user, "profile", None)
    if profile is None:
        return RunResult(user.get_username(), "no_profile", note="user has no profile")

    interests = profile.interests or {}
    queries = build_queries(interests, limit=query_limit)
    if not queries:
        return RunResult(
            user.get_username(), "no_interests", note="profile has no areas/keywords"
        )

    summary = scan(
        queries,
        window=ScanWindow.around_today_days(days_back, days_forward),
        sources=sources,
        embed=embed,
        search_fn=search_fn,
        embedder=scan_embedder,
    )

    # Embed the profile into the *same* space as the papers and persist it so a
    # later scoring phase finds the interest vector ready.
    profile_vector = embeddings.embed_text(canonical_text(profile))
    if profile_vector is None:
        return RunResult(
            user.get_username(),
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
        return RunResult(
            user.get_username(),
            "no_results",
            queries=queries,
            scanned_new=summary.new,
            embedded=summary.embedded,
            note="no embedded papers to retrieve yet",
        )

    suggestions = generate_suggestions(
        interests, hits, limit=suggestion_limit, complete=complete
    )

    if persist:
        _persist(user, hits, suggestions)

    return RunResult(
        user.get_username(),
        "ok",
        queries=queries,
        scanned_new=summary.new,
        embedded=summary.embedded,
        retrieved=len(hits),
        suggestions=len(suggestions),
        llm=sum(1 for s in suggestions if s["source"] == "llm"),
        fallback=sum(1 for s in suggestions if s["source"] == "fallback"),
    )


def _persist(user: User, hits, suggestions) -> None:
    """Upsert one RelevanceScore per retrieved item; flag the suggested subset.

    A single ``run_at`` stamp marks this run so the daily-report endpoint can show
    the latest run's suggestions and ignore items promoted by earlier runs.
    """
    run_at = timezone.now().isoformat()
    suggested = {s["content_id"]: s for s in suggestions}
    for item, similarity in hits:
        promoted = suggested.get(str(item.id))
        signals = {
            "similarity": round(float(similarity), 4),
            "run_at": run_at,
            "suggested": promoted is not None,
        }
        if promoted is not None:
            signals.update(
                rank=promoted["rank"],
                headline=promoted["headline"],
                reason=promoted["reason"],
                source=promoted["source"],
            )
        RelevanceScore.objects.update_or_create(
            content=item,
            target_user=user,
            defaults={"score": round(float(similarity), 6), "signals": signals},
        )
