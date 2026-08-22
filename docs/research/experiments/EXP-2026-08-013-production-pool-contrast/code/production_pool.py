"""The union-pool variants, built on the production functions rather than beside them.

`apps.content.pipeline._build_pool` is the deployed pool builder and is used
unmodified as arm A1. The variants here change **one thing** — which candidates
enter the pool — and then call the same `build_bm25_index` / `rank_bm25_over` /
`fuse_interest` production code the deployed path calls. Nothing in
`apps.content` is edited; the point of `EXP-2026-08-013` is to measure the
deployed stack, and a reimplementation would measure a copy of it.

Three pool constructions:

- :func:`dense_pool` — a thin pass-through to `_build_pool`, present so the arms
  read symmetrically at the call site.
- :func:`union_pool_harness` — the arm `eval/harness/arms.py::fusion_union_pool`
  defines, mirrored exactly so this experiment's contrast is the *same*
  contrast C-008 was measured with. Its lexical channel is corpus-wide BM25
  truncated at ``pool_per_interest``.
- :func:`union_pool_prod` — `_build_pool` with a wider seed: the pool is the
  dense union **plus** the corpus-wide lexical union, and the per-interest
  lexical channel is then BM25 over that pool, exactly as `_build_pool` does it.
  This is the variant a production change would actually take, and it avoids the
  truncation asymmetry the harness arm carries (see ISSUES.md §2).

The lexical channel of the two union builders is injectable (``lexical_topk``)
so the same code serves the BM25Okapi arm and the Postgres-FTS arm without a
second implementation.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from apps.content.fusion import fuse_interest
from apps.content.lexical import build_bm25_index, rank_bm25_over
from apps.content.pipeline import _build_pool

#: ``(query_text, limit) -> [(item, score)]`` best first, over the whole in-scope
#: corpus. The seam that lets one union builder serve BM25 and FTS alike.
LexicalTopK = Callable[[str, int], list[tuple[Any, float]]]

PoolResult = tuple[dict[str, Any], dict[str, dict[str, float]], dict[str, float]]


def dense_pool(search_ints, *, index, pool_per_interest: int) -> PoolResult:
    """Production, verbatim. BM25 indexes only what the dense channel retrieved."""
    return _build_pool(
        search_ints,
        content_type=None,
        pool_per_interest=pool_per_interest,
        created_on=None,
        index=index,
    )


def _dense_channel(
    search_ints, *, index, pool_per_interest: int, embed
) -> tuple[dict[str, Any], dict[str, list], dict[str, float]]:
    """Each interest's dense pull, unioned — the half both arms share."""
    pool: dict[str, Any] = {}
    hits: dict[str, list] = {}
    best_cosine: dict[str, float] = {}
    for interest in search_ints:
        vector = embed(interest.embed_text)
        if vector is None:
            continue
        unified = []
        for item, similarity in index.search(vector, limit=pool_per_interest):
            key = str(item.id)
            pool.setdefault(key, item)
            unified.append((pool[key], similarity))
            if similarity > best_cosine.get(key, 0.0):
                best_cosine[key] = similarity
        hits[interest.label] = unified
    return pool, hits, best_cosine


def union_pool_harness(
    search_ints,
    *,
    index,
    pool_per_interest: int,
    lexical_topk: LexicalTopK,
    embed,
) -> PoolResult:
    """`eval/harness/arms.py::fusion_union_pool`, mirrored.

    Both channels are restricted to the union pool with their orderings intact
    and handed to the production :func:`fuse_interest`.
    """
    pool, dense_hits, best_cosine = _dense_channel(
        search_ints, index=index, pool_per_interest=pool_per_interest, embed=embed
    )
    lexical_hits: dict[str, list] = {}
    for interest in search_ints:
        hits = lexical_topk(interest.query_text, pool_per_interest)
        for item, _score in hits:
            pool.setdefault(str(item.id), item)
        lexical_hits[interest.label] = hits

    if not pool:
        return {}, {}, {}

    per_interest: dict[str, dict[str, float]] = {}
    for interest in search_ints:
        pooled_lexical = [
            (pool[str(i.id)], s)
            for i, s in lexical_hits.get(interest.label, [])
            if str(i.id) in pool
        ]
        pooled_dense = [
            (pool[str(i.id)], s)
            for i, s in dense_hits.get(interest.label, [])
            if str(i.id) in pool
        ]
        fused = fuse_interest(pooled_lexical, pooled_dense)
        if fused:
            per_interest[interest.label] = fused
    return pool, per_interest, best_cosine


def union_pool_prod(
    search_ints,
    *,
    index,
    pool_per_interest: int,
    lexical_topk: LexicalTopK,
    embed,
) -> PoolResult:
    """`_build_pool` with a wider seed — the shippable variant.

    Identical to the deployed builder except that the pool is seeded with the
    corpus-wide lexical union as well as the dense union. The per-interest
    lexical channel is then BM25 over that pool, which is what `_build_pool`
    does today; only the pool it runs over is different.
    """
    pool, dense_hits, best_cosine = _dense_channel(
        search_ints, index=index, pool_per_interest=pool_per_interest, embed=embed
    )
    for interest in search_ints:
        for item, _score in lexical_topk(interest.query_text, pool_per_interest):
            pool.setdefault(str(item.id), item)

    if not pool:
        return {}, {}, {}

    bm25_index = build_bm25_index(list(pool.values()))
    per_interest: dict[str, dict[str, float]] = {}
    for interest in search_ints:
        fused = fuse_interest(
            rank_bm25_over(interest.query_text, bm25_index),
            dense_hits.get(interest.label, []),
        )
        if fused:
            per_interest[interest.label] = fused
    return pool, per_interest, best_cosine


def bm25_lexical(corpus: Sequence[Any]) -> LexicalTopK:
    """A corpus-wide BM25 channel over ``corpus``, built once and reused.

    Uses `apps.content.lexical.build_bm25_index` — the same index the deployed
    path builds, over a wider set of documents.
    """
    index = build_bm25_index(list(corpus))
    if index is None:
        raise RuntimeError("build_bm25_index returned None over the in-scope corpus")

    def topk(query_text: str, limit: int) -> list[tuple[Any, float]]:
        return rank_bm25_over(query_text, index)[:limit]

    return topk
