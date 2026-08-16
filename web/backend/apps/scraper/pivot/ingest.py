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

from .records import FELLOWSHIP_SOURCE, PIVOT_SOURCE, PivotItem, build_pivot_item

# An embedder maps a batch of texts to vectors, or ``None`` when unavailable.
Embedder = Callable[[Sequence[str]], list[list[float]] | None]

# FELLOWSHIP_SOURCE is defined in .records (alongside PIVOT_SOURCE, which this
# module already imports from there) rather than here, so the two source ids
# have exactly one definition each instead of two that can silently drift apart.

# All sources this ingest layer manages. Upsert keys on (source, external_id);
# prune covers all sources in this set.
OPPORTUNITY_SOURCES = (PIVOT_SOURCE, FELLOWSHIP_SOURCE)

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
    constrained: int = 0   # fellowships whose eligibility prose the model read
    by_type: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "seen": self.seen,
            "created": self.created,
            "updated": self.updated,
            "embedded": self.embedded,
            "pruned": self.pruned,
            "skipped": self.skipped,
            "constrained": self.constrained,
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
    today: str | None = None,
    log: Log | None = None,
) -> PivotIngestSummary:
    """Upsert :class:`PivotItem`s, preserving ``first_seen``; embed new/changed.

    After the upsert (and before any caller prunes), the ``ContentDeadline``
    projection is rebuilt for every upserted opportunity so the daily reminder tick
    always reads live deadlines, and a moved date leaves a ``changed_at`` signal.
    """
    log = log or _noop
    summary = PivotIngestSummary()
    now_iso = timezone.now().isoformat()
    to_embed: list[tuple[ContentItem, str]] = []
    touched: list[ContentItem] = []

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
            # A model-extracted constraints block is expensive and stable; the
            # freshly-built record only ever carries the free pattern result, so
            # keep the richer one rather than paying for the extraction again on
            # every re-scrape.
            prior_constraints = old.get("constraints") or {}
            if prior_constraints.get("source") == "llm" and (
                (meta.get("constraints") or {}).get("source") != "llm"
            ):
                meta["constraints"] = prior_constraints
            text_changed = old.get("search_text") != item.text
            existing.type = item.type
            existing.source_url = item.source_url
            existing.metadata = meta
            existing.save(update_fields=["type", "source_url", "metadata"])
            summary.updated += 1
            touched.append(existing)
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
            touched.append(obj)
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

    _rebuild_deadline_projection(touched, today, log)

    log(
        f"upsert: {summary.created} new, {summary.updated} updated, "
        f"{summary.embedded} embedded"
    )
    return summary


def _rebuild_deadline_projection(
    items: list[ContentItem], today: str | None, log: Log
) -> None:
    """Rebuild the ``ContentDeadline`` rows for the upserted opportunities (R0).

    Papers carry no deadlines and are skipped. Import is lazy so a bare
    ``scraper`` import never pulls the content projection at module load.
    """
    from apps.content.deadlines_projection import rebuild_deadlines_for

    today = _today_iso(today)
    opportunity_types = {
        ContentItem.Type.GRANT,
        ContentItem.Type.CONFERENCE,
        ContentItem.Type.FELLOWSHIP,
    }
    moved = 0
    for obj in items:
        if obj.type in opportunity_types:
            moved += len(rebuild_deadlines_for(obj, today))
    if moved:
        log(f"deadlines: {moved} due date(s) moved")


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

    summary = upsert_pivot_items(
        items, embed=embed, embedder=embedder, today=today, log=log
    )
    summary.skipped += skipped
    summary.constrained = extract_fellowship_constraints(log=log)
    if prune:
        summary.pruned = prune_expired(today=today, log=log)
    return summary


#: How many unresolved fellowships one ingest sends to the model. A backstop, not
#: a target: the corpus is ~950 records and the pattern layer resolves most of the
#: ones that state a constraint at all, so a normal run sends far fewer.
CONSTRAINT_EXTRACTION_BATCH = 40


def extract_fellowship_constraints(
    *,
    complete: Callable[[str], str | None] | None = None,
    limit: int = CONSTRAINT_EXTRACTION_BATCH,
    log: Log | None = None,
) -> int:
    """Fill in the eligibility constraints the patterns could not read.

    Runs over stored fellowships whose prose is non-empty and whose constraints
    block is still unresolved, once per record: a record the model has answered
    for carries ``source == "llm"`` and is never revisited (the upsert above keeps
    that block across re-scrapes). Returns how many records gained a constraint.

    Best-effort by contract — the whole ingest must not fail because an extraction
    pass had a bad day, and the pattern result already stands on its own.
    """
    from django.conf import settings

    from apps.scraper.eligibility.constraints import extract_by_model, is_resolved

    log = log or _noop
    if not getattr(settings, "FELLOWSHIP_CONSTRAINT_EXTRACTION", True):
        return 0

    pending: list[ContentItem] = []
    units: list[tuple[str, str]] = []
    # Bug fix (Phase 2): this used to filter source=PIVOT_SOURCE, but fellowships
    # are ingested under FELLOWSHIP_SOURCE ("illinois-fellowship-finder"), never
    # "pivot" — so the queryset was always empty and this extraction pass had
    # never run on a single real fellowship. type=FELLOWSHIP alone would already
    # be unambiguous (only the Illinois adapter produces that type today), but
    # the explicit source keeps this query correct even if that stops being true.
    for item in ContentItem.objects.filter(
        type=ContentItem.Type.FELLOWSHIP, source=FELLOWSHIP_SOURCE
    ).iterator():
        meta = item.metadata or {}
        if is_resolved(meta.get("constraints") or {}):
            continue
        eligibility = meta.get("eligibility") or []
        if not isinstance(eligibility, list):
            eligibility = [str(eligibility)]
        text = " ".join([*eligibility, str(meta.get("note") or "")])
        text = " ".join(text.split())
        if not text:
            continue
        pending.append(item)
        units.append((str(meta.get("title") or "Untitled"), text))
        if len(pending) >= limit:
            break

    if not units:
        return 0
    try:
        found = extract_by_model(units, complete=complete)
    except Exception:  # pragma: no cover - defensive; extraction is optional
        log("fellowship constraint extraction failed; patterns only")
        return 0
    if not found:
        return 0

    changed: list[ContentItem] = []
    for index, block in found.items():
        item = pending[index]
        meta = dict(item.metadata or {})
        meta["constraints"] = block
        item.metadata = meta
        changed.append(item)
    if changed:
        ContentItem.objects.bulk_update(changed, ["metadata"], batch_size=100)
    log(f"constraints: read eligibility prose for {len(changed)} fellowships")
    return len(changed)
