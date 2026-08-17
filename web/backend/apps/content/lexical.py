"""The BM25 lexical retrieval channel over the day's candidate pool.

The vector channel (:mod:`apps.content.retrieval`) answers "what is semantically
near this interest?"; this module adds the complementary lexical channel — "which
candidate papers actually contain this interest's terms?" — so the per-interest
fusion (:mod:`apps.content.fusion`) blends meaning with exact term overlap.

Given the "targeted, bounded ingestion" architecture, BM25 needs no search engine:
it runs in-process (``rank_bm25.BM25Okapi``) over the day's bounded candidate
candidate pool — the same pool the vector ANN draws from. The index is the
expensive part, so build it **once per run** (:func:`build_bm25_index`) and score
every interest query against that one index (:func:`rank_bm25_over`).

``rank_bm25`` is imported lazily and every entry point degrades to an empty result
rather than raising, so a missing dependency or empty pool simply drops the lexical
channel (fusion then falls back to vector-only) — matching the pipeline's "every
missing capability degrades to a status, not a crash" convention.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass

from .protocols import Retrievable

logger = logging.getLogger(__name__)

#: A lexical hit: the item and its raw BM25 score (higher is more relevant). No
#: normalization here — that happens per interest, after RRF (see fusion).
Hit = tuple[Retrievable, float]

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    """Lowercase word/number tokens — the one tokenizer shared index-and-query.

    Kept deliberately simple (no stemming/stopwords) so indexing and querying
    tokenize identically; BM25's term weighting already discounts common terms.
    """
    return _TOKEN_RE.findall((text or "").casefold())


def _item_text(item: Retrievable) -> str:
    meta = item.metadata or {}
    # Grants/conferences carry a prebuilt ``search_text`` (title/scope + context,
    # or — post plan Phase 8 — the verified LLM extraction); papers use
    # title+abstract. Prefer the explicit field when present.
    prebuilt = meta.get("search_text")
    if prebuilt:
        return str(prebuilt)
    return f"{meta.get('title', '')} {meta.get('abstract', '')}"


@dataclass
class BM25Index:
    """A BM25 index built once over a candidate pool, queryable per interest."""

    items: list[Retrievable]
    _bm25: object  # rank_bm25.BM25Okapi — kept opaque to avoid a hard import

    def rank(self, query_text: str) -> list[Hit]:
        """Score every candidate against ``query_text``, best first.

        An empty or all-stopword query yields ``[]``. Zero-score candidates are
        dropped (a query term must actually appear) so an interest only
        contributes papers it truly matches lexically.
        """
        tokens = _tokenize(query_text)
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        hits = [
            (item, float(score))
            for item, score in zip(self.items, scores, strict=False)
            if score > 0
        ]
        hits.sort(key=lambda hit: hit[1], reverse=True)
        return hits


def build_bm25_index(candidates: Sequence[Retrievable]) -> BM25Index | None:
    """Build one BM25 index over ``candidates``' title+abstract text.

    Returns ``None`` — the signal to skip the lexical channel — when ``rank_bm25``
    is unavailable, the pool is empty, or no candidate carries any indexable text.
    """
    items = list(candidates)
    if not items:
        return None
    try:
        from rank_bm25 import BM25Okapi
    except ImportError:
        logger.warning(
            "rank_bm25 not installed; BM25 lexical channel disabled "
            "(fusion falls back to vector-only)."
        )
        return None

    corpus = [_tokenize(_item_text(item)) for item in items]
    if not any(corpus):
        return None
    return BM25Index(items=items, _bm25=BM25Okapi(corpus))


def rank_bm25_over(
    query_text: str, index: BM25Index | None
) -> list[Hit]:
    """Rank the indexed candidates against ``query_text`` (descending).

    Convenience over :meth:`BM25Index.rank` that tolerates a ``None`` index (no
    lexical channel available) by returning ``[]``.
    """
    if index is None:
        return []
    return index.rank(query_text)
