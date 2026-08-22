"""Does the dense-restricted pool still win once the three-channel pool is reranked?

    docker compose up -d postgres
    uv run --project eval python .../code/run.py

`EXP-2026-08-015` and `EXP-2026-08-016` compared `fusion_dense_pool+xenc` against
a **bare** three-channel pool, which confounds the pool with the reranker. This
gives both pools the same cross-encoder so the only remaining difference is which
documents are in them.

Two arms, two queries, four corpora, sixteen lists. The pool builders come from
`EXP-2026-08-013` and the sparse encoder and RRF from `eval/harness` — imported,
never reimplemented, so the two arms differ only where they are meant to.

Writes `data/lists.json`. No LLM, no network.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = EXP_DIR.parents[3]
sys.path.insert(0, str(REPO_ROOT / "eval"))
sys.path.insert(0, str(REPO_ROOT / "web" / "backend"))
sys.path.insert(
    0, str(EXP_DIR.parent / "EXP-2026-08-013-production-pool-contrast" / "code")
)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ["DATABASE_URL"] = os.environ.get(
    "MYCELIUM_DATABASE_URL", "postgres://mycelium:mycelium@127.0.0.1:11450/mycelium"
)
os.environ.setdefault(
    "FASTEMBED_CACHE_PATH", str(REPO_ROOT / "data" / "eval-cache" / "fastembed")
)
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

QUERIES = ["Agentic AI in healthcare", "knowledge graphs"]
TYPES = ["paper", "grant", "conference", "fellowship"]
POOL_PER_INTEREST = 100
RERANK_DEPTH = 50
TOP_N = 10
CROSS_ENCODER = "Xenova/ms-marco-MiniLM-L-6-v2"
SNAPSHOT = "mycelium-store-2026-08-22"

#: A fourth set of letters — no overlap with A-J, W-Z or M/N/P/R, so no previous
#: verdict can carry over. The same letter means the same arm throughout.
BLIND_ORDER = {
    "K": "fusion_union_splade+xenc",
    "V": "fusion_dense_pool+xenc",
}


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def sorted_ids(scores: dict[str, float]) -> list[str]:
    """Best first, ties broken by id so the ranking is not a hash ordering."""
    return [k for k, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))]


def rrf_fuse(channels, *, k: int = 60) -> list[str]:
    """RRF over any number of ranked id lists — `eval/harness/ladder.py`'s."""
    scores: dict[str, float] = {}
    for channel in channels:
        for rank, doc_id in enumerate(channel, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return [i for i, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))]


def title_of(item) -> str:
    meta = item.metadata or {}
    return " ".join(str(meta.get("title") or meta.get("name") or "(untitled)").split())


def main() -> int:
    import django

    django.setup()

    import numpy as np
    import production_pool as pp
    from apps.content import embeddings
    from apps.content.interests_query import SearchInterest
    from apps.content.lexical import _item_text, build_bm25_index, rank_bm25_over
    from apps.content.models import ContentItem
    from apps.content.retrieval import PgVectorIndex
    from fastembed.rerank.cross_encoder import TextCrossEncoder
    from harness import neural

    encoder = TextCrossEncoder(model_name=CROSS_ENCODER)
    out: dict = {
        "queries": QUERIES,
        "types": TYPES,
        "blind_labels": BLIND_ORDER,
        "cells": {},
        "timing": [],
        "corpus_sizes": {},
    }

    for content_type in TYPES:
        docs = list(
            ContentItem.objects.filter(
                type=content_type, embedding__isnull=False
            ).order_by("id")
        )
        by_id = {str(d.id): d for d in docs}
        doc_ids = [str(d.id) for d in docs]
        out["corpus_sizes"][content_type] = len(docs)
        log(f"=== {content_type}: {len(docs)} docs ===")

        corpus_bm25 = build_bm25_index(docs)
        splade_matrix = neural.splade_encode(
            [type("D", (), {"id": d.id, "text": _item_text(d)})() for d in docs],
            snapshot=SNAPSHOT,
            scope=content_type,
            log=lambda m: None,
        )
        splade_model = neural._splade_model()
        width = splade_matrix.shape[1]
        index = PgVectorIndex(content_type=content_type, created_on=None)

        def rerank(query: str, ids: list[str], _by_id=by_id) -> list[str]:
            """The shared rerank stage — identical for both arms by construction.

            ``_by_id`` is bound at definition time rather than closed over: this is
            redefined once per corpus and only ever called inside that iteration,
            but binding it makes that explicit instead of load-bearing.
            """
            if not ids:
                return []
            scores = list(encoder.rerank(query, [_item_text(_by_id[i]) for i in ids]))
            order = sorted(range(len(ids)), key=lambda j: (-scores[j], ids[j]))
            return [ids[j] for j in order]

        for query in QUERIES:
            interest = SearchInterest(
                label=query, query_text=query, embed_text=query
            )
            rankings: dict[str, list[str]] = {}
            timings: dict[str, float] = {}

            # --- production's dense-restricted pool, reranked
            started = time.perf_counter()
            _pool, per_interest, _cos = pp.dense_pool(
                [interest], index=index, pool_per_interest=POOL_PER_INTEREST
            )
            base = sorted_ids(per_interest.get(query, {}))[:RERANK_DEPTH]
            rankings["fusion_dense_pool+xenc"] = rerank(query, base)
            timings["fusion_dense_pool+xenc"] = time.perf_counter() - started

            # --- three channels over a union pool, reranked
            started = time.perf_counter()
            vector = embeddings.embed_text(query)
            qvec = neural.splade_query_vector(splade_model, query, width)
            scores = np.asarray((splade_matrix @ qvec.T).todense()).ravel()
            cut = min(POOL_PER_INTEREST, len(scores) - 1)
            top = np.argpartition(-scores, cut)[:POOL_PER_INTEREST]
            top = top[np.argsort(-scores[top], kind="stable")]
            base = rrf_fuse([
                [
                    str(d.id)
                    for d, _ in rank_bm25_over(query, corpus_bm25)[:POOL_PER_INTEREST]
                ],
                [str(d.id) for d, _ in index.search(vector, limit=POOL_PER_INTEREST)],
                [doc_ids[j] for j in top if scores[j] > 0],
            ])[:RERANK_DEPTH]
            rankings["fusion_union_splade+xenc"] = rerank(query, base)
            timings["fusion_union_splade+xenc"] = time.perf_counter() - started

            out["cells"][f"{query}|{content_type}"] = {
                arm: [
                    {"id": i, "title": title_of(by_id[i])}
                    for i in rankings[arm][:TOP_N]
                ]
                for arm in BLIND_ORDER.values()
            }
            for arm in BLIND_ORDER.values():
                out["timing"].append({
                    "type": content_type, "query": query,
                    "arm": arm, "seconds": timings[arm],
                })
            log(f"  {query!r}: 2 arms scored")

    (EXP_DIR / "data").mkdir(exist_ok=True)
    (EXP_DIR / "data" / "lists.json").write_text(json.dumps(out, indent=1) + "\n")
    log(f"wrote {len(out['cells'])} cells to data/lists.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
