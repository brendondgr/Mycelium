"""The retrieval ladder: candidate stages measured before anything is deployed.

`arms.py` holds a strict rule — no ranking logic of its own, every arm a thin call
into `apps.content`. That rule exists so a production change is measured
automatically. **This module deliberately sits outside it**, and the distinction
matters when reading any number it produces: SPLADE, ColBERT, and the
cross-encoder do not exist in production, so there is nothing to call into. These
are *candidates*. A number from `arms.py` describes Mycelium; a number from here
describes something Mycelium could become.

The ladder keeps the deployed shape — lexical + dense → RRF → (LLM) — and adds
stops between the rungs:

    BM25 ─┐
    dense ─┼─ RRF ─→ [ColBERT MaxSim] ─→ [cross-encoder] ─→ [LLM]
    SPLADE ┘

Each rung is measured against the rung below it on an identical frozen document
set, so a difference is attributable to the stage that was added and nothing else.

**Positional run scores.** Every arm here emits `1/(1 + i)` rather than its own
score, for the reason `arms.py` documents for profile arms: `ir_measures` re-sorts
a run by score and breaks ties its own way, so an arm whose scores tie would be
silently reordered inside the metric. A strictly decreasing positional score
preserves the arm's ordering exactly, which is the thing being measured.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]

Ranking = dict[str, list[tuple[str, float]]]

#: How deep run files go. TREC convention, matching `arms.DEPTH`.
DEPTH = 1000

#: RRF dampening constant, from `apps.content.fusion.DEFAULT_RRF_K`. Held here so
#: a ladder arm fuses identically to production unless an arm overrides it.
RRF_K = 60


def _positional(ordering: Sequence[str], depth: int = DEPTH) -> list[tuple[str, float]]:
    """`[(doc_id, 1/(1+i))]` — an order that no metric can silently re-sort."""
    return [(doc_id, 1.0 / (1.0 + i)) for i, doc_id in enumerate(ordering[:depth])]


def rrf_fuse(channels: Sequence[Sequence[str]], *, k: int = RRF_K) -> list[str]:
    """Reciprocal Rank Fusion over any number of ranked id lists.

    Production's `fuse_interest` takes exactly two channels; this generalizes to
    three so SPLADE can join BM25 and dense as a peer. The formula is unchanged —
    `sum over channels of 1/(k + rank)` — and with two channels and the same `k`
    it reproduces production's ordering exactly.
    """
    scores: dict[str, float] = {}
    for channel in channels:
        for rank, doc_id in enumerate(channel, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    ordered = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    return [doc_id for doc_id, _ in ordered]


# -- shared state -------------------------------------------------------------

#: Base rankings and loaded models, memoized for the life of the process. A day's
#: grid runs many rerank depths over the same base ranking; recomputing it per
#: config would dominate the wall clock for no reason.
_CACHE: dict[tuple, Any] = {}


def _docs_by_id(docs: Sequence[Any]) -> dict[str, Any]:
    key = ("docs_by_id", id(docs))
    if key not in _CACHE:
        _CACHE[key] = {str(doc.id): doc for doc in docs}
    return _CACHE[key]


def _positions(docs: Sequence[Any]) -> dict[str, int]:
    key = ("positions", id(docs))
    if key not in _CACHE:
        _CACHE[key] = {str(doc.id): i for i, doc in enumerate(docs)}
    return _CACHE[key]


def base_ranking(
    name: str,
    queries: Sequence[tuple[str, str]],
    docs: Sequence[Any],
    *,
    index,
    pool_per_interest: int,
    log: Callable[[str], None],
    collection=None,
) -> Ranking:
    """The first-stage ranking a rerank arm consumes, computed at most once.

    `collection` must be forwarded: a base can itself be a ladder arm, and the
    ladder arms need it to locate their cached model artifacts. Omitting it is how
    `xenc_rerank` over a SPLADE base first failed.
    """
    key = ("base", name, id(docs), pool_per_interest)
    if key in _CACHE:
        return _CACHE[key]
    from . import arms as arms_mod

    log(f"computing base ranking '{name}' (pool={pool_per_interest}) …")
    if name in LADDER_ARMS:
        ranking = LADDER_ARMS[name](
            queries, docs, index=index, pool_per_interest=pool_per_interest,
            collection=collection, log=log,
        )
    else:
        ranking = arms_mod.ARMS[name](
            queries, docs, index=index, pool_per_interest=pool_per_interest, log=log
        )
    _CACHE[key] = ranking
    return ranking


# -- SPLADE -------------------------------------------------------------------


def _splade_matrix(docs, collection, log):
    key = ("splade", id(docs))
    if key not in _CACHE:
        from . import neural

        matrix = neural.splade_encode(
            docs, snapshot=collection.snapshot, scope="pooled", log=log
        )
        if matrix.shape[0] != len(docs):
            raise RuntimeError(
                f"SPLADE matrix has {matrix.shape[0]} rows for {len(docs)} docs — "
                "the cache is stale or the subset moved"
            )
        _CACHE[key] = (matrix, neural._splade_model())
    return _CACHE[key]


def splade_only(
    queries: Sequence[tuple[str, str]],
    docs: Sequence[Any],
    *,
    index=None,
    params: dict | None = None,
    collection=None,
    log: Callable[[str], None] = print,
    **_: Any,
) -> Ranking:
    """Learned sparse retrieval alone — the SPLADE ceiling on this collection.

    The interesting comparison is against `bm25_only`, not against dense: both are
    term-weighted sparse retrieval over an inverted index, and the only difference
    is that SPLADE's weights are learned and its query is *expanded* into terms the
    text never contained. That is exactly the job the hand-authored keyword
    clusters do in production, done automatically.
    """
    from . import neural

    matrix, embedder = _splade_matrix(docs, collection, log)
    width = matrix.shape[1]
    doc_ids = [str(doc.id) for doc in docs]

    ranking: Ranking = {}
    for i, (query_id, query_text) in enumerate(queries, start=1):
        qvec = neural.splade_query_vector(embedder, query_text, width)
        scores = np.asarray((matrix @ qvec.T).todense()).ravel()
        top = np.argpartition(-scores, min(DEPTH, len(scores) - 1))[:DEPTH]
        top = top[np.argsort(-scores[top], kind="stable")]
        ranking[query_id] = _positional([doc_ids[j] for j in top if scores[j] > 0])
        if i % 25 == 0:
            log(f"  scored {i}/{len(queries)} queries")
    return ranking


def fusion_bm25_dense_splade(
    queries: Sequence[tuple[str, str]],
    docs: Sequence[Any],
    *,
    index,
    pool_per_interest: int = 100,
    params: dict | None = None,
    collection=None,
    log: Callable[[str], None] = print,
    **_: Any,
) -> Ranking:
    """Three-channel RRF: BM25 ∪ dense ∪ SPLADE, over a true union pool.

    The recall rung. Built on the *union* pool rather than production's
    dense-restricted pool, because a channel that cannot add a document cannot
    add recall — which is the whole point of adding a third one.
    """
    from apps.content import embeddings
    from apps.content.lexical import build_bm25_index, rank_bm25_over

    from . import neural

    matrix, embedder = _splade_matrix(docs, collection, log)
    width = matrix.shape[1]
    doc_ids = [str(doc.id) for doc in docs]

    log(f"building corpus-wide BM25 index over {len(docs)} docs …")
    corpus_index = build_bm25_index(docs)

    ranking: Ranking = {}
    for i, (query_id, query_text) in enumerate(queries, start=1):
        vector = embeddings.embed_text(query_text)
        dense = [str(d.id) for d, _ in index.search(vector, limit=pool_per_interest)]
        lexical = [
            str(d.id)
            for d, _ in rank_bm25_over(query_text, corpus_index)[:pool_per_interest]
        ]
        qvec = neural.splade_query_vector(embedder, query_text, width)
        scores = np.asarray((matrix @ qvec.T).todense()).ravel()
        top = np.argpartition(-scores, min(pool_per_interest, len(scores) - 1))[
            :pool_per_interest
        ]
        top = top[np.argsort(-scores[top], kind="stable")]
        splade = [doc_ids[j] for j in top if scores[j] > 0]

        ranking[query_id] = _positional(rrf_fuse([lexical, dense, splade]))
        if i % 25 == 0:
            log(f"  scored {i}/{len(queries)} queries")
    return ranking


# -- query expansion for the reranker only ------------------------------------


def _expansions(collection_id: str, words: int, log) -> dict[str, str]:
    """`{query_id: prose}` for one target length, from the cache on disk.

    Built by `eval/expand_queries.py`, which sees the query string and nothing
    else — no documents, no judgments — so an arm reading this cannot have
    relevance leaked into it.
    """
    key = ("expansion", collection_id, words)
    if key not in _CACHE:
        import json

        path = (
            REPO_ROOT / "data" / "eval-cache" / "expansions"
            / f"{collection_id}__{words}w.json"
        )
        if not path.exists():
            raise RuntimeError(
                f"no expansion cache at {path}; run eval/expand_queries.py first"
            )
        rows = json.loads(path.read_text())
        ok = sum(1 for r in rows.values() if r.get("ok"))
        log(f"query expansions ~{words}w: {len(rows)} queries, {ok} generated cleanly")
        _CACHE[key] = {qid: r["expanded"] for qid, r in rows.items()}
    return _CACHE[key]


# -- ColBERT ------------------------------------------------------------------


def _colbert_store(docs, collection, log):
    key = ("colbert", id(docs))
    if key not in _CACHE:
        from . import neural

        store = neural.colbert_encode(
            docs, snapshot=collection.snapshot, scope="pooled", log=log
        )
        if len(store) != len(docs):
            raise RuntimeError(
                f"ColBERT store has {len(store)} docs for {len(docs)} — stale cache"
            )
        _CACHE[key] = (store, neural._colbert_model())
    return _CACHE[key]


def colbert_rerank(
    queries: Sequence[tuple[str, str]],
    docs: Sequence[Any],
    *,
    index,
    pool_per_interest: int = 100,
    params: dict | None = None,
    collection=None,
    log: Callable[[str], None] = print,
    **_: Any,
) -> Ranking:
    """Rerank the base ranking's top-K by ColBERT late interaction.

    The rung that should, in principle, catch what a single averaged vector
    cannot: MaxSim aligns *token to token*, so a query phrase can find its match
    in a document that shares no vocabulary with it. Candidates below `depth` keep
    their base order and sit underneath the reranked head.
    """
    from . import neural

    params = params or {}
    depth = int(params.get("rerank_depth", 100))
    base_name = params.get("base", "fusion_union_pool")

    store, embedder = _colbert_store(docs, collection, log)
    positions = _positions(docs)
    base = base_ranking(
        base_name, queries, docs, index=index,
        pool_per_interest=pool_per_interest, log=log, collection=collection,
    )

    log(f"ColBERT reranking top-{depth} of '{base_name}' …")
    ranking: Ranking = {}
    for i, (query_id, _query_text) in enumerate(queries, start=1):
        candidates = [doc_id for doc_id, _ in base.get(query_id, [])]
        head, tail = candidates[:depth], candidates[depth:]
        qvecs = neural.colbert_query_vectors(embedder, _query_text)
        scored = [
            (doc_id, neural.maxsim(qvecs, store.doc(positions[doc_id])))
            for doc_id in head
            if doc_id in positions
        ]
        scored.sort(key=lambda kv: (-kv[1], kv[0]))
        ranking[query_id] = _positional([doc_id for doc_id, _ in scored] + tail)
        if i % 25 == 0:
            log(f"  reranked {i}/{len(queries)} queries")
    return ranking


# -- cross-encoder ------------------------------------------------------------


def _cross_encoder(model: str):
    key = ("xenc", model)
    if key not in _CACHE:
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        _CACHE[key] = TextCrossEncoder(model)
    return _CACHE[key]


def xenc_rerank(
    queries: Sequence[tuple[str, str]],
    docs: Sequence[Any],
    *,
    index,
    pool_per_interest: int = 100,
    params: dict | None = None,
    collection=None,
    log: Callable[[str], None] = print,
    **_: Any,
) -> Ranking:
    """Rerank the base ranking's top-K with a cross-encoder.

    The strongest and cheapest rung on this host: no corpus encoding at all, since
    a cross-encoder reads the query and the document *together* and produces one
    score per pair. Measured at 61.5 pairs/s, so top-100 over 100 queries is about
    three minutes.
    """
    params = params or {}
    depth = int(params.get("rerank_depth", 100))
    base_name = params.get("base", "fusion_union_pool")
    model = params.get("xenc_model", "Xenova/ms-marco-MiniLM-L-6-v2")
    expand_words = params.get("expand_words")

    encoder = _cross_encoder(model)
    # The expansion changes ONLY what the reranker reads. The base ranking is
    # still computed from the original short query, so BM25 keeps the rare-term
    # exact match that `EXP-2026-08-009` showed it is best at — the intervention
    # is confined to the one stage the query length was hurting.
    expanded: dict[str, str] = {}
    if expand_words:
        expanded = _expansions(collection.id, int(expand_words), log)
    by_id = _docs_by_id(docs)
    base = base_ranking(
        base_name, queries, docs, index=index,
        pool_per_interest=pool_per_interest, log=log, collection=collection,
    )

    suffix = f", scored against ~{expand_words}-word prose" if expand_words else ""
    log(f"cross-encoder ({model}) reranking top-{depth} of '{base_name}'{suffix} …")
    ranking: Ranking = {}
    for i, (query_id, query_text) in enumerate(queries, start=1):
        scoring_text = expanded.get(query_id, query_text) if expanded else query_text
        candidates = [doc_id for doc_id, _ in base.get(query_id, [])]
        head, tail = candidates[:depth], candidates[depth:]
        texts = [by_id[doc_id].text for doc_id in head if doc_id in by_id]
        present = [doc_id for doc_id in head if doc_id in by_id]
        if texts:
            scores = list(encoder.rerank(scoring_text, texts, batch_size=32))
            # strict=True: a length mismatch here would silently mis-pair a
            # document with another document's score.
            paired = zip(present, scores, strict=True)
            order = sorted(paired, key=lambda kv: (-kv[1], kv[0]))
            head = [doc_id for doc_id, _ in order]
        ranking[query_id] = _positional(head + tail)
        if i % 10 == 0:
            log(f"  reranked {i}/{len(queries)} queries")
    return ranking


def cascade_colbert_xenc(
    queries: Sequence[tuple[str, str]],
    docs: Sequence[Any],
    *,
    index,
    pool_per_interest: int = 100,
    params: dict | None = None,
    collection=None,
    log: Callable[[str], None] = print,
    **_: Any,
) -> Ranking:
    """Retrieve wide → ColBERT narrows → cross-encoder finishes.

    The standard production cascade, and the point of it is cost: ColBERT's
    reranking is cheap per candidate because the document side is precomputed, so
    it can afford to look at hundreds; the cross-encoder is expensive per
    candidate but only ever sees the few dozen ColBERT promoted.
    """
    params = params or {}
    colbert_depth = int(params.get("colbert_depth", 250))
    xenc_depth = int(params.get("rerank_depth", 50))

    stage1 = colbert_rerank(
        queries, docs, index=index, pool_per_interest=pool_per_interest,
        params={**params, "rerank_depth": colbert_depth},
        collection=collection, log=log,
    )
    key = ("base", "__cascade_stage1", id(docs), pool_per_interest)
    _CACHE[key] = stage1
    return xenc_rerank(
        queries, docs, index=index, pool_per_interest=pool_per_interest,
        params={**params, "base": "__cascade_stage1", "rerank_depth": xenc_depth},
        collection=collection, log=log,
    )


LADDER_ARMS: dict[str, Callable[..., Ranking]] = {
    "splade_only": splade_only,
    "fusion_bm25_dense_splade": fusion_bm25_dense_splade,
    "colbert_rerank": colbert_rerank,
    "xenc_rerank": xenc_rerank,
    "cascade_colbert_xenc": cascade_colbert_xenc,
}
