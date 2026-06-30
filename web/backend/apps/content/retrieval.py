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

from pgvector.django import CosineDistance

from .models import ContentItem

#: A retrieval hit: the item and its cosine *similarity* (1 - distance), in
#: ``[0, 1]`` for unit-length vectors where higher is more relevant.
Hit = tuple[ContentItem, float]


def retrieve_for_vector(
    vector: Sequence[float] | None,
    *,
    content_type: str | None = ContentItem.Type.PAPER,
    limit: int = 20,
    exclude_ids: Sequence | None = None,
) -> list[Hit]:
    """Return up to ``limit`` content items nearest ``vector`` by cosine distance.

    Only items that actually have an embedding are considered. ``content_type``
    filters by paper/grant/fellowship (pass ``None`` for all types).
    ``exclude_ids`` drops items already known to the caller. Each hit carries the
    cosine similarity (``1 - distance``) so callers can threshold or rank without
    re-querying.
    """
    if vector is None or len(vector) == 0:
        return []

    queryset = ContentItem.objects.filter(embedding__isnull=False)
    if content_type:
        queryset = queryset.filter(type=content_type)
    if exclude_ids:
        queryset = queryset.exclude(id__in=list(exclude_ids))

    queryset = queryset.annotate(
        distance=CosineDistance("embedding", vector)
    ).order_by("distance")[:limit]

    return [(item, _similarity(item.distance)) for item in queryset]


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
