"""The literature-scan orchestrator.

``scan()`` is the single entry point both triggers (the Celery task and the
management command) call:

    queries ─► search every source over the window (concurrent)
            ─► cross-source de-duplicate (shared DOI/PMID/PMCID/ArXiv, else fuzzy)
            ─► de-duplicate against already-stored ContentItem rows (skip re-embed)
            ─► embed the genuinely-new papers (fastembed, optional)
            ─► upsert ContentItem(type=paper) rows for the RAG store

Networking and embedding are both injectable (``search_fn`` / ``embedder``) so
the test-suite runs fully offline with fake sources and a fake embedder.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field

import aiohttp

from apps.content.models import ContentItem

from .embedding import Embedder, build_article_text, get_default_embedder
from .sources.dedup import Deduplicator
from .sources.record import Record
from .sources.registry import ScraperConfig, build_scrapers, resolve_sources
from .window import ScanWindow

logger = logging.getLogger(__name__)

#: A search function maps (queries, window, sources) -> a flat list of Records.
SearchFn = Callable[[list[str], ScanWindow, list[str]], list[Record]]


@dataclass
class ScanSummary:
    """A JSON-able report of one scan, returned by ``scan`` and the task."""

    queries: list[str]
    window: str
    sources: list[str]
    raw: int = 0
    unique: int = 0
    already_present: int = 0
    new: int = 0
    embedded: int = 0
    upserted: int = 0
    embedding_skipped_reason: str | None = None
    by_source: dict[str, int] = field(default_factory=dict)
    #: Per (source, query) hit counts from the search phase: {source, query, count}.
    by_source_query: list[dict] = field(default_factory=list)
    #: Wall-clock seconds for each phase: search / dedup / against_store / embed /
    #: upsert / total.
    timings: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)


def _emit(log: Callable[[str], None] | None, message: str) -> None:
    """Send a verbose progress line to the optional run-log callback."""
    if log is not None:
        log(message)


def _noop_progress(status: str, records: int, pages: int, detail: str) -> None:
    pass


async def _search_all(
    queries: list[str], window: ScanWindow, sources: list[str], config: ScraperConfig
) -> tuple[list[Record], list[tuple[str, str, int]]]:
    """Run every (scraper × query) concurrently; a failed task is logged, not fatal.

    Returns the flat record list plus a per (source, query) hit-count breakdown
    (count ``-1`` marks a task that errored) for the verbose run log.
    """
    connector = aiohttp.TCPConnector(limit=32)
    async with aiohttp.ClientSession(connector=connector) as session:
        scrapers = build_scrapers(session, config, sources)
        tasks = [
            (scraper.name, query, scraper.search(query, window, _noop_progress))
            for scraper in scrapers
            for query in queries
        ]
        gathered = await asyncio.gather(*(t[2] for t in tasks), return_exceptions=True)

    records: list[Record] = []
    breakdown: list[tuple[str, str, int]] = []
    for (name, query, _), result in zip(tasks, gathered, strict=True):
        if isinstance(result, Exception):
            logger.warning("scraper %s failed for %r: %s", name, query, result)
            breakdown.append((name, query, -1))
            continue
        records.extend(result)
        breakdown.append((name, query, len(result)))
    return records, breakdown


def _live_search(
    queries: list[str], window: ScanWindow, sources: list[str]
) -> tuple[list[Record], list[tuple[str, str, int]]]:
    config = ScraperConfig.from_settings()
    return asyncio.run(_search_all(queries, window, sources, config))


def _external_id(record: Record) -> str:
    # ContentItem.external_id is max_length=255; truncate deterministically so the
    # existence check and the stored key always agree across runs.
    return record.canonical_id[:255]


def scan(
    queries: list[str],
    *,
    window: ScanWindow | None = None,
    months_back: int = 2,
    months_forward: int = 1,
    sources: list[str] | None = None,
    embed: bool = True,
    search_fn: SearchFn | None = None,
    embedder: Embedder | None = None,
    log: Callable[[str], None] | None = None,
) -> ScanSummary:
    """Search, deduplicate, embed, and upsert papers into the RAG store.

    Returns a :class:`ScanSummary`. Embedding is best-effort: when fastembed is
    unavailable (or fails), rows are still upserted with ``embedding=NULL`` and
    ``embedding_skipped_reason`` explains why. ``log`` (optional) receives a
    verbose, step-by-step progress line for each phase so a caller can record a
    timestamped run log and see where the time goes.
    """
    queries = [q.strip() for q in (queries or []) if q and q.strip()]
    resolved_sources = resolve_sources(sources)
    window = window or ScanWindow.around_today(months_back, months_forward)
    summary = ScanSummary(queries=queries, window=str(window), sources=resolved_sources)
    if not queries:
        return summary

    _emit(log, f"scan start: window {window}, sources {resolved_sources}")
    _emit(log, f"queries ({len(queries)}): {', '.join(queries)}")

    # --- 1. Search every source over the window. ---------------------------- #
    started = time.monotonic()
    if search_fn is not None:
        records = search_fn(queries, window, resolved_sources)
        breakdown: list[tuple[str, str, int]] = []
    else:
        records, breakdown = _live_search(queries, window, resolved_sources)
    summary.raw = len(records)
    summary.timings["search"] = round(time.monotonic() - started, 2)

    summary.by_source_query = [
        {"source": source, "query": query, "count": count}
        for source, query, count in breakdown
    ]
    by_source_found: dict[str, int] = {}
    for source, query, count in breakdown:
        label = f"{count} papers" if count >= 0 else "FAILED"
        _emit(log, f"  search: {source} × {query!r} -> {label}")
        if count > 0:
            by_source_found[source] = by_source_found.get(source, 0) + count
    if by_source_found:
        per_source = ", ".join(f"{s}={n}" for s, n in sorted(by_source_found.items()))
        _emit(log, f"  search per-source: {per_source}")
    _emit(
        log,
        f"search done: {summary.raw} papers in {summary.timings['search']}s",
    )

    # --- 2. Cross-source de-duplication. ------------------------------------ #
    started = time.monotonic()
    dedup = Deduplicator()
    for record in records:
        dedup.add(record)
    unique = dedup.results()
    summary.unique = len(unique)
    summary.timings["dedup"] = round(time.monotonic() - started, 2)
    _emit(
        log,
        f"cross-source dedup: {summary.raw} -> {summary.unique} unique "
        f"({summary.raw - summary.unique} merged) in {summary.timings['dedup']}s",
    )

    # --- 3. De-duplicate against rows we already store (skip re-embedding). - #
    started = time.monotonic()
    candidates = [(record, _external_id(record)) for record in unique]
    ext_ids = [ext for _, ext in candidates]
    existing = set(
        ContentItem.objects.filter(external_id__in=ext_ids).values_list(
            "external_id", flat=True
        )
    )
    fresh = [(record, ext) for record, ext in candidates if ext not in existing]
    summary.already_present = summary.unique - len(fresh)
    summary.new = len(fresh)
    summary.timings["against_store"] = round(time.monotonic() - started, 2)
    _emit(
        log,
        f"against store: {summary.new} new, {summary.already_present} already "
        f"present in {summary.timings['against_store']}s",
    )
    if not fresh:
        _emit(log, _tally(summary))
        return summary

    # --- 4. Embed the new papers (optional / pluggable). -------------------- #
    started = time.monotonic()
    vectors: list[list[float] | None] = [None] * len(fresh)
    if embed:
        emb = embedder if embedder is not None else get_default_embedder()
        if emb is None:
            summary.embedding_skipped_reason = (
                "fastembed not installed (install with: uv sync --extra embeddings)"
            )
        else:
            texts = [build_article_text(record) for record, _ in fresh]
            try:
                computed = emb(texts)
            except Exception as exc:  # noqa: BLE001 - degrade to NULL embeddings, don't crash.
                logger.warning("embedding failed: %s", exc)
                summary.embedding_skipped_reason = f"embedder error: {exc}"
                computed = []
            if len(computed) == len(fresh):
                vectors = list(computed)
                summary.embedded = sum(1 for v in vectors if v)
            elif computed:
                summary.embedding_skipped_reason = (
                    f"embedder returned {len(computed)} vectors for {len(fresh)} papers"
                )
    summary.timings["embed"] = round(time.monotonic() - started, 2)
    if summary.embedding_skipped_reason:
        _emit(log, f"embed skipped: {summary.embedding_skipped_reason}")
    else:
        _emit(
            log,
            f"embed: {summary.embedded}/{summary.new} papers in "
            f"{summary.timings['embed']}s",
        )

    # --- 5. Upsert into the RAG store. -------------------------------------- #
    started = time.monotonic()
    by_source: dict[str, int] = {}
    for (record, ext), vector in zip(fresh, vectors, strict=True):
        defaults = {
            "type": ContentItem.Type.PAPER,
            "source_url": (record.url or "")[:500],
            "metadata": {
                **record.to_metadata(),
                "queries": queries,
                "scanned_window": str(window),
            },
        }
        if vector is not None:
            defaults["embedding"] = vector
        ContentItem.objects.update_or_create(
            source=record.source,
            external_id=ext,
            defaults=defaults,
        )
        by_source[record.source] = by_source.get(record.source, 0) + 1
        summary.upserted += 1

    summary.by_source = by_source
    summary.timings["upsert"] = round(time.monotonic() - started, 2)
    summary.timings["total"] = round(sum(summary.timings.values()), 2)
    _emit(log, f"upsert: {summary.upserted} papers in {summary.timings['upsert']}s")
    _emit(log, _tally(summary))
    return summary


def _tally(summary: ScanSummary) -> str:
    """The one-line final tally after full de-duplication, with total time."""
    total = summary.timings.get("total")
    if total is None:
        total = round(sum(summary.timings.values()), 2)
    return (
        "tally: "
        f"raw={summary.raw} unique={summary.unique} "
        f"already_present={summary.already_present} new={summary.new} "
        f"embedded={summary.embedded} upserted={summary.upserted} "
        f"total={total}s"
    )
