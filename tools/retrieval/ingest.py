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
from django.db.models import Q

from tools.retrieval.embedding import Embedder, build_article_text, get_default_embedder
from tools.retrieval.models import ContentItem
from tools.retrieval.sources.dedup import (
    Deduplicator,
    metadata_identifier_keys,
)
from tools.retrieval.sources.dedup import (
    identifier_keys as _record_identifier_keys,
)
from tools.retrieval.sources.record import Record
from tools.retrieval.sources.registry import (
    ScraperConfig,
    build_scrapers,
    resolve_sources,
)
from tools.retrieval.window import ScanWindow

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


def _record_lookup_keys(record: Record, ext: str) -> list[str]:
    """Every key under which ``record`` might already be stored.

    The exact ``(source, external_id)`` canonical key **plus** the full strong-
    identifier set (doi/pmid/pmcid/arxiv). Cross-source dedup within one scan run
    picks the canonical id from the first-seen source, so the *same* paper can
    reach the store on a later run under a different canonical id (e.g. OpenAlex
    stores ``doi:…`` while SemanticScholar stores ``semanticscholar:…``). Matching
    on the identifier set — not just the canonical id — is what collapses those.
    """
    return [ext, *_record_identifier_keys(
        record.doi, record.pmid, record.pmcid, record.arxiv
    )]


def _index_existing(candidates: list[tuple[Record, str]]) -> dict[str, ContentItem]:
    """Map every identifier key of already-stored papers to their row.

    Prefilters the store to rows that could match one of ``candidates`` (by
    canonical id or by any shared strong identifier), then indexes each fetched
    row under its ``external_id`` and its metadata-derived identifier keys.
    """
    ext_ids = [ext for _, ext in candidates]
    dois = {r.doi for r, _ in candidates if r.doi}
    pmids = {r.pmid for r, _ in candidates if r.pmid}
    pmcids = {r.pmcid for r, _ in candidates if r.pmcid}
    arxivs: set[str] = set()
    for r, _ in candidates:
        if r.arxiv:
            arxivs.add(r.arxiv.strip())
            arxivs.add(r.arxiv.strip().lower())

    query = Q(external_id__in=ext_ids)
    if dois:
        query |= Q(metadata__doi__in=list(dois))
    if pmids:
        query |= Q(metadata__pmid__in=list(pmids))
    if pmcids:
        query |= Q(metadata__pmcid__in=list(pmcids))
    if arxivs:
        query |= Q(metadata__arxiv__in=list(arxivs))

    index: dict[str, ContentItem] = {}
    for item in ContentItem.objects.filter(type=ContentItem.Type.PAPER).filter(query):
        if item.external_id:
            index.setdefault(item.external_id, item)
        for key in metadata_identifier_keys(item.metadata or {}):
            index.setdefault(key, item)
    return index


def _absorb_into_existing(item: ContentItem, record: Record) -> bool:
    """Fold a duplicate record's sources/identifiers into the stored row.

    Mirrors ``Deduplicator._merge`` at the persistence layer: unions the source
    list and back-fills any identifier/field the stored metadata is missing, so a
    row first seen from one source visibly records every source it later matched.
    Returns whether ``item.metadata`` changed (caller saves).
    """
    md = dict(item.metadata or {})
    changed = False

    have = set(md.get("sources") or [])
    want = set(record.sources) | {record.source}
    if not want <= have:
        md["sources"] = sorted(have | want)
        changed = True

    for attr in (
        "doi", "pmid", "pmcid", "arxiv", "abstract", "venue",
        "pdf_url", "year", "publication_date",
    ):
        value = getattr(record, attr, None)
        if value and not md.get(attr):
            md[attr] = value
            changed = True

    if changed:
        item.metadata = md
    return changed


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
    # Match on the full identifier set, not just the canonical id, so a paper
    # that reached the store earlier from a different source (under a different
    # canonical id) is recognized instead of inserted a second time.
    started = time.monotonic()
    candidates = [(record, _external_id(record)) for record in unique]
    existing_index = _index_existing(candidates)

    fresh: list[tuple[Record, str]] = []
    absorbed: dict = {}
    for record, ext in candidates:
        match = None
        for key in _record_lookup_keys(record, ext):
            match = existing_index.get(key)
            if match is not None:
                break
        if match is None:
            fresh.append((record, ext))
        elif _absorb_into_existing(match, record):
            absorbed[match.pk] = match
    if absorbed:
        ContentItem.objects.bulk_update(list(absorbed.values()), ["metadata"])
    summary.already_present = summary.unique - len(fresh)
    summary.new = len(fresh)
    summary.timings["against_store"] = round(time.monotonic() - started, 2)
    _emit(
        log,
        f"against store: {summary.new} new, {summary.already_present} already "
        f"present ({len(absorbed)} enriched) in {summary.timings['against_store']}s",
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
