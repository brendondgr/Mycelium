"""Does prose length recover the cross-encoder's short-query loss?

    IR_DATASETS_HOME=data/eval-cache/ir_datasets \
      uv run --project eval python .../code/analyse.py

Every arm retrieves identically — `bm25_only` over the original short query — and
reranks the same top 50 with the same cross-encoder. The **only** thing that
differs is the text the reranker is asked to score against: the raw query, or
~8/16/20/40 words of LLM-written prose describing it. So a difference between arms
is attributable to that text and nothing else.

Two outputs, and the second is the one the hypothesis is actually about:

1. Δ nDCG@10 against `bm25_only` per arm, with a paired bootstrap interval and a
   sign test (`harness.stats`, shared with `EXP-2026-08-009`).
2. The same Δ **split by the length of the original query**, because the
   prediction is specifically that expansion rescues the short queries that were
   being hurt — and may cost the long ones that were already fine.

Writes `tables/expansion.md` and `data/expansion.json`.
"""

from __future__ import annotations

import gzip
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = EXP_DIR.parents[3]
sys.path.insert(0, str(REPO_ROOT / "eval"))
sys.path.insert(0, str(REPO_ROOT / "web" / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

RUNS = REPO_ROOT / "eval" / "runs"
CONFIGS = REPO_ROOT / "eval" / "configs"
COLLECTION = "sci-2025-01"
QRELS = "test"
METRIC = "nDCG@10"

#: `label -> config file`, in the order the table should read. The baseline and
#: the raw-query arm come from `EXP-2026-08-009`; the rest are this experiment.
ARMS = {
    "bm25_only (baseline)": "bm25_only_pooled.toml",
    "xenc, raw query": "xenc_rerank_bm25base_d50.toml",
    "xenc, ~8w prose": "xenc_bm25base_expand8w_d50.toml",
    "xenc, ~16w prose": "xenc_bm25base_expand16w_d50.toml",
    "xenc, ~20w prose": "xenc_bm25base_expand20w_d50.toml",
    "xenc, ~40w prose": "xenc_bm25base_expand40w_d50.toml",
}
BASELINE = "bm25_only (baseline)"


def config_hash(path: Path) -> str:
    import hashlib
    import tomllib

    return hashlib.sha256(
        json.dumps(tomllib.loads(path.read_text()), sort_keys=True).encode()
    ).hexdigest()[:16]


def read_run(path: Path) -> dict[str, list[tuple[str, float]]]:
    ranking: dict[str, list[tuple[str, float]]] = defaultdict(list)
    with gzip.open(path, "rt") as handle:
        for line in handle:
            parts = line.split()
            if len(parts) >= 5:
                ranking[parts[0]].append((parts[2], float(parts[4])))
    return dict(ranking)


def find_run(snapshot: str, config_file: str) -> Path | None:
    digest = config_hash(CONFIGS / config_file)
    prefix = snapshot.replace("/", "_")
    hits = sorted(
        RUNS.glob(f"{prefix}__*__{digest}__*.txt.gz"), key=lambda p: p.stat().st_mtime
    )
    return hits[-1] if hits else None


def main() -> int:
    import django

    django.setup()
    from harness import datasets, scoring, stats

    collection = datasets.load_collections()[COLLECTION]
    dataset = datasets.load_dataset(collection, QRELS)
    query_len = {qid: len(text.split()) for qid, text in datasets.queries(dataset)}
    qrels: dict[str, dict[str, int]] = defaultdict(dict)
    for q in dataset.qrels_iter():
        qrels[q.query_id][q.doc_id] = int(q.relevance)

    per_arm: dict[str, dict[str, float]] = {}
    missing: list[str] = []
    for label, config_file in ARMS.items():
        path = find_run(collection.snapshot, config_file)
        if path is None:
            missing.append(label)
            continue
        scores = scoring.score_per_topic(read_run(path), dict(qrels), measures=[METRIC])
        per_arm[label] = {q: v[METRIC] for q, v in scores.items() if METRIC in v}

    if BASELINE not in per_arm:
        raise SystemExit(f"baseline {BASELINE!r} has no run file; cannot contrast")

    base = per_arm[BASELINE]
    out: dict = {"missing_arms": missing, "n_queries": len(base), "arms": {}}

    lines = [
        (
            f"*Snapshot `{collection.snapshot}`, qrels `{QRELS}`, {len(base)} "
            "queries. Every arm retrieves with `bm25_only` over the **original** "
            "query and reranks the same top 50; only the reranker's input text "
            f"differs. {stats.DEFAULT_RESAMPLES:,} paired bootstrap resamples, "
            f"seed {stats.DEFAULT_SEED}.*"
        ),
        "",
        "### Overall",
        "",
        f"| Arm | {METRIC} | Δ vs BM25 | 95% CI | excludes 0 | win/loss/tie | sign p |",
        "|---|---:|---:|---|:--:|---|---:|",
    ]
    if missing:
        lines.insert(2, f"*Not yet run: {', '.join(missing)}*\n")

    absolute = {k: sum(v.values()) / len(v) for k, v in per_arm.items()}
    lines.append(
        f"| {BASELINE} | {absolute[BASELINE]:.4f} | — | — | — | — | — |"
    )

    by_bucket: dict[str, dict[str, float]] = {}
    for label in ARMS:
        if label == BASELINE or label not in per_arm:
            continue
        shared = sorted(set(per_arm[label]) & set(base))
        deltas = [per_arm[label][q] - base[q] for q in shared]
        result = stats.paired_bootstrap(deltas)
        lines.append(
            f"| {label} | {absolute[label]:.4f} | {result.mean:+.4f} | "
            f"[{result.ci_low:+.4f}, {result.ci_high:+.4f}] | "
            f"{'**yes**' if result.excludes_zero else 'no'} | "
            f"{result.wins}/{result.losses}/{result.ties} | {result.sign_p:.3g} |"
        )
        strata: dict[str, list[float]] = defaultdict(list)
        for q, d in zip(shared, deltas, strict=True):
            strata[stats.length_bucket(query_len.get(q, 0))].append(d)
        by_bucket[label] = {
            b: sum(v) / len(v) for b, v in strata.items()
        }
        out["arms"][label] = {
            "absolute": absolute[label],
            **result.as_dict(),
            "by_query_length": {
                b: {"n": len(v), "mean_delta": sum(v) / len(v)}
                for b, v in sorted(strata.items())
            },
        }

    counts = defaultdict(int)
    for q in base:
        counts[stats.length_bucket(query_len.get(q, 0))] += 1

    lines += [
        "",
        "### Δ vs BM25, split by the length of the **original** query",
        "",
        "| Arm | " + " | ".join(
            f"{b} (n={counts[b]})" for b in stats.BUCKET_ORDER if counts[b]
        ) + " |",
        "|---|" + "---:|" * sum(1 for b in stats.BUCKET_ORDER if counts[b]),
    ]
    for label, buckets in by_bucket.items():
        cells = [
            f"{buckets.get(b, float('nan')):+.4f}"
            for b in stats.BUCKET_ORDER if counts[b]
        ]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")

    body = "\n".join(lines)
    (EXP_DIR / "tables").mkdir(exist_ok=True)
    (EXP_DIR / "data").mkdir(exist_ok=True)
    (EXP_DIR / "tables" / "expansion.md").write_text(body + "\n")
    (EXP_DIR / "data" / "expansion.json").write_text(
        json.dumps(out, indent=2, sort_keys=True) + "\n"
    )
    print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
