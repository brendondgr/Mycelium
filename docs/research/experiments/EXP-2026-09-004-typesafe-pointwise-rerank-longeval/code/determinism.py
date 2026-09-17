"""Determinism check, before any arm: 20 (query, document) pairs asked three times.

    IR_DATASETS_HOME=data/eval-cache/ir_datasets \
      uv run --project eval python .../code/determinism.py

Loads the pooled corpus exactly as `eval/run.py` does for the `typesafe_noul`
config, takes BM25's top document for each of the first 20 queries, and asks the
arm's own question of each pair three times through the arm's own client. The
maximum absolute difference in `noul` is the number PROTOCOL.md gates on.

Writes `data/determinism.json`.
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import tomllib
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = EXP_DIR.parents[3]
sys.path.insert(0, str(REPO_ROOT / "eval"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from harness import datasets, ladder
from harness import typesafe_rerank as ts

import run

COLLECTION = "sci-2026-train"
PAIRS = 20
REPEATS = 3
CONFIG = REPO_ROOT / "eval" / "configs" / "typesafe_noul_bm25.toml"


def main() -> int:
    config = tomllib.loads(CONFIG.read_text())
    model = ts._pinned_model(config["params"])
    collection = datasets.load_collections()[COLLECTION]
    dataset = datasets.load_dataset(collection, collection.default_qrels)
    queries = datasets.queries(dataset)
    docs, _scope, _index = run.load_corpus(
        collection, dataset, config, queries, None, needs_vectors=False
    )
    base = ladder.base_ranking(
        "bm25_only", queries, docs, index=None,
        pool_per_interest=int(config["params"].get("pool_per_interest", 100)),
        log=run.log, collection=collection,
    )
    by_id = ladder._docs_by_id(docs)
    pairs = []
    for query_id, query_text in queries:
        top = [d for d, _ in base.get(query_id, []) if d in by_id]
        if top:
            pairs.append((query_id, query_text, top[0]))
        if len(pairs) >= PAIRS:
            break

    client = ts._client("eval-typesafe-determinism")
    rows, tokens = [], 0
    for query_id, query_text, doc_id in pairs:
        values = []
        for _ in range(REPEATS):
            result = client.ask(
                ts._state(query_text, by_id[doc_id]),
                {"relevance": ts.noul_question()},
                model=model,
            )
            values.append(float(result.answers["relevance"].noul))
            tokens += result.usage["input_tokens"]
        rows.append({
            "query_id": query_id, "doc_id": doc_id, "values": values,
            "spread": max(values) - min(values),
        })
    spreads = [r["spread"] for r in rows]
    out = {
        "model": model, "pairs": len(rows), "repeats": REPEATS,
        "max_abs_diff_noul": max(spreads), "mean_abs_diff_noul": statistics.fmean(spreads),
        "pairs_moved_more_than_0_05": sum(1 for s in spreads if s > 0.05),
        "input_tokens": tokens, "rows": rows,
    }
    (EXP_DIR / "data").mkdir(exist_ok=True)
    (EXP_DIR / "data" / "determinism.json").write_text(json.dumps(out, indent=1))
    run.log(
        f"determinism: max |Δnoul| = {out['max_abs_diff_noul']:.3f}, "
        f"mean {out['mean_abs_diff_noul']:.3f}, {tokens} input tokens"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
