"""Upsert Pivot grants/conferences into ``ContentItem`` (+embed) and prune expired.

The opportunity twin of :func:`apps.scraper.ingest.scan`: it turns normalized Pivot
records into ``ContentItem`` rows the ``content`` app matches per user. Three
guarantees the daily job relies on:

* **Idempotent upsert** keyed by ``(source="pivot", external_id)`` — a re-scrape
  updates in place, never duplicates.
* **``first_seen`` is immutable** — written once on first ingest and preserved on
  every later upsert, so a nightly refresh never resets a user's "New" items
  (the pin logic reads ``first_seen``).
* **Prune of expired items** — grants past their application deadline and
  conferences past their event date are deleted, freeing the embedding/retrieval
  pool. A user's *saved* deadline survives because ``SavedOpportunity.content`` is
  ``SET_NULL`` with a snapshot.

Embedding reuses the shared fastembed model (:mod:`apps.content.embeddings`), so
Pivot vectors and the profile query share a space. Only new or changed documents
are embedded.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

from django.utils import timezone

from apps.content.models import ContentItem

from .records import PIVOT_SOURCE, PivotItem, build_pivot_item

# An embedder maps a batch of texts to vectors, or ``None`` when unavailable.
Embedder = Callable[[Sequence[str]], list[list[float]] | None]

# All sources this ingest layer manages. Upsert keys on (source, external_id);
# prune covers all sources in this set.
OPPORTUNITY_SOURCES = (PIVOT_SOURCE, "illinois-fellowship-finder")

Log = Callable[[str], None]


def _noop(_msg: str) -> None:
    pass


@dataclass
class PivotIngestSummary:
    """What one ingest pass did."""

    seen: int = 0
    created: int = 0
    updated: int = 0
    embedded: int = 0
    pruned: int = 0
    skipped: int = 0
    by_type: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "seen": self.seen,
            "created": self.created,
            "updated": self.updated,
            "embedded": self.embedded,
            "pruned": self.pruned,
            "skipped": self.skipped,
            "by_type": dict(self.by_type),
        }


def _default_embedder() -> Embedder:
    from apps.content.embeddings import embed_texts

    return embed_texts


def _today_iso(today: str | None) -> str:
    return today or timezone.now().date().isoformat()


def upsert_pivot_items(
    items: Iterable[PivotItem],
    *,
    embed: bool = True,
    embedder: Embedder | None = None,
    log: Log | None = None,
) -> PivotIngestSummary:
    """Upsert :class:`PivotItem`s, preserving ``first_seen``; embed new/changed."""
    log = log or _noop
    summary = PivotIngestSummary()
    now_iso = timezone.now().isoformat()
    to_embed: list[tuple[ContentItem, str]] = []

    for item in items:
        summary.seen += 1
        summary.by_type[item.type] = summary.by_type.get(item.type, 0) + 1
        meta = dict(item.metadata)
        meta["search_text"] = item.text

        existing = ContentItem.objects.filter(
            source=item.source, external_id=item.external_id
        ).first()
        if existing is not None:
            old = existing.metadata or {}
            meta["first_seen"] = old.get("first_seen") or now_iso  # immutable
            meta["last_seen"] = now_iso
            text_changed = old.get("search_text") != item.text
            existing.type = item.type
            existing.source_url = item.source_url
            existing.metadata = meta
            existing.save(update_fields=["type", "source_url", "metadata"])
            summary.updated += 1
            if embed and (text_changed or existing.embedding is None):
                to_embed.append((existing, item.text))
        else:
            meta["first_seen"] = now_iso
            meta["last_seen"] = now_iso
            obj = ContentItem.objects.create(
                type=item.type,
                source=item.source,
                external_id=item.external_id,
                source_url=item.source_url,
                metadata=meta,
            )
            summary.created += 1
            if embed:
                to_embed.append((obj, item.text))

    if embed and to_embed:
        embed_fn = embedder or _default_embedder()
        vectors = embed_fn([text for _, text in to_embed])
        if vectors:
            for (obj, _text), vector in zip(to_embed, vectors, strict=False):
                obj.embedding = vector
                obj.save(update_fields=["embedding"])
                summary.embedded += 1
        else:
            log("embeddings unavailable — items stored without vectors")

    log(
        f"upsert: {summary.created} new, {summary.updated} updated, "
        f"{summary.embedded} embedded"
    )
    return summary


def prune_expired(*, today: str | None = None, log: Log | None = None) -> int:
    """Delete Pivot grants/conferences/fellowships whose actionable date has passed.

    Grants expire at their application deadline; conferences at their event date;
    fellowships at their ``prune_after`` (set only for "true" hard deadlines —
    rolling/anticipated/continuous entries are never pruned).
    Unknown dates are kept (can't prove they're past) — the same rule as
    :func:`apps.scraper.pivot.status.is_visible`.
    """
    log = log or _noop
    today = _today_iso(today)
    qs = ContentItem.objects.filter(
        source__in=OPPORTUNITY_SOURCES,
        type__in=[
            ContentItem.Type.GRANT,
            ContentItem.Type.CONFERENCE,
            ContentItem.Type.FELLOWSHIP,
        ],
    ).only("id", "metadata")
    expired_ids = [
        c.id
        for c in qs
        if (pa := (c.metadata or {}).get("prune_after")) and pa < today
    ]
    if not expired_ids:
        log("prune: nothing expired")
        return 0
    ContentItem.objects.filter(id__in=expired_ids).delete()
    log(f"prune: removed {len(expired_ids)} expired item(s)")
    return len(expired_ids)


def ingest_pivot(
    records_by_area: Iterable[tuple[str, dict]],
    *,
    embed: bool = True,
    prune: bool = True,
    embedder: Embedder | None = None,
    today: str | None = None,
    log: Log | None = None,
) -> PivotIngestSummary:
    """Ingest ``(area, raw_record)`` pairs: build → upsert → embed → prune.

    ``area`` is the tool's plural label ("grants" / "conferences" / "fellowships").
    """
    log = log or _noop
    today = _today_iso(today)
    items: list[PivotItem] = []
    skipped = 0
    for area, rec in records_by_area:
        item = build_pivot_item(area, rec, today=today)
        if item is None:
            skipped += 1
            continue
        items.append(item)

    summary = upsert_pivot_items(items, embed=embed, embedder=embedder, log=log)
    summary.skipped += skipped
    if prune:
        summary.pruned = prune_expired(today=today, log=log)
    return summary
