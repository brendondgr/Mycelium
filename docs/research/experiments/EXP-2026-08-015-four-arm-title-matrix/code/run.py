"""Four arms, one query, four corpora — titles and ranks only (`EXP-2026-08-015`).

    docker compose up -d postgres
    uv run --project eval python .../code/run.py

`EXP-2026-08-014` asked ten arms, three queries and four categories, and the
answer that came back included "the booklet is too long to navigate". This is the
same measurement cut to the four arms the reader named and the one query they
named, so the output fits on a page per category.

The arms are the production functions, and the union-pool builders are imported
from `EXP-2026-08-013` — the same code all three experiments have used.

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

QUERY = "Agentic AI in healthcare"
TYPES = ["paper", "grant", "conference", "fellowship"]
POOL_PER_INTEREST = 100
RERANK_DEPTH = 50
TOP_N = 10
CROSS_ENCODER = "Xenova/ms-marco-MiniLM-L-6-v2"
SNAPSHOT = "mycelium-store-2026-08-22"

#: Fresh letters, deliberately not A-J: reusing them would carry the previous
#: read's verdicts into this one, and A-D would invite the reader to assume the
#: mapping was unchanged.
BLIND_ORDER = {
    "W": "fusion_dense_pool+xenc",
    "X": "fusion_union_splade",
    "Y": "fusion_union_pool",
    "Z": "fusion_dense_pool",
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
    return " ".join(
        str(meta.get("title") or meta.get("name") or "(untitled)").split()
    )


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
    interest = SearchInterest(label=QUERY, query_text=QUERY, embed_text=QUERY)
    out: dict = {
        "query": QUERY,
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

        rankings: dict[str, list[str]] = {}
        timings: dict[str, float] = {}

        def lexical_topk(text: str, limit: int, _idx=corpus_bm25):
            return rank_bm25_over(text, _idx)[:limit]

        # --- production as deployed
        started = time.perf_counter()
        _pool, per_interest, _cos = pp.dense_pool(
            [interest], index=index, pool_per_interest=POOL_PER_INTEREST
        )
        rankings["fusion_dense_pool"] = sorted_ids(per_interest.get(QUERY, {}))[
            :RERANK_DEPTH
        ]
        timings["fusion_dense_pool"] = time.perf_counter() - started

        # --- union pool
        started = time.perf_counter()
        _pool, per_interest_u, _cos = pp.union_pool_prod(
            [interest],
            index=index,
            pool_per_interest=POOL_PER_INTEREST,
            lexical_topk=lexical_topk,
            embed=embeddings.embed_text,
        )
        rankings["fusion_union_pool"] = sorted_ids(per_interest_u.get(QUERY, {}))[
            :RERANK_DEPTH
        ]
        timings["fusion_union_pool"] = time.perf_counter() - started

        # --- three channels
        started = time.perf_counter()
        vector = embeddings.embed_text(QUERY)
        qvec = neural.splade_query_vector(splade_model, QUERY, width)
        scores = np.asarray((splade_matrix @ qvec.T).todense()).ravel()
        cut = min(POOL_PER_INTEREST, len(scores) - 1)
        top = np.argpartition(-scores, cut)[:POOL_PER_INTEREST]
        top = top[np.argsort(-scores[top], kind="stable")]
        rankings["fusion_union_splade"] = rrf_fuse([
            [str(d.id) for d, _ in rank_bm25_over(QUERY, corpus_bm25)[:POOL_PER_INTEREST]],
            [str(d.id) for d, _ in index.search(vector, limit=POOL_PER_INTEREST)],
            [doc_ids[j] for j in top if scores[j] > 0],
        ])[:RERANK_DEPTH]
        timings["fusion_union_splade"] = time.perf_counter() - started

        # --- production + cross-encoder
        started = time.perf_counter()
        ids = rankings["fusion_dense_pool"]
        xscores = list(encoder.rerank(QUERY, [_item_text(by_id[i]) for i in ids]))
        order = sorted(range(len(ids)), key=lambda j: (-xscores[j], ids[j]))
        rankings["fusion_dense_pool+xenc"] = [ids[j] for j in order]
        timings["fusion_dense_pool+xenc"] = (
            time.perf_counter() - started + timings["fusion_dense_pool"]
        )

        out["cells"][content_type] = {
            arm: [
                {"id": i, "title": title_of(by_id[i])}
                for i in rankings[arm][:TOP_N]
            ]
            for arm in BLIND_ORDER.values()
        }
        for arm in BLIND_ORDER.values():
            out["timing"].append({
                "type": content_type, "arm": arm, "seconds": timings[arm]
            })
        log(f"  4 arms scored for {QUERY!r}")

    (EXP_DIR / "data").mkdir(exist_ok=True)
    (EXP_DIR / "data" / "lists.json").write_text(json.dumps(out, indent=1) + "\n")
    log("wrote data/lists.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
