"""Query-first search over the content corpus.

This is the digest retrieval pipeline run **query-first** instead of
**profile-first**: the same Postgres store, the same shared BGE embedder, and the
same Reciprocal-Rank-Fusion idea — but driven by a user's search box instead of
their interest profile. It is a **separate module** from the daily pipeline on
purpose:

- Unlike the digest, search **never abstains**. It always returns the top-k and
  only flags low confidence as a UI cue (:data:`SearchResult.confidence`), so the
  digest's abstention floor must never leak onto this path.
- The digest's fusion (:mod:`apps.content.fusion`) stays untouched; this module
  has its own rank-only RRF (:func:`rrf_fuse`).

Channels (added across phases, fused by RRF into one ranked candidate pool):

- **lexical** — Postgres full-text search over ``ContentItem.search_vector``
  (weighted title/body/aux), ranked by ``ts_rank_cd`` (Phase 1).
- **semantic** — pgvector cosine ANN over the shared 384-dim embedding (Phase 2).
- **fuzzy** — ``pg_trgm`` word similarity on the title (Phase 3), for typos.

Everything degrades gracefully: no embedder ⇒ lexical (+ fuzzy) carry the query;
an empty/all-whitespace query ⇒ an empty result, never an error. The whole path
is PostgreSQL-only (full-text search + pgvector); on other backends the lexical
filter simply matches nothing.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

from django.conf import settings
from django.contrib.postgres.search import (
    SearchQuery,
    SearchRank,
    TrigramWordSimilarity,
)
from django.db.models import Count, F, QuerySet, TextField, Value
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Coalesce
from pgvector.django import CosineDistance

from .models import ContentItem
from .retrieval import _similarity

#: RRF dampening constant — 60 is the original-paper default (Cormack et al.).
DEFAULT_RRF_K = 60

#: The sort modes the endpoint accepts. ``deadline`` lands in Phase 3; until then
#: it is treated as ``relevance`` (validated/normalized by :func:`clean_sort`).
SORTS = ("relevance", "date", "deadline")


#: Per-type facet field: the one clean scalar ``metadata`` key each content type
#: carries that makes a good, index-cheap filter. Shown contextually — only when
#: that type is the sole selected ``type`` (see :func:`run_search`). The filter
#: value and the facet value are the same ``->>`` text, so a clicked chip always
#: round-trips back to an exact match.
TYPE_FACET_FIELD: dict[str, str] = {
    "paper": "year",
    "grant": "sponsor",
    "fellowship": "award_class",
    "conference": "country",
}

#: How many rows a facet lists (top-N by count). Bounds noisy high-cardinality
#: fields (sponsor/country) without hiding the useful head of the distribution.
FACET_LIMIT = 12


@dataclass(frozen=True)
class SearchFilters:
    """The corpus-scoping filters shared by every channel.

    ``types`` empty means "all content types". ``date_from``/``date_to`` filter on
    ``created_at`` (ingest time) — the one timestamp every type reliably carries.
    The remaining tuples are the per-type metadata facets (:data:`TYPE_FACET_FIELD`):
    each filters its ``metadata`` key as text, and — since only that type carries
    the key — naturally scopes to that type.
    """

    types: tuple[str, ...] = ()
    years: tuple[str, ...] = ()
    sponsors: tuple[str, ...] = ()
    award_classes: tuple[str, ...] = ()
    countries: tuple[str, ...] = ()
    date_from: date | None = None
    date_to: date | None = None


@dataclass
class SearchResult:
    """One page of a search, plus the facets and paging cursor around it."""

    query: str
    normalized: str
    sort: str
    count: int  # candidates in the fused pool after filtering
    pool_truncated: bool  # a channel hit the pool cap (more may exist beyond it)
    confidence: str  # "ok" | "low" — a display cue, never a gate (Phase 2)
    facets: dict
    items: list[ContentItem]  # this page, each tagged with _search_* transients
    limit: int
    offset: int
    next_offset: int | None = None
    matched_on: dict = field(default_factory=dict)  # id -> [channel names]


# --------------------------------------------------------------------------- #
# Query normalization + filter application
# --------------------------------------------------------------------------- #


def normalize_query(query: str | None) -> str:
    """Lowercase, trim, and collapse whitespace — the FTS input and cache key.

    ``to_tsvector`` already lowercases, but folding here also normalizes the
    Redis cache key (Phase 3) so ``"Protein  Folding"`` and ``"protein folding"``
    share one cached embedding.
    """
    return " ".join((query or "").split()).casefold()


def clean_sort(sort: str | None) -> str:
    """Coerce an incoming sort to a supported value (default ``relevance``)."""
    value = (sort or "").strip().lower()
    return value if value in SORTS else "relevance"


def clamp_limit(limit: int | None) -> int:
    """Bound the page size to ``[1, SEARCH_MAX_PAGE_SIZE]``."""
    default = getattr(settings, "SEARCH_PAGE_SIZE", 20)
    ceiling = getattr(settings, "SEARCH_MAX_PAGE_SIZE", 50)
    try:
        value = int(limit) if limit is not None else default
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, ceiling))


#: Per-type metadata filter: which :class:`SearchFilters` tuple feeds which
#: ``metadata`` key. Selecting a value equals its ``->>`` text (see
#: :func:`_metadata_text_expr`), so the facet the user clicks filters exactly.
_METADATA_FILTERS: tuple[tuple[str, str], ...] = (
    ("years", "year"),
    ("sponsors", "sponsor"),
    ("award_classes", "award_class"),
    ("countries", "country"),
)


def _metadata_text_expr(key: str):
    """The text form of a ``metadata`` key (``metadata->>'key'``), '' when absent.

    Used identically for filtering and faceting so a facet's value round-trips to
    an exact filter match regardless of the JSON value's underlying type (e.g. a
    numeric ``year`` still compares as the string the facet emitted).
    """
    return Coalesce(
        KeyTextTransform(key, "metadata"), Value(""), output_field=TextField()
    )


def _apply_filters(
    qs: QuerySet,
    filters: SearchFilters,
    *,
    include_type: bool,
    include_metadata: bool = True,
) -> QuerySet:
    """Apply date (always), type (optional), and per-type metadata (optional).

    ``include_metadata=False`` drops the per-type facet filters — used when
    computing a facet's own counts, which must ignore that facet's selection so
    multi-select stays legible.
    """
    if filters.date_from is not None:
        qs = qs.filter(created_at__date__gte=filters.date_from)
    if filters.date_to is not None:
        qs = qs.filter(created_at__date__lte=filters.date_to)
    if include_type and filters.types:
        qs = qs.filter(type__in=list(filters.types))
    if include_metadata:
        for attr, key in _METADATA_FILTERS:
            values = getattr(filters, attr)
            if values:
                alias = f"_f_{key}"
                qs = qs.annotate(**{alias: _metadata_text_expr(key)}).filter(
                    **{f"{alias}__in": list(values)}
                )
    return qs


# --------------------------------------------------------------------------- #
# Channels
# --------------------------------------------------------------------------- #


def _search_query(q: str) -> SearchQuery:
    """A ``websearch``-parsed English tsquery (honors quotes / OR / ``-term``)."""
    return SearchQuery(q, search_type="websearch", config="english")


def _lexical(base: QuerySet, q: str, *, limit: int) -> list[ContentItem]:
    """The lexical channel: FTS matches ranked by ``ts_rank_cd``, best first.

    ``ts_rank_cd`` rewards proximity and weight (title = A), so an exact title
    match ranks above a body mention — the property the relevance path relies on.
    """
    query = _search_query(q)
    rows = (
        base.filter(search_vector=query)
        .annotate(lex_rank=SearchRank(F("search_vector"), query))
        .order_by("-lex_rank", "id")[:limit]
    )
    return list(rows)


def _semantic(
    base: QuerySet, query_vector: Sequence[float] | None, *, limit: int
) -> tuple[list[ContentItem], float | None]:
    """The semantic channel: pgvector cosine ANN, nearest first.

    Reuses the same cosine-distance retrieval as the digest (the shared BGE
    space). Returns the ordered hits and the top cosine *similarity* (for the
    low-confidence cue). ``None``/empty query vector (no embedder) ⇒ no channel.
    """
    if query_vector is None or len(query_vector) == 0:
        return [], None
    rows = (
        base.filter(embedding__isnull=False)
        .annotate(distance=CosineDistance("embedding", query_vector))
        .order_by("distance")[:limit]
    )
    items = list(rows)
    if not items:
        return [], None
    top_cosine = _similarity(items[0].distance)
    return items, top_cosine


def _title_expr():
    """The title text expression (``title`` then ``name``), matched by the index.

    Mirrors the ``COALESCE(metadata->>'title', metadata->>'name', '')`` GIN
    trigram index (migration 0005) so the ``%>`` word-similarity prefilter can use
    the index instead of scanning the corpus.
    """
    return Coalesce(
        KeyTextTransform("title", "metadata"),
        KeyTextTransform("name", "metadata"),
        Value(""),
        output_field=TextField(),
    )


def _fuzzy(base: QuerySet, q: str, *, limit: int) -> list[ContentItem]:
    """The fuzzy channel: trigram word-similarity on the title, best first.

    Recovers a title query with a typo. The ``__trigram_word_similar`` lookup is
    the index-backed ``%>`` prefilter (fast); the annotated similarity then orders
    the survivors. Empty when ``pg_trgm`` is unavailable — the channel just drops.
    """
    rows = (
        base.annotate(title_text=_title_expr())
        .filter(title_text__trigram_word_similar=q)
        .annotate(tw_sim=TrigramWordSimilarity(q, "title_text"))
        .order_by("-tw_sim", "id")[:limit]
    )
    return list(rows)


def _channels(
    base: QuerySet, q: str, *, pool: int, query_vector: Sequence[float] | None
) -> tuple[dict[str, list[str]], dict[str, ContentItem], float | None]:
    """Run every available channel; return their rankings + a unified item map.

    Returns ``(channels, items_by_id, top_cosine)`` where ``channels`` maps a
    channel name to its ordered list of content ids (best first), ``items_by_id``
    resolves any surfaced id back to its :class:`ContentItem`, and ``top_cosine``
    is the best semantic similarity seen (``None`` when the semantic channel did
    not run) for the low-confidence cue. The fusion downstream is
    channel-agnostic, so every channel is just one more ordered id list.
    """
    items_by_id: dict[str, ContentItem] = {}
    channels: dict[str, list[str]] = {}

    def add(name: str, items: list[ContentItem]) -> None:
        if not items:
            return
        channels[name] = [str(item.id) for item in items]
        for item in items:
            items_by_id.setdefault(str(item.id), item)

    add("lexical", _lexical(base, q, limit=pool))

    semantic, top_cosine = _semantic(base, query_vector, limit=pool)
    add("semantic", semantic)

    if getattr(settings, "SEARCH_FUZZY_ENABLED", True):
        fuzzy_pool = min(pool, getattr(settings, "SEARCH_FUZZY_POOL", 200))
        add("fuzzy", _fuzzy(base, q, limit=fuzzy_pool))

    return channels, items_by_id, top_cosine


# --------------------------------------------------------------------------- #
# Fusion (rank-only RRF — the search path's own, separate from the digest's)
# --------------------------------------------------------------------------- #


def rrf_fuse(
    channels: dict[str, list[str]], *, k: int = DEFAULT_RRF_K
) -> dict[str, float]:
    """Reciprocal Rank Fusion over each channel's ordered id list.

    RRF combines **rank positions only** — the raw ts_rank/cosine/trigram
    magnitudes are deliberately discarded, so no single channel's scale can
    dominate (the "normalize before fusing" invariant, here achieved by ranking).
    A candidate's fused score is ``Σ 1/(k + rank)`` over the channels that
    surfaced it, so matching several channels beats matching one.
    """
    scores: dict[str, float] = {}
    for ids in channels.values():
        for rank, cid in enumerate(ids, start=1):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
    return scores


def _matched_on(channels: dict[str, list[str]]) -> dict[str, list[str]]:
    """Map each surfaced id to the channels that matched it (for the UI badge)."""
    matched: dict[str, list[str]] = {}
    for name, ids in channels.items():
        for cid in ids:
            matched.setdefault(cid, []).append(name)
    return matched


def _deadline_of(item: ContentItem) -> date | None:
    """A best-effort deadline date from whatever key the item's type carries.

    Grants snapshot ``deadline_date``; fellowships nest ``deadline.date``; papers
    have none. Unparseable/absent ⇒ ``None`` (sorted last by :func:`_order`).
    """
    meta = item.metadata or {}
    raw = meta.get("deadline_date")
    if not raw:
        nested = meta.get("deadline")
        if isinstance(nested, dict):
            raw = nested.get("date")
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


def _order(
    fused: dict[str, float], items_by_id: dict[str, ContentItem], sort: str
) -> list[str]:
    """Order the fused candidate ids by the requested sort mode (deterministic).

    ``relevance`` (default) sorts by fused score, breaking ties by recency then
    id; ``date`` sorts by ``created_at`` (newest first); ``deadline`` sorts by the
    soonest deadline with items that have none placed last (relevance breaks ties).
    """
    ids = sorted(fused.keys())  # stable, deterministic base order
    if sort == "date":
        ids.sort(key=lambda c: items_by_id[c].created_at, reverse=True)
        return ids
    if sort == "deadline":
        ids.sort(
            key=lambda c: (
                _deadline_of(items_by_id[c]) is None,  # nulls last
                _deadline_of(items_by_id[c]) or date.max,  # soonest first
                -fused[c],  # then most relevant
            )
        )
        return ids
    ids.sort(
        key=lambda c: (fused[c], items_by_id[c].created_at),
        reverse=True,
    )
    return ids


# --------------------------------------------------------------------------- #
# Facets
# --------------------------------------------------------------------------- #


def _facet_counts(base: QuerySet, field_name: str, q: str) -> list[dict]:
    """Count lexical matches grouped by a column, most-common first.

    Facets are computed from the lexical match set only (one fast aggregate per
    facet) — a documented approximation; the semantic/fuzzy tails are not counted.
    """
    query = _search_query(q)
    rows = (
        base.filter(search_vector=query)
        .values(field_name)
        .annotate(n=Count("id"))
        .order_by("-n", field_name)
    )
    return [{"value": row[field_name], "count": row["n"]} for row in rows]


def _metadata_facet_counts(
    base: QuerySet, key: str, q: str, *, limit: int = FACET_LIMIT
) -> list[dict]:
    """Count lexical matches grouped by a ``metadata`` text key, top-N by count.

    The per-type facet counterpart of :func:`_facet_counts`: groups by
    ``metadata->>key`` (the same expression the filter uses), drops blanks, and
    caps to ``limit`` so a high-cardinality field (sponsor/country) shows only its
    useful head. Computed over the lexical match set, like every other facet.
    """
    query = _search_query(q)
    rows = (
        base.filter(search_vector=query)
        .annotate(_facet=_metadata_text_expr(key))
        .exclude(_facet="")
        .values("_facet")
        .annotate(n=Count("id"))
        .order_by("-n", "_facet")[:limit]
    )
    return [{"value": row["_facet"], "count": row["n"]} for row in rows]


def _empty_result(query: str, sort: str, limit: int, offset: int) -> SearchResult:
    return SearchResult(
        query=query,
        normalized="",
        sort=sort,
        count=0,
        pool_truncated=False,
        confidence="ok",
        facets={"type": []},
        items=[],
        limit=limit,
        offset=offset,
        next_offset=None,
    )


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def run_search(
    query: str,
    *,
    filters: SearchFilters | None = None,
    sort: str = "relevance",
    limit: int | None = None,
    offset: int = 0,
    pool: int | None = None,
    query_vector: Sequence[float] | None = None,
) -> SearchResult:
    """Search the content corpus, query-first, and return one page of results.

    ``filters`` scopes the corpus (type/source/date); ``sort`` picks the ordering;
    ``limit``/``offset`` page within the bounded relevance pool (``pool``, default
    :data:`settings.SEARCH_CANDIDATE_POOL`). ``query_vector`` is injected by the
    view (Phase 2) as the cached query embedding so this stays free of the
    embedder and Redis, keeping it unit-testable. Never abstains: an in-corpus
    query always returns its best matches.
    """
    filters = filters or SearchFilters()
    sort = clean_sort(sort)
    limit = clamp_limit(limit)
    offset = max(0, int(offset or 0))
    pool = pool or getattr(settings, "SEARCH_CANDIDATE_POOL", 500)

    normalized = normalize_query(query)
    if not normalized:
        return _empty_result(query, sort, limit, offset)

    base_no_type = _apply_filters(
        ContentItem.objects.all(), filters, include_type=False
    )
    base_typed = _apply_filters(base_no_type, filters, include_type=True)

    channels, items_by_id, top_cosine = _channels(
        base_typed, normalized, pool=pool, query_vector=query_vector
    )
    fused = rrf_fuse(channels)
    matched_on = _matched_on(channels)

    ordered_ids = _order(fused, items_by_id, sort)
    count = len(ordered_ids)
    pool_truncated = any(len(ids) >= pool for ids in channels.values())

    page_ids = ordered_ids[offset : offset + limit]
    next_offset = offset + limit if offset + limit < count else None

    page_items: list[ContentItem] = []
    for cid in page_ids:
        item = items_by_id[cid]
        item._search_score = round(fused.get(cid, 0.0), 6)
        item._search_matched_on = matched_on.get(cid, [])
        page_items.append(item)

    confidence = _confidence(top_cosine)
    # Type facet: counts ignore the type filter (so every type stays selectable),
    # as before. Per-type facet: only when exactly one type is active — the
    # contextual "drill into a type, then its filters appear" flow. Its counts
    # ignore its own selection (include_metadata=False) so multi-select is legible.
    facets = {"type": _facet_counts(base_no_type, "type", normalized)}
    if len(filters.types) == 1:
        field = TYPE_FACET_FIELD.get(filters.types[0])
        if field:
            base_type_only = _apply_filters(
                ContentItem.objects.all(),
                filters,
                include_type=True,
                include_metadata=False,
            )
            facets[field] = _metadata_facet_counts(base_type_only, field, normalized)

    return SearchResult(
        query=query,
        normalized=normalized,
        sort=sort,
        count=count,
        pool_truncated=pool_truncated,
        confidence=confidence,
        facets=facets,
        items=page_items,
        limit=limit,
        offset=offset,
        next_offset=next_offset,
        matched_on=matched_on,
    )


def _confidence(top_cosine: float | None) -> str:
    """The low-confidence UI cue: top semantic cosine below the display floor.

    A cue only — search still returns the results. ``None`` (no semantic channel
    yet, Phase 1) is treated as ``"ok"``.
    """
    if top_cosine is None:
        return "ok"
    floor = getattr(settings, "SEARCH_LOW_CONFIDENCE_COSINE", 0.35)
    return "low" if top_cosine < floor else "ok"
