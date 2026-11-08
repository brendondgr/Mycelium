"""Upsert open-collector grants/conferences into ``ContentItem``, and prune expired.

The collector's twin of Pivot-RP's own ``apps.scraper.pivot.ingest`` (plan
Phase 4), which this module replaces for the ``grants:<adapter>`` /
``conf:<adapter>`` sources :mod:`tools.retrieval.collect.mapping` produces — the
mechanics below are deliberately the same shape, minus everything that was
Pivot-specific: fellowships, the ``PivotItem`` dataclass, and the constraint
extraction pass, none of which this module ever touches. Pivot-RP itself was
deleted in plan Phase 6; fellowship ingest and constraint extraction now live
permanently in :mod:`tools.retrieval.fellowships.ingest`, not here.

**Runtime order is ingest -> extract (Phase 8) -> embed** (plan D10), and that
ordering is why this module's embedding step is a separate function rather
than folded into the upsert the way Pivot's was. Phase 8's verified
extraction — or, for a refused record, its truncated raw-text fallback — is
what :func:`~tools.retrieval.collect.extract.apply_to_metadata` writes to
``metadata["search_text"]``, directly against the stored ``ContentItem``. By
the time :func:`embed_pending` ever runs against a real record, extraction has
already settled what that record's embedding basis is; this module never
invents one. A record :func:`upsert_items` has written but extraction has not
yet reached simply carries no ``search_text`` key and is silently skipped by
:func:`embed_pending` until it does — that gap is intentional, not a bug, and
is exactly what keeps a raw 11,411-character NSF description from ever being
embedded directly (plan D9).

Three guarantees the daily job relies on, same as Pivot's:

* **Idempotent upsert** keyed on ``(source, external_id)`` — the same partial
  unique constraint Pivot used (``content_item_unique_source_external_id``).
  A record already present is updated, never re-inserted.
* **``first_seen`` is immutable** — written once and preserved on every later
  upsert (the "New" pin logic reads it).
* **A re-ingest of unchanged input writes nothing.** This is new relative to
  Pivot, which always wrote every touched row regardless of whether its
  content had actually changed. Two things force the change here: the
  ⚠️ in the plan — ``run_analytics.collect_discovery`` counts
  ``ContentItem.created_at`` on the run day, so a nightly that re-inserted
  would report a fake discovery spike, and an always-write upsert makes the
  *un*changed case indistinguishable from a real update in the summary this
  module returns. See ``upsert_items``' use of ``_without``.

**Extraction/embedding state always survives a re-scrape.** ``map_grant`` /
``map_conference`` are pure functions of the collector's own record and know
nothing about extraction or embeddings, so a freshly mapped item never carries
``search_text``, ``embedding_model``, or any of Phase 8's bookkeeping keys.
Wholesale-replacing ``metadata`` on every upsert — which is what keeping
Pivot's mechanics literally would do — would silently erase a paid-for
extraction verdict and force a needless re-embed on every single nightly
re-scrape of source data that has not moved. ``_DERIVED_KEYS`` is carried
forward from the existing row for exactly this reason; see ``upsert_items``.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from django.db.models import Q
from django.utils import timezone

from tools.retrieval.models import ContentItem

# An embedder maps a batch of texts to vectors, or ``None`` when unavailable
# (the ``embeddings`` extra is not installed). Same contract as Pivot's.
Embedder = Callable[[Sequence[str]], list[list[float]] | None]

Log = Callable[[str], None]


def _noop(_msg: str) -> None:
    pass


# --------------------------------------------------------------------------- #
# Metadata keys this module must never let ``upsert_items`` clobber
# --------------------------------------------------------------------------- #

#: Keys only ever written by a *later* stage than ingest: Phase 8's extraction
#: (``search_text`` and everything ``tools.retrieval.collect.extract
#: .apply_to_metadata`` writes) and this module's own :func:`embed_pending`
#: (``embedding_model``, ``search_text_hash``). ``map_grant`` / ``map_conference``
#: never produce any of these — they are pure mappers of the collector's own
#: record and have no notion of extraction or embeddings (see their module
#: docstring) — so any key found here in the *existing* row's metadata is
#: carried forward onto the freshly mapped one rather than dropped, exactly the
#: way ``first_seen`` is.
_DERIVED_KEYS: tuple[str, ...] = (
    "search_text",
    "search_text_source",
    "search_text_hash",
    "embedding_model",
    "extraction_status",
    "extraction_attempts",
    "extraction_page_hash",
    "extraction_refusal",
    "ai_summary",
    "ai_fields",
    "summary_source",
)

#: Metadata a *material* re-scrape change is judged on — the fields that change
#: what a reader could act on. A source page that gains a new event, or moves an
#: existing one's dates, changes one of these; a re-worded title or a moved URL
#: does not. See :func:`_material_change`.
_MATERIAL_KEYS: tuple[str, ...] = (
    "deadlines_structured",
    "due_dates",
    "deadline_date",
    "event_start",
    "event_end",
    "open",
)

#: Bookkeeping keys this module itself stamps on every upsert. Excluded from
#: the "did anything actually change" comparison in ``_content_unchanged`` —
#: ``last_seen`` in particular is a fresh timestamp on every call by
#: construction, so comparing it directly would mean *nothing* ever compares
#: equal and the idempotent-reingest guarantee above could never hold.
_BOOKKEEPING_KEYS: tuple[str, ...] = (
    "first_seen",
    "last_seen",
    "refreshed_at",
    "refresh_reason",
)


def _without(meta: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {k: v for k, v in meta.items() if k not in keys}


def _material_change(old: dict[str, Any], new: dict[str, Any]) -> str:
    """Which actionable field a re-scrape moved, or ``""`` for cosmetic drift.

    Conferences and grants are routinely extracted from pages that host many
    events at once, and when such a page is updated the old entries stay put —
    so "this record changed" is a weak signal and fires on a re-worded title
    every night. What the reader actually wants to hear about is a page that
    gained a deadline, moved one, or reopened: the reason to look at a listing
    again.

    Returns the first key that moved, so the stamped ``refresh_reason`` says
    *what* changed rather than only that something did. Order follows
    ``_MATERIAL_KEYS``, deadlines first, because that is the most informative
    answer when several moved together.
    """
    for key in _MATERIAL_KEYS:
        if key in old or key in new:
            if old.get(key) != new.get(key):
                return key
    return ""


# --------------------------------------------------------------------------- #
# The summary
# --------------------------------------------------------------------------- #


@dataclass
class IngestSummary:
    """What one ingest pass did.

    Shaped after Pivot-RP's own ``PivotIngestSummary`` so the analytics stage
    that reads it (``run_analytics``) keeps working, with one deliberate
    substitution: Pivot's ``constrained`` (how many fellowships had their
    eligibility prose read by the model) has no equivalent here — this module
    never touches fellowships, which have their own permanent ingest path at
    :mod:`tools.retrieval.fellowships.ingest` (and its own
    ``FellowshipIngestSummary.constrained``) — so it is replaced with
    ``refused``: how many of the records this pass touched currently carry a
    settled Phase 8 ``extraction_status == "refused"``. Purely observational
    (this module
    never runs extraction itself), but it is exactly the plan's "a refusal is
    a first-class outcome, counted and shown, never a silent drop" (§8)
    applied to the one place that already summarises every ingest.
    """

    seen: int = 0
    created: int = 0
    updated: int = 0
    embedded: int = 0
    pruned: int = 0
    skipped: int = 0
    refused: int = 0
    #: Of the updated rows, how many moved something a reader can act on — a
    #: deadline added, moved, or reopened — rather than drifting cosmetically.
    refreshed: int = 0
    by_type: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "seen": self.seen,
            "created": self.created,
            "updated": self.updated,
            "embedded": self.embedded,
            "pruned": self.pruned,
            "skipped": self.skipped,
            "refused": self.refused,
            "refreshed": self.refreshed,
            "by_type": dict(self.by_type),
        }


def _default_embedder() -> Embedder:
    from tools.retrieval.embeddings import embed_texts

    return embed_texts


def _today_iso(today: str | None) -> str:
    return today or timezone.now().date().isoformat()


def _search_text_hash(text: str) -> str:
    """A stable, cross-process, cross-machine digest of embedded text.

    Deliberately not Python's builtin ``hash()`` — string hashing is salted
    per-process (``PYTHONHASHSEED``) unless explicitly disabled, so the same
    text would hash differently between two runs and every record would look
    "changed" forever. ``sha256`` is stable by construction and cheap enough
    that hashing a search-text string on every embed sweep is noise next to
    the embedding call itself.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Upsert
# --------------------------------------------------------------------------- #


def upsert_items(
    items: Iterable[dict[str, Any] | None],
    *,
    today: str | None = None,
    log: Log | None = None,
) -> IngestSummary:
    """Upsert mapped grant/conference dicts, preserving ``first_seen`` and
    every key a later pipeline stage (extraction, embedding) has already
    written for that record.

    ``items`` is exactly what :func:`tools.retrieval.collect.mapping.map_grant` /
    ``map_conference`` produce — ``None`` is tolerated inline (``map_grant``
    returns it for a filtered ``overlay`` record) and counted as ``skipped``
    rather than requiring the caller to pre-filter, the same convenience
    Pivot's own ``ingest_pivot`` gave a raw record that ``build_pivot_item``
    rejected.

    Does **not** embed — see the module docstring on why that is a separate
    stage now — and does not run Phase 8 extraction, which is a distinct
    pipeline stage this module has no business invoking.
    """
    log = log or _noop
    today = _today_iso(today)
    summary = IngestSummary()
    now_iso = timezone.now().isoformat()
    touched: list[ContentItem] = []

    for item in items:
        if item is None:
            summary.skipped += 1
            continue
        summary.seen += 1
        summary.by_type[item["type"]] = summary.by_type.get(item["type"], 0) + 1
        meta: dict[str, Any] = dict(item["metadata"])

        existing = ContentItem.objects.filter(
            source=item["source"], external_id=item["external_id"]
        ).first()

        if existing is not None:
            old = existing.metadata or {}

            # Carry forward anything a later stage already settled for this
            # record — see ``_DERIVED_KEYS``. A freshly mapped item never
            # sets any of these itself, so ``setdefault`` only ever fires
            # when the existing row actually has one to protect.
            for key in _DERIVED_KEYS:
                if key in old:
                    meta.setdefault(key, old[key])

            # Same preservation rule Pivot's ingest carried for a
            # model-extracted ``constraints`` block: an expensive, stable,
            # LLM-sourced verdict is never displaced by a re-scrape's cheaper
            # pattern-only result. No grant/conference metadata sets
            # ``constraints`` today — that key is fellowship eligibility,
            # untouched by this module — so this is a no-op here, kept only
            # because the port instructions call for it explicitly and it
            # costs nothing to leave in place for whatever future metadata
            # follows the same "LLM verdict outranks a re-scrape" shape.
            prior_constraints = old.get("constraints") or {}
            if prior_constraints.get("source") == "llm" and (
                (meta.get("constraints") or {}).get("source") != "llm"
            ):
                meta["constraints"] = prior_constraints

            if old.get("extraction_status") == "refused":
                summary.refused += 1

            # ``type``/``source_url`` are mapper-derived too (a record's
            # canonical URL can move without any metadata field changing at
            # all), so both join the comparison alongside metadata — checking
            # metadata alone would silently skip persisting a moved URL.
            unchanged = (
                existing.type == item["type"]
                and existing.source_url == item["source_url"]
                and _without(meta, _BOOKKEEPING_KEYS)
                == _without(old, _BOOKKEEPING_KEYS)
            )
            if unchanged:
                # Nothing the collector re-scraped actually changed. Writing
                # anyway (Pivot always did) would make ``updated`` count every
                # unchanged nightly re-scrape as a real update, and defeats
                # the idempotency guarantee this module exists to add — see
                # the module docstring and the headline ingest test.
                continue

            meta["first_seen"] = old.get("first_seen") or now_iso  # immutable
            meta["last_seen"] = now_iso
            # A source page whose actionable content moved is worth re-surfacing;
            # one whose title was re-worded is not. Carry the previous stamp
            # forward when nothing material moved, so an "Updated" pin runs out
            # on its own clock rather than being refreshed by cosmetic drift.
            reason = _material_change(old, meta)
            if reason:
                meta["refreshed_at"] = now_iso
                meta["refresh_reason"] = reason
                summary.refreshed += 1
            else:
                for key in ("refreshed_at", "refresh_reason"):
                    if key in old:
                        meta[key] = old[key]
            existing.type = item["type"]
            existing.source_url = item["source_url"]
            existing.metadata = meta
            existing.save(update_fields=["type", "source_url", "metadata"])
            summary.updated += 1
            touched.append(existing)
        else:
            meta["first_seen"] = now_iso
            meta["last_seen"] = now_iso
            obj = ContentItem.objects.create(
                type=item["type"],
                source=item["source"],
                external_id=item["external_id"],
                source_url=item["source_url"],
                metadata=meta,
            )
            summary.created += 1
            touched.append(obj)

    _rebuild_deadline_projection(touched, today, log)

    log(
        f"upsert: {summary.created} new, {summary.updated} updated "
        f"({summary.refreshed} with a moved deadline), {summary.skipped} skipped"
    )
    return summary


def _rebuild_deadline_projection(
    items: list[ContentItem], today: str, log: Log
) -> None:
    """Rebuild the ``ContentDeadline`` projection for every created/updated row.

    Only genuinely touched rows — an unchanged re-scrape's metadata (and
    therefore its deadlines) is already correct in the projection from the
    ingest that first wrote it, so rebuilding again would be pure waste. This
    is a stricter, cheaper version of Pivot's equivalent, which rebuilt for
    every row an ingest pass saw whether or not anything had moved.

    Phase 5 rewrites what ``deadline_specs_for`` reads for a conference
    (``metadata["deadlines_structured"]`` instead of ``pivot.deadlines``); the
    call site here is unaffected by that change, which is why this function
    is safe to write now, ahead of Phase 5 landing.
    """
    from tools.retrieval.deadlines_projection import rebuild_deadlines_for

    opportunity_types = {ContentItem.Type.GRANT, ContentItem.Type.CONFERENCE}
    moved = 0
    for obj in items:
        if obj.type in opportunity_types:
            moved += len(rebuild_deadlines_for(obj, today))
    if moved:
        log(f"deadlines: {moved} due date(s) moved")


# --------------------------------------------------------------------------- #
# Prune
# --------------------------------------------------------------------------- #


def prune_expired(
    *,
    today: str | None = None,
    log: Log | None = None,
    stale_only: bool = False,
    dry_run: bool = False,
) -> int:
    """Delete grant/conference/fellowship items that are past, or dead and stale.

    Two independent rules, counted and logged separately because they answer
    different questions and one of them is much newer:

    1. **Expired** — ``prune_after`` is set and has passed. The original rule.
    2. **Stale and dateless** — a *conference* carrying no date at all (no
       deadline, no event date) that the collector has not re-seen for
       ``settings.OPPORTUNITY_STALE_DAYS``. Rule 1 can never reach these: an
       empty ``prune_after`` cannot be proven past, so before this they
       accumulated in the corpus permanently — 156 of 912 live conferences on
       2026-08-17, mostly journal listings and undated stubs. See
       :mod:`tools.retrieval.liveness` for why "dateless" is fatal for a
       conference and correct for a grant.

    ``stale_only`` runs rule 2 alone (the one-off purge of what has already
    accumulated); ``dry_run`` reports what would go without deleting anything.

    **Type-scoped, not source-scoped** (plan Phase 4, point 2 — the fix this
    function exists to make). Pivot's version filtered on a hard-coded
    ``OPPORTUNITY_SOURCES = (PIVOT_SOURCE, FELLOWSHIP_SOURCE)`` allow-list, so
    a record from any source id not in that tuple — every single
    ``grants:<adapter>`` / ``conf:<adapter>`` row this migration introduces —
    was silently invisible to expiry and would accumulate in the corpus
    forever, never freeing its place in the embedding/retrieval pool.
    Filtering on ``type__in`` instead means a new source can never be
    silently skipped again: the *type* vocabulary (grant/conference/
    fellowship) changes far less often than the *source* vocabulary does, and
    this function does not need to know about a source at all to prune it
    correctly.

    Fellowships are included in ``type__in`` even though this module never
    *upserts* them (that is :mod:`tools.retrieval.fellowships.ingest`'s job) —
    this is now the one ``prune_expired`` the plan converges the whole
    opportunity surface on, and a fellowship's ``prune_after`` means exactly
    the same thing a grant's does.

    Keeps the ORM ``.delete()`` (not a bulk queryset delete under the hood —
    Django's queryset ``.delete()`` still fires ``pre_delete`` per row) so
    reminders are marked stale, and keeps "unknown dates are kept" — an empty
    ``prune_after`` can never be proven past, so it is never pruned.
    """
    from tools.retrieval.liveness import OPPORTUNITY_TYPES, is_expired, is_stale

    log = log or _noop
    today = _today_iso(today)
    qs = ContentItem.objects.filter(type__in=sorted(OPPORTUNITY_TYPES)).only(
        "id", "type", "metadata"
    )
    # Zero-padded ISO throughout (``map_grant`` / ``map_conference`` both emit
    # ``date.isoformat()`` results) is what makes ``is_expired``'s plain string
    # compare correct: "2026-08-16" < "2026-10-01" holds character-by-character
    # only because both sides pad the month to two digits.
    expired_ids: list = []
    stale_ids: list = []
    for c in qs:
        if not stale_only and is_expired(c.type, c.metadata, today):
            expired_ids.append(c.id)
        elif is_stale(c.type, c.metadata, today):
            stale_ids.append(c.id)

    doomed = [*expired_ids, *stale_ids]
    if not doomed:
        log("prune: nothing expired")
        return 0

    if expired_ids:
        log(f"prune: {len(expired_ids)} item(s) past their last written date")
    if stale_ids:
        log(
            f"prune: {len(stale_ids)} dateless conference(s) unseen for over "
            f"{_stale_days()} days"
        )
    if dry_run:
        log(f"prune: dry run — {len(doomed)} item(s) left in place")
        return len(doomed)

    ContentItem.objects.filter(id__in=doomed).delete()
    log(f"prune: removed {len(doomed)} item(s)")
    return len(doomed)


def _stale_days() -> int:
    from tools.retrieval.liveness import stale_days

    return stale_days()


# --------------------------------------------------------------------------- #
# Embed
# --------------------------------------------------------------------------- #


def embed_pending(*, embedder: Embedder | None = None, log: Log | None = None) -> int:
    """Embed every grant/conference whose ``search_text`` is new or changed.

    The final stage of ``ingest -> extract -> embed`` (D10). Reads
    ``metadata["search_text"]`` exactly as Phase 8 leaves it — a verified
    extraction, or a refused record's truncated raw-text fallback — and never
    composes one itself; a record with no ``search_text`` key at all has not
    reached extraction yet and is silently left alone, not embedded from raw
    collector text (the entire premise of D9 is that raw text is not a
    comparable embedding basis).

    Re-embeds only when ``metadata["search_text_hash"]`` disagrees with the
    hash of the *current* ``search_text`` (or there is no vector yet at all),
    so a nightly run that changes nothing about a record's extracted text —
    only, say, its deadline — costs no embedding call. ``metadata
    ["embedding_model"]`` is recorded beside every vector this writes: plan
    D10 point 6 — Mycelium stores no embedding model beside a vector today,
    so a model change would leave the corpus silently in the old space with
    nothing to ever trigger a refit.

    Scoped to ``source`` starting ``grants:`` / ``conf:`` — the prefixes
    :mod:`tools.retrieval.collect.mapping` always writes — rather than just
    ``type in (grant, conference)``, so this function can never reach a
    still-live Pivot-sourced grant/conference row during the migration
    window and re-embed it under a different composition than Pivot's own
    ingest already gave it.
    """
    from django.conf import settings

    from tools.retrieval.embedding import DEFAULT_MODEL

    log = log or _noop
    embed_fn = embedder or _default_embedder()
    model_name = getattr(settings, "SCRAPER_EMBEDDING_MODEL", DEFAULT_MODEL)

    candidates = ContentItem.objects.filter(
        Q(source__startswith="grants:") | Q(source__startswith="conf:"),
        type__in=[ContentItem.Type.GRANT, ContentItem.Type.CONFERENCE],
    ).only("id", "metadata", "embedding")

    to_embed: list[tuple[ContentItem, str, str]] = []
    for obj in candidates:
        meta = obj.metadata or {}
        text = meta.get("search_text")
        if not text:
            continue
        digest = _search_text_hash(text)
        if obj.embedding is not None and meta.get("search_text_hash") == digest:
            continue
        to_embed.append((obj, text, digest))

    if not to_embed:
        log("embed: nothing pending")
        return 0

    vectors = embed_fn([text for _, text, _ in to_embed])
    if not vectors:
        log("embeddings unavailable — items stay without vectors")
        return 0

    embedded = 0
    for (obj, _text, digest), vector in zip(to_embed, vectors, strict=False):
        obj.embedding = vector
        meta = dict(obj.metadata or {})
        meta["search_text_hash"] = digest
        meta["embedding_model"] = model_name
        obj.metadata = meta
        obj.save(update_fields=["embedding", "metadata"])
        embedded += 1

    log(f"embed: {embedded} item(s) embedded")
    return embedded


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #


def ingest_collected(
    items: Iterable[dict[str, Any] | None],
    *,
    embed: bool = True,
    prune: bool = True,
    embedder: Embedder | None = None,
    today: str | None = None,
    log: Log | None = None,
) -> IngestSummary:
    """Upsert -> embed pending -> prune expired, one summary for the whole pass.

    The collector's analogue of ``ingest_pivot``: the one call a management
    command or the nightly run makes. Unlike ``ingest_pivot`` this does not
    take raw ``(area, record)`` pairs — dispatching a collector record to
    ``map_grant`` or ``map_conference`` needs the resolved
    :class:`~tools.retrieval.collect.conferences.record.ConferenceSeries` for a
    conference, which only the caller driving the collector run actually has,
    so that dispatch belongs to whichever later phase wires the runner in, not
    here. Callers pass already-mapped ``dict | None`` items, exactly what
    ``map_grant`` / ``map_conference`` return.

    ``embed`` here always means :func:`embed_pending`'s **global** sweep, not
    "embed only what this call's ``items`` touched" — a prior ingest's records
    may have only just cleared Phase 8 extraction between runs, and this is
    the one call site meant to catch all of them, not only this batch's.
    """
    log = log or _noop
    today = _today_iso(today)
    summary = upsert_items(items, today=today, log=log)
    if embed:
        summary.embedded = embed_pending(embedder=embedder, log=log)
    if prune:
        summary.pruned = prune_expired(today=today, log=log)
    return summary
