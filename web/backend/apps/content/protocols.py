"""Structural types that let the ranking stack run off the Django ORM.

The ranking stack — :mod:`.lexical`, :mod:`.fusion`, :mod:`.ranking`, and the pool
construction in :mod:`.pipeline` — only ever needs three things from a candidate:
a stable id, a metadata dict to draw text from, and (for the vector channel) an
embedding. It never needs a model instance, a manager, or a database connection.
:class:`ContentItem` satisfies that shape already, so stating it as a protocol
costs nothing at runtime and buys one real thing: the *same production code* can
be scored against an external test collection (see ``eval/``) instead of being
reimplemented there, which is the only way a re-measurement can stay honest as the
ranking stack changes.

Two seams live here:

- :class:`Retrievable` — "a thing that can be ranked". Widening the annotations in
  :mod:`.lexical` and :mod:`.fusion` from ``ContentItem`` to this is a pure typing
  change; the runtime behaviour is byte-identical.
- :class:`VectorIndex` — "a thing that can answer nearest-neighbour queries".
  Production uses :class:`apps.content.retrieval.PgVectorIndex`, which wraps the
  existing pgvector query; the harness passes an in-memory numpy index. Because
  production runs **no ANN index** (every vector query is an exact sequential scan
  over ``ContentItem.embedding``), an exact in-memory index is not an approximation
  of production — it computes the identical ranking.

Both are :func:`runtime_checkable` so a test can assert conformance directly.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Retrievable(Protocol):
    """A candidate the ranking stack can score.

    ``id`` is only ever stringified (``str(item.id)`` is the key that unifies the
    lexical and vector channels, which surface different instances of the same
    row), so a UUID, an int, or a plain string all work. ``metadata`` is the dict
    the lexical channel draws text from — ``search_text`` when present, otherwise
    ``title`` + ``abstract``. ``embedding`` is the unit-length vector, or ``None``
    for a candidate that was never embedded.
    """

    id: Any
    metadata: dict[str, Any]
    embedding: Sequence[float] | None


@runtime_checkable
class VectorIndex(Protocol):
    """A nearest-neighbour index over :class:`Retrievable` candidates."""

    def search(
        self,
        vector: Sequence[float] | None,
        *,
        limit: int,
        exclude_ids: Sequence[Any] | None = None,
    ) -> list[tuple[Retrievable, float]]:
        """Return up to ``limit`` candidates nearest ``vector``, best first.

        Each hit carries its cosine *similarity* in ``[0, 1]`` (higher is more
        relevant), not a distance. An empty or ``None`` vector returns ``[]``
        rather than raising, matching
        :func:`apps.content.retrieval.retrieve_for_vector`.
        """
        ...
