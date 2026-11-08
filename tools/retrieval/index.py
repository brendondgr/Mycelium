"""pgvector nearest-neighbour retrieval over the content store.

The RAG step of the daily pipeline: given a query vector (a user's interest
embedding), return the content items whose embeddings sit closest to it by cosine
distance. This is the first vector-similarity query in the codebase — until now
embeddings were only stored, never searched.

Cosine distance needs pgvector, so these queries run against Postgres. The
queryset is built lazily; callers that pass an empty/``None`` vector get an empty
result instead of a database error.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from django.db.models import Max
from django.utils import timezone
from pgvector.django import CosineDistance

from tools.retrieval.models import ContentItem

#: A retrieval hit: the item and its cosine *similarity* (1 - distance), in
#: ``[0, 1]`` for unit-length vectors where higher is more relevant.
Hit = tuple[ContentItem, float]


def retrieve_for_vector(
    vector: Sequence[float] | None,
    *,
    content_type: str | None = ContentItem.Type.PAPER,
    limit: int = 20,
    exclude_ids: Sequence | None = None,
    created_on: date | None = None,
) -> list[Hit]:
    """Return up to ``limit`` content items nearest ``vector`` by cosine distance.

    Only items that actually have an embedding are considered. ``content_type``
    filters by paper/grant/fellowship (pass ``None`` for all types).
    ``exclude_ids`` drops items already known to the caller. ``created_on`` (when
    set) restricts the pool to items *gathered* on that calendar day — the freshness
    gate the paper feed uses to surface only the latest batch, never the whole
    historical corpus. Each hit carries the cosine similarity (``1 - distance``) so
    callers can threshold or rank without re-querying.
    """
    if vector is None or len(vector) == 0:
        return []

    queryset = ContentItem.objects.filter(embedding__isnull=False)
    if content_type:
        queryset = queryset.filter(type=content_type)
    if created_on is not None:
        queryset = queryset.filter(created_at__date=created_on)
    if exclude_ids:
        queryset = queryset.exclude(id__in=list(exclude_ids))

    queryset = queryset.annotate(
        distance=CosineDistance("embedding", vector)
    ).order_by("distance")[:limit]

    return [(item, _similarity(item.distance)) for item in queryset]


def latest_gather_date(
    *, content_type: str = ContentItem.Type.PAPER
) -> date | None:
    """The freshest day any *embedded* item of ``content_type`` was gathered.

    "Gathered" is ingestion time (``ContentItem.created_at``, set once on first
    insert and never rewritten by re-scrapes), so this is the date of the freshest
    batch that can actually be retrieved. Only embedded items count, since a paper
    with no vector can never surface. Returns ``None`` when the store holds no such
    item yet. The paper pipeline passes this back into :func:`retrieve_for_vector`
    as ``created_on`` so a run recommends only the latest batch.
    """
    latest = (
        ContentItem.objects.filter(
            type=content_type, embedding__isnull=False
        ).aggregate(latest=Max("created_at"))
    )["latest"]
    return timezone.localdate(latest) if latest is not None else None


class PgVectorIndex:
    """The production :class:`~tools.retrieval.protocols.VectorIndex`.

    A one-method adapter over :func:`retrieve_for_vector` so the pool builder in
    :mod:`apps.content.pipeline` depends on the *protocol* rather than on this
    module directly. The scoping arguments a caller cannot vary per query
    (``content_type``, ``created_on``) are bound once at construction; ``limit``
    and ``exclude_ids`` stay per-query because the pool builder varies them.

    This carries no behaviour of its own — it exists so an alternative index (an
    in-memory one, for offline evaluation) can be substituted without the pipeline
    knowing. See :mod:`tools.retrieval.protocols` for why that matters.
    """

    def __init__(
        self,
        *,
        content_type: str | None = ContentItem.Type.PAPER,
        created_on: date | None = None,
    ) -> None:
        self.content_type = content_type
        self.created_on = created_on

    def search(
        self,
        vector: Sequence[float] | None,
        *,
        limit: int,
        exclude_ids: Sequence | None = None,
    ) -> list[Hit]:
        return retrieve_for_vector(
            vector,
            content_type=self.content_type,
            limit=limit,
            exclude_ids=exclude_ids,
            created_on=self.created_on,
        )


def _similarity(distance: float | None) -> float:
    """Cosine similarity from cosine distance, clamped to ``[0, 1]``."""
    if distance is None:
        return 0.0
    similarity = 1.0 - float(distance)
    if similarity < 0.0:
        return 0.0
    if similarity > 1.0:
        return 1.0
    return similarity
