"""Ten retrieval arms, four corpora, three queries — the lists themselves.

    docker compose up -d postgres
    uv run --project eval python .../code/encode_splade.py   # one-time
    uv run --project eval python .../code/run.py

`EXP-2026-08-014` produces ranked lists for a human to judge; it computes no
verdict (see `PROTOCOL.md`). This script runs the arms, records what they
returned and how long they took, and writes `data/lists.json` for
`code/build_pdf.py` to typeset. Nothing here decides anything.

The pool builders are imported from `EXP-2026-08-013` rather than reimplemented:
two implementations of "union pool" is two chances to build subtly different
pools and then compare them as if they were the same.

No LLM. No network.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = EXP_DIR.parents[3]
PRIOR = EXP_DIR.parent / "EXP-2026-08-013-production-pool-contrast" / "code"
sys.path.insert(0, str(REPO_ROOT / "eval"))
sys.path.insert(0, str(REPO_ROOT / "web" / "backend"))
sys.path.insert(0, str(PRIOR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ["DATABASE_URL"] = os.environ.get(
    "MYCELIUM_DATABASE_URL", "postgres://mycelium:mycelium@127.0.0.1:11450/mycelium"
)
os.environ.setdefault(
    "FASTEMBED_CACHE_PATH", str(REPO_ROOT / "data" / "eval-cache" / "fastembed")
)
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

QUERIES = [
    "AI agents in healthcare",
    "AI agents in medicine",
    "agentic AI for clinical decision support",
]
TYPES = ["paper", "grant", "conference", "fellowship"]
POOL_PER_INTEREST = 100
RERANK_DEPTH = 50
TOP_N = 10
CROSS_ENCODER = "Xenova/ms-marco-MiniLM-L-6-v2"
SNAPSHOT = "mycelium-store-2026-08-22"

BASE_ARMS = [
    "bm25_only",
    "dense_only",
    "fusion_dense_pool",
    "fusion_union_pool",
    "fusion_union_splade",
]
ARM_KEYS = [a for arm in BASE_ARMS for a in (arm, f"{arm}+xenc")]

#: Blinded presentation order, fixed here and recorded in the PDF's key page.
#: Deliberately NOT alphabetical and not grouped by base arm, so a reader cannot
#: infer which list is production's from where it sits on the page.
BLIND_ORDER = [
    "fusion_union_pool",
    "bm25_only+xenc",
    "fusion_dense_pool",
    "dense_only",
    "fusion_union_splade+xenc",
    "bm25_only",
    "fusion_dense_pool+xenc",
    "fusion_union_splade",
    "dense_only+xenc",
    "fusion_union_pool+xenc",
]
BLIND_LABELS = dict(zip("ABCDEFGHIJ", BLIND_ORDER, strict=True))


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def display(item) -> dict:
    """Title, source and a short snippet — what a reader will actually judge on."""
    meta = item.metadata or {}
    title = meta.get("title") or meta.get("name") or "(untitled)"
    body = meta.get("abstract") or meta.get("search_text") or meta.get("summary") or ""
    snippet = " ".join(str(body).split())[:220]
    return {
        "id": str(item.id),
        "title": " ".join(str(title).split()),
        "source": item.source,
        "url": item.source_url,
        "snippet": snippet,
        "deadline": meta.get("deadline") or meta.get("close_date") or "",
    }


def sorted_ids(scores: dict[str, float]) -> list[str]:
    """Best first, ties broken by id so a run is reproducible.

    `EXP-2026-08-003` ISSUES recorded the trap this avoids: a tie order that
    depends on set iteration is not a ranking, it is a hash.
    """
    return [k for k, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))]


def splade_encode_seconds() -> dict[str, float]:
    """Recover the one-time SPLADE encode cost from the encoder's own log."""
    path = EXP_DIR / "logs" / "splade.log"
    if not path.exists():
        return {}
    pattern = re.compile(r"^=== (\w+): \(.*?(\d+)s ===$", re.MULTILINE)
    return {m.group(1): float(m.group(2)) for m in pattern.finditer(path.read_text())}


def main() -> int:
    import django

    django.setup()

    import numpy as np
    import production_pool as pp
    from apps.content import embeddings
    from apps.content.interests_query import SearchInterest
    from apps.content.lexical import build_bm25_index, rank_bm25_over
    from apps.content.models import ContentItem
    from apps.content.retrieval import PgVectorIndex
    from fastembed.rerank.cross_encoder import TextCrossEncoder
    from harness import neural

    log(f"loading cross-encoder {CROSS_ENCODER} …")
    started = time.perf_counter()
    encoder = TextCrossEncoder(model_name=CROSS_ENCODER)
    model_load = time.perf_counter() - started
    log(f"  loaded in {model_load:.1f}s")

    out: dict = {
        "queries": QUERIES,
        "types": TYPES,
        "blind_labels": BLIND_LABELS,
        "pool_per_interest": POOL_PER_INTEREST,
        "rerank_depth": RERANK_DEPTH,
        "cells": {},
        "timing": [],
        "index_cost": [],
        "corpus_sizes": {},
    }
    encode_seconds = splade_encode_seconds()

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

        started = time.perf_counter()
        corpus_bm25 = build_bm25_index(docs)
        bm25_build = time.perf_counter() - started
        log(f"  BM25 index built in {bm25_build:.1f}s")

        started = time.perf_counter()
        splade_matrix = neural.splade_encode(
            [type("D", (), {"id": d.id, "text": _text(d)})() for d in docs],
            snapshot=SNAPSHOT,
            scope=content_type,
            log=lambda m: None,
        )
        splade_load = time.perf_counter() - started
        splade_model = neural._splade_model()
        width = splade_matrix.shape[1]
        log(f"  SPLADE matrix loaded in {splade_load:.1f}s ({splade_matrix.nnz:,} nnz)")

        out["index_cost"] += [
            {"type": content_type, "stage": "bm25_index_build", "seconds": bm25_build},
            {"type": content_type, "stage": "splade_matrix_load", "seconds": splade_load},
            {
                "type": content_type,
                "stage": "splade_encode_one_time",
                "seconds": encode_seconds.get(content_type, float("nan")),
            },
        ]

        index = PgVectorIndex(content_type=content_type, created_on=None)

        for query in QUERIES:
            interest = SearchInterest(label=query, query_text=query, embed_text=query)
            rankings: dict[str, list[str]] = {}
            timings: dict[str, float] = {}

            # --- bm25_only
            started = time.perf_counter()
            hits = rank_bm25_over(query, corpus_bm25)
            rankings["bm25_only"] = [str(d.id) for d, _ in hits[:RERANK_DEPTH]]
            timings["bm25_only"] = time.perf_counter() - started

            # --- dense_only
            started = time.perf_counter()
            vector = embeddings.embed_text(query)
            dense_hits = index.search(vector, limit=RERANK_DEPTH)
            rankings["dense_only"] = [str(d.id) for d, _ in dense_hits]
            timings["dense_only"] = time.perf_counter() - started

            # --- fusion_dense_pool (production as deployed)
            started = time.perf_counter()
            _pool, per_interest, _cos = pp.dense_pool(
                [interest], index=index, pool_per_interest=POOL_PER_INTEREST
            )
            rankings["fusion_dense_pool"] = sorted_ids(per_interest.get(query, {}))[
                :RERANK_DEPTH
            ]
            timings["fusion_dense_pool"] = time.perf_counter() - started

            # --- fusion_union_pool
            started = time.perf_counter()

            def lexical_topk(text: str, limit: int, _idx=corpus_bm25):
                return rank_bm25_over(text, _idx)[:limit]

            _pool, per_interest_u, _cos = pp.union_pool_prod(
                [interest],
                index=index,
                pool_per_interest=POOL_PER_INTEREST,
                lexical_topk=lexical_topk,
                embed=embeddings.embed_text,
            )
            rankings["fusion_union_pool"] = sorted_ids(per_interest_u.get(query, {}))[
                :RERANK_DEPTH
            ]
            timings["fusion_union_pool"] = time.perf_counter() - started

            # --- fusion_union_splade (three channels, RRF)
            started = time.perf_counter()
            qvec = neural.splade_query_vector(splade_model, query, width)
            scores = np.asarray((splade_matrix @ qvec.T).todense()).ravel()
            cut = min(POOL_PER_INTEREST, len(scores) - 1)
            top = np.argpartition(-scores, cut)[:POOL_PER_INTEREST]
            top = top[np.argsort(-scores[top], kind="stable")]
            splade_channel = [doc_ids[j] for j in top if scores[j] > 0]
            lexical_channel = [
                str(d.id) for d, _ in rank_bm25_over(query, corpus_bm25)[:POOL_PER_INTEREST]
            ]
            dense_channel = [
                str(d.id) for d, _ in index.search(vector, limit=POOL_PER_INTEREST)
            ]
            rankings["fusion_union_splade"] = rrf_fuse(
                [lexical_channel, dense_channel, splade_channel]
            )[:RERANK_DEPTH]
            timings["fusion_union_splade"] = time.perf_counter() - started

            # --- cross-encoder variants
            for arm in BASE_ARMS:
                ids = rankings[arm]
                started = time.perf_counter()
                if ids:
                    texts = [_text(by_id[i]) for i in ids]
                    xscores = list(encoder.rerank(query, texts))
                    order = sorted(
                        range(len(ids)), key=lambda j: (-xscores[j], ids[j])
                    )
                    rankings[f"{arm}+xenc"] = [ids[j] for j in order]
                else:
                    rankings[f"{arm}+xenc"] = []
                timings[f"{arm}+xenc"] = time.perf_counter() - started

            cell_key = f"{content_type}|{query}"
            out["cells"][cell_key] = {
                arm: [display(by_id[i]) for i in rankings[arm][:TOP_N]]
                for arm in ARM_KEYS
            }
            for arm in ARM_KEYS:
                out["timing"].append({
                    "type": content_type,
                    "query": query,
                    "arm": arm,
                    "seconds": timings[arm],
                    "pairs_scored": len(rankings[arm.removesuffix("+xenc")])
                    if arm.endswith("+xenc")
                    else 0,
                })
            log(f"  {query!r}: 10 arms scored")

    out["cross_encoder_load_seconds"] = model_load
    (EXP_DIR / "data").mkdir(exist_ok=True)
    (EXP_DIR / "data" / "lists.json").write_text(json.dumps(out, indent=1) + "\n")
    log(f"wrote {len(out['cells'])} cells to data/lists.json")
    return 0


def _text(item) -> str:
    from apps.content.lexical import _item_text

    return _item_text(item)


def rrf_fuse(channels, *, k: int = 60) -> list[str]:
    """RRF over any number of ranked id lists — `eval/harness/ladder.py`'s."""
    scores: dict[str, float] = {}
    for channel in channels:
        for rank, doc_id in enumerate(channel, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return [doc_id for doc_id, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))]


if __name__ == "__main__":
    raise SystemExit(main())
