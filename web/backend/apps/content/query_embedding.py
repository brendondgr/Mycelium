"""Embed a search query into the shared corpus vector space (Redis-cached).

The semantic search channel only works if the *query* and the *documents* are
embedded by the **same** model into the same space, so this reuses the exact
shared BGE embedder (:mod:`apps.content.embeddings`, ``BAAI/bge-small-en-v1.5``,
384-dim) that ingest uses on the corpus — never a second model.

Kept as its own thin module so the view can embed once while
:mod:`apps.content.search` stays embedder- and cache-free and therefore trivially
unit-testable with an injected vector. A repeated search skips the (slow) model
call: the normalized query → its vector is cached in a dedicated Redis db (the
``"search"`` cache alias). Everything degrades to ``None``/no-cache when the
embedder is absent or Redis is unreachable — never an error.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Sequence

from . import embeddings

logger = logging.getLogger(__name__)

_CACHE_ALIAS = "search"
_CACHE_PREFIX = "qvec:"


def _cache_key(normalized_query: str) -> str:
    """A safe, bounded cache key (hashed so spaces/length never trip a backend)."""
    digest = hashlib.blake2s(normalized_query.encode("utf-8")).hexdigest()
    return _CACHE_PREFIX + digest


def _cache():
    """The search cache, or ``None`` when it is misconfigured/unavailable."""
    try:
        from django.core.cache import caches

        return caches[_CACHE_ALIAS]
    except Exception:  # pragma: no cover - defensive: bad/missing alias
        return None


def embed_query(normalized_query: str) -> Sequence[float] | None:
    """Embed a *normalized* query, or ``None`` when no embedder is available.

    The input must already be normalized (:func:`apps.content.search.normalize_query`)
    so the cache key and the embedded text agree. A cache hit skips the model
    call; a cache miss embeds once and stores the vector. All cache access is
    best-effort — a Redis outage simply means embedding every time.
    """
    if not normalized_query:
        return None

    cache = _cache()
    key = _cache_key(normalized_query)
    if cache is not None:
        try:
            cached = cache.get(key)
        except Exception:  # pragma: no cover - Redis down mid-request
            logger.warning("search embedding cache read failed", exc_info=True)
            cache = None
        else:
            if cached is not None:
                return cached

    vector = embeddings.embed_text(normalized_query)
    if vector is not None and cache is not None:
        try:
            cache.set(key, vector)
        except Exception:  # pragma: no cover - Redis down mid-request
            logger.warning("search embedding cache write failed", exc_info=True)
    return vector
