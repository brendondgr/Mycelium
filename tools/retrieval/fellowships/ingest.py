"""Upsert Illinois Fellowship Finder records into ``ContentItem`` (+embed).

Relocated from :mod:`apps.scraper.pivot.ingest` (plan Phase 6 — the deletion of
Pivot-RP). That module's ``ingest_pivot``/``upsert_pivot_items`` handled three
areas generically; fellowships were always the one area with nothing to do with
Pivot itself (D8), so this module keeps exactly that slice, under its own name.

Pruning is **not** duplicated here. Plan Phase 4 already converged expiry onto
one function — :func:`tools.retrieval.collect.ingest.prune_expired` — which is
type-scoped (``type__in=[GRANT, CONFERENCE, FELLOWSHIP]``), not source-scoped,
specifically so it covers every opportunity type including fellowships without
this module needing a second copy of the same delete-expired logic. Call that
function after this module's :func:`ingest_fellowships`, or independently on
its own schedule; both are safe to call any number of times.

Three guarantees the daily job relies on, same as Pivot's:

* **Idempotent upsert** keyed by ``(source="illinois-fellowship-finder",
  external_id)`` — a re-scrape updates in place, never duplicates.
* **``first_seen`` is immutable** — written once on first ingest and preserved on
  every later upsert, so a nightly refresh never resets a user's "New" items.
* **The ``ContentDeadline`` projection is rebuilt** after every upsert so the
  daily reminder tick always reads live deadlines. Unlike
  :mod:`tools.retrieval.collect.ingest`'s own rebuild hook (grants/conferences
  only — see its docstring), this module's hook covers ``FELLOWSHIP`` rows,
  because nothing else does.

Embedding reuses the shared fastembed model (:mod:`tools.retrieval.embeddings`), so
fellowship vectors and the profile query share a space with every other
opportunity type. Only new or changed documents are embedded.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from django.utils import timezone

from tools.retrieval.fellowships.records import (
    FELLOWSHIP_SOURCE,
    FellowshipItem,
    build_fellowship_item,
)
from tools.retrieval.models import ContentItem

# An embedder maps a batch of texts to vectors, or ``None`` when unavailable.
Embedder = Callable[[Sequence[str]], list[list[float]] | None]

Log = Callable[[str], None]


def _noop(_msg: str) -> None:
    pass


@dataclass
class FellowshipIngestSummary:
    """What one fellowship ingest pass did."""

    seen: int = 0
    created: int = 0
    updated: int = 0
    embedded: int = 0
    skipped: int = 0
    constrained: int = 0  # fellowships whose eligibility prose the model read

    def as_dict(self) -> dict:
        return {
            "seen": self.seen,
            "created": self.created,
            "updated": self.updated,
            "embedded": self.embedded,
            "skipped": self.skipped,
            "constrained": self.constrained,
        }


def _default_embedder() -> Embedder:
    from tools.retrieval.embeddings import embed_texts

    return embed_texts


def _today_iso(today: str | None) -> str:
    return today or timezone.now().date().isoformat()


def upsert_fellowship_items(
    items: Iterable[FellowshipItem],
    *,
    embed: bool = True,
    embedder: Embedder | None = None,
    today: str | None = None,
    log: Log | None = None,
) -> FellowshipIngestSummary:
    """Upsert :class:`FellowshipItem`\\ s, preserving ``first_seen``; embed new/changed.

    After the upsert, the ``ContentDeadline`` projection is rebuilt for every
    upserted fellowship so the daily reminder tick always reads live deadlines,
    and a moved date leaves a ``changed_at`` signal.
    """
    log = log or _noop
    summary = FellowshipIngestSummary()
    now_iso = timezone.now().isoformat()
    to_embed: list[tuple[ContentItem, str]] = []
    touched: list[ContentItem] = []

    for item in items:
        summary.seen += 1
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
        f"fellowships upsert: {summary.created} new, {summary.updated} updated, "
        f"{summary.embedded} embedded"
    )
    return summary


def _rebuild_deadline_projection(
    items: list[ContentItem], today: str | None, log: Log
) -> None:
    """Rebuild the ``ContentDeadline`` rows for the upserted fellowships (R0).

    Import is lazy so a bare ``scraper`` import never pulls the content
    projection at module load.
    """
    from tools.retrieval.deadlines_projection import rebuild_deadlines_for

    today = _today_iso(today)
    moved = 0
    for obj in items:
        if obj.type == ContentItem.Type.FELLOWSHIP:
            moved += len(rebuild_deadlines_for(obj, today))
    if moved:
        log(f"deadlines: {moved} due date(s) moved")


def ingest_fellowships(
    records: Iterable[dict],
    *,
    embed: bool = True,
    embedder: Embedder | None = None,
    today: str | None = None,
    log: Log | None = None,
) -> FellowshipIngestSummary:
    """Ingest raw Illinois Fellowship Finder records: build -> upsert -> embed.

    Pruning is deliberately not this function's job — call
    :func:`tools.retrieval.collect.ingest.prune_expired` after (it is type-scoped
    and already covers ``FELLOWSHIP`` rows; see the module docstring).
    """
    log = log or _noop
    today = _today_iso(today)
    items: list[FellowshipItem] = []
    skipped = 0
    for rec in records:
        item = build_fellowship_item(rec, today=today)
        if item is None:
            skipped += 1
            continue
        items.append(item)

    summary = upsert_fellowship_items(
        items, embed=embed, embedder=embedder, today=today, log=log
    )
    summary.skipped += skipped
    summary.constrained = extract_fellowship_constraints(log=log)
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

    from tools.retrieval.eligibility.constraints import extract_by_model, is_resolved

    log = log or _noop
    if not getattr(settings, "FELLOWSHIP_CONSTRAINT_EXTRACTION", True):
        return 0

    pending: list[ContentItem] = []
    units: list[tuple[str, str]] = []
    # This filters on both type AND source (rather than type alone) so the
    # queryset stays correct even if a non-Illinois fellowship source is ever
    # added — see the Phase 2 bug this guarded against (a stale
    # ``source=PIVOT_SOURCE`` filter left this pass permanently no-op).
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
