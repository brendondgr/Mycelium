"""Embed a search query into the shared corpus vector space.

The semantic search channel only works if the *query* and the *documents* are
embedded by the **same** model into the same space, so this reuses the exact
shared BGE embedder (:mod:`apps.content.embeddings`, ``BAAI/bge-small-en-v1.5``,
384-dim) that ingest uses on the corpus — never a second model.

Kept as its own thin module so the view can embed once (and, in Phase 3, cache
the vector in Redis keyed by the normalized query to skip the model call on
repeats) while :mod:`apps.content.search` stays embedder- and cache-free and
therefore trivially unit-testable with an injected vector. Degrades to ``None``
when no embedder is installed — the search path then leans on lexical + fuzzy.
"""

from __future__ import annotations

from collections.abc import Sequence

from . import embeddings


def embed_query(normalized_query: str) -> Sequence[float] | None:
    """Embed a *normalized* query, or ``None`` when no embedder is available.

    The input must already be normalized (:func:`apps.content.search.normalize_query`)
    so the Phase 3 cache key and the embedded text agree.
    """
    if not normalized_query:
        return None
    return embeddings.embed_text(normalized_query)
