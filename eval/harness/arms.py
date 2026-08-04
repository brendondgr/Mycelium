"""The evaluation arms. Every one is a thin call into `apps.content`.

The discipline that makes this harness worth building: **no arm contains ranking
logic of its own.** Each is a few lines of plumbing around the production
functions, so when `fusion.py` or `lexical.py` changes, the next run measures the
change automatically and nothing here needs editing.

- `bm25_only` — whether this repository's BM25 is correct at all. No embeddings.
- `dense_only` — the bge-small ceiling on its own.
- `fusion_dense_pool` — **production behaviour**: BM25 indexes only what dense
  retrieval already found.
- `fusion_union_pool` — true hybrid, BM25 top-N union dense top-N. Its gap from
  the arm above is exactly what the pool restriction costs.
- `fusion_full` — the above plus `rerank_by_focus`.

`fusion_dense_pool` runs the real `_build_pool`, which is why the `VectorIndex`
seam had to exist: it is the one parameter that swaps pgvector for the in-memory
index without the pipeline knowing.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

Ranking = dict[str, list[tuple[str, float]]]

#: How deep each run file goes. TREC convention, and what LongEval expects.
DEPTH = 1000


def _sorted_hits(
    scores: dict[str, float], depth: int = DEPTH
) -> list[tuple[str, float]]:
    """`{doc_id: score}` → a deterministic best-first list.

    Ties break on `doc_id` so the same inputs always produce byte-identical run
    files — a precondition for the harness's determinism goal.
    """
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:depth]


def bm25_only(
    queries: Sequence[tuple[str, str]],
    docs: Sequence[Any],
    *,
    log: Callable[[str], None] = print,
    **_: Any,
) -> Ranking:
    """Production BM25 over the whole corpus. No embeddings involved."""
    from apps.content.lexical import build_bm25_index, rank_bm25_over

    log(f"building BM25 index over {len(docs)} docs …")
    index = build_bm25_index(docs)
    if index is None:
        raise RuntimeError("build_bm25_index returned None — no indexable text?")

    ranking: Ranking = {}
    for i, (query_id, query_text) in enumerate(queries, start=1):
        hits = rank_bm25_over(query_text, index)
        ranking[query_id] = [(str(item.id), score) for item, score in hits[:DEPTH]]
        if i % 25 == 0:
            log(f"  scored {i}/{len(queries)} queries")
    return ranking


def dense_only(
    queries: Sequence[tuple[str, str]],
    docs: Sequence[Any],
    *,
    index,
    log: Callable[[str], None] = print,
    **_: Any,
) -> Ranking:
    """The vector channel alone, through the same index production would use."""
    from apps.content import embeddings

    ranking: Ranking = {}
    for i, (query_id, query_text) in enumerate(queries, start=1):
        vector = embeddings.embed_text(query_text)
        hits = index.search(vector, limit=DEPTH)
        ranking[query_id] = [(str(doc.id), sim) for doc, sim in hits]
        if i % 25 == 0:
            log(f"  scored {i}/{len(queries)} queries")
    return ranking


def fusion_dense_pool(
    queries: Sequence[tuple[str, str]],
    docs: Sequence[Any],
    *,
    index,
    pool_per_interest: int = 100,
    log: Callable[[str], None] = print,
    **_: Any,
) -> Ranking:
    """Production behaviour: `_build_pool` verbatim, one interest per query.

    This is claim C1 as actually implemented — the dense channel picks the pool,
    BM25 only reorders inside it.
    """
    from apps.content.pipeline import _build_pool

    from .datasets import search_interest

    ranking: Ranking = {}
    for i, (query_id, query_text) in enumerate(queries, start=1):
        _pool, per_interest, _best = _build_pool(
            [search_interest(query_text)],
            content_type=None,
            pool_per_interest=pool_per_interest,
            created_on=None,
            index=index,
        )
        scores = per_interest.get(query_text, {})
        ranking[query_id] = _sorted_hits(scores)
        if i % 25 == 0:
            log(f"  scored {i}/{len(queries)} queries")
    return ranking


def fusion_union_pool(
    queries: Sequence[tuple[str, str]],
    docs: Sequence[Any],
    *,
    index,
    pool_per_interest: int = 100,
    log: Callable[[str], None] = print,
    **_: Any,
) -> Ranking:
    """True hybrid: the pool is BM25 top-N ∪ dense top-N, then production fusion.

    The audit's sharpest structural criticism is that BM25 currently indexes only
    what dense retrieval already found, so the lexical channel can never *add* a
    document — only reorder. This arm is that criticism turned into a number: it
    uses the identical `fuse_interest` call, changing only which candidates are in
    the pool.
    """
    from apps.content import embeddings
    from apps.content.fusion import fuse_interest
    from apps.content.lexical import build_bm25_index, rank_bm25_over

    log(f"building corpus-wide BM25 index over {len(docs)} docs …")
    corpus_index = build_bm25_index(docs)
    if corpus_index is None:
        raise RuntimeError("build_bm25_index returned None — no indexable text?")

    ranking: Ranking = {}
    for i, (query_id, query_text) in enumerate(queries, start=1):
        vector = embeddings.embed_text(query_text)
        dense_hits = index.search(vector, limit=pool_per_interest)
        lexical_hits = rank_bm25_over(query_text, corpus_index)[:pool_per_interest]

        pool: dict[str, Any] = {str(doc.id): doc for doc, _ in dense_hits}
        for doc, _ in lexical_hits:
            pool.setdefault(str(doc.id), doc)

        # Restrict both channels to the union pool, preserving their orderings —
        # then hand them to the *same* fusion function production calls.
        pooled_lexical = [(d, s) for d, s in lexical_hits if str(d.id) in pool]
        pooled_dense = [(d, s) for d, s in dense_hits if str(d.id) in pool]
        scores = fuse_interest(pooled_lexical, pooled_dense)
        ranking[query_id] = _sorted_hits(scores)
        if i % 25 == 0:
            log(f"  scored {i}/{len(queries)} queries")
    return ranking


def fusion_full(
    queries: Sequence[tuple[str, str]],
    docs: Sequence[Any],
    *,
    index,
    pool_per_interest: int = 100,
    log: Callable[[str], None] = print,
    **_: Any,
) -> Ranking:
    """`fusion_dense_pool` plus the production focus re-rank.

    LongEval gives one keyword query and no declared research areas, so the focus
    signal here is the query's own terms — the closest honest analogue. Whether
    that helps or hurts is precisely what this arm reports.
    """
    from apps.content.pipeline import _build_pool
    from apps.content.ranking import rerank_by_focus

    from .datasets import search_interest

    ranking: Ranking = {}
    for i, (query_id, query_text) in enumerate(queries, start=1):
        pool, per_interest, _best = _build_pool(
            [search_interest(query_text)],
            content_type=None,
            pool_per_interest=pool_per_interest,
            created_on=None,
            index=index,
        )
        scores = per_interest.get(query_text, {})
        hits = sorted(
            ((pool[key], value) for key, value in scores.items() if key in pool),
            key=lambda kv: -kv[1],
        )
        reranked = rerank_by_focus(hits, [query_text])
        ranking[query_id] = _sorted_hits(
            {str(hit.item.id): hit.score for hit in reranked}
        )
        if i % 25 == 0:
            log(f"  scored {i}/{len(queries)} queries")
    return ranking


ARMS: dict[str, Callable[..., Ranking]] = {
    "bm25_only": bm25_only,
    "dense_only": dense_only,
    "fusion_dense_pool": fusion_dense_pool,
    "fusion_union_pool": fusion_union_pool,
    "fusion_full": fusion_full,
}

#: Arms that never touch a vector — runnable before any corpus is embedded.
LEXICAL_ONLY = {"bm25_only"}
