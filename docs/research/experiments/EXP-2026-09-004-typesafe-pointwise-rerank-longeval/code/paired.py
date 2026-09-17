"""Paired bootstrap intervals over per-query nDCG@10 for the TypeSafe arms.

    IR_DATASETS_HOME=data/eval-cache/ir_datasets \
      uv run --project eval python .../code/paired.py

Adapted from `EXP-2026-08-009/code/paired.py`: same resampling unit (the query),
same `harness.stats` implementation, same seed, so an interval here is
comparable to every interval before it. Run files are located by the config
hash the harness stamped, so a label can never resolve to a different setting.

Writes `tables/paired.md` and `data/paired.json`.
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
RESAMPLES = 10_000
SEED = 20260821  # fixed, as in every prior interval in this record
METRIC = "nDCG@10"

SNAPSHOTS = [
    (
        "sci-2026-train",
        "dctr",
        {
            "bm25_only": "bm25_only_pooled.toml",
            "typesafe_noul over bm25": "typesafe_noul_bm25.toml",
            "typesafe_score over bm25": "typesafe_score_bm25.toml",
            "typesafe_noul over fusion": "typesafe_noul_fusion.toml",
            "fusion_union_pool": "fusion_union_pool.toml",
        },
    ),
    (
        "sci-2025-01",
        "test",
        {
            "bm25_only": "bm25_only_pooled.toml",
            "typesafe_noul over bm25": "typesafe_noul_bm25.toml",
            "typesafe_score over bm25": "typesafe_score_bm25.toml",
        },
    ),
]

#: `(treatment, control)`. The first is the protocol's primary contrast.
CONTRASTS = [
    ("typesafe_noul over bm25", "bm25_only"),
    ("typesafe_score over bm25", "bm25_only"),
    ("typesafe_noul over bm25", "typesafe_score over bm25"),
    ("typesafe_noul over fusion", "fusion_union_pool"),
    ("typesafe_noul over fusion", "bm25_only"),
]
FOCUS = ("typesafe_noul over bm25", "bm25_only")


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

    out: dict = {}
    lines: list[str] = []
    for collection_id, variant, arms in SNAPSHOTS:
        collection = datasets.load_collections()[collection_id]
        if not any(find_run(collection.snapshot, f) for f in arms.values()):
            continue  # snapshot never run on this host; nothing to pair
        dataset = datasets.load_dataset(collection, variant)
        query_len = {qid: len(text.split()) for qid, text in datasets.queries(dataset)}
        qrels: dict[str, dict[str, int]] = defaultdict(dict)
        for q in dataset.qrels_iter():
            qrels[q.query_id][q.doc_id] = int(q.relevance)

        per_arm: dict[str, dict[str, float]] = {}
        missing: list[str] = []
        for label, config_file in arms.items():
            path = find_run(collection.snapshot, config_file)
            if path is None:
                missing.append(label)
                continue
            scores = scoring.score_per_topic(read_run(path), dict(qrels), measures=[METRIC])
            per_arm[label] = {q: v[METRIC] for q, v in scores.items() if METRIC in v}

        n_q = len(next(iter(per_arm.values()))) if per_arm else 0
        lines += [f"## `{collection.snapshot}` — qrels `{variant}`, {n_q} queries", ""]
        if missing:
            lines += [f"*Not run: {', '.join(missing)}*", ""]
        lines += [
            f"| Contrast | mean Δ {METRIC} | 95% CI | excludes 0 | win/loss/tie | sign p |",
            "|---|---:|---|:--:|---|---:|",
        ]
        rows = []
        for treat, control in CONTRASTS:
            if treat not in per_arm or control not in per_arm:
                continue
            shared = sorted(set(per_arm[treat]) & set(per_arm[control]))
            deltas = [per_arm[treat][q] - per_arm[control][q] for q in shared]
            if not deltas:
                continue
            result = stats.paired_bootstrap(deltas, resamples=RESAMPLES, seed=SEED)
            excludes = "**yes**" if result.excludes_zero else "no"
            lines.append(
                f"| {treat} − {control} | {result.mean:+.4f} | "
                f"[{result.ci_low:+.4f}, {result.ci_high:+.4f}] | {excludes} | "
                f"{result.wins}/{result.losses}/{result.ties} | {result.sign_p:.3g} |"
            )
            strata: dict[str, list[float]] = defaultdict(list)
            for q, d in zip(shared, deltas, strict=True):
                strata[stats.length_bucket(query_len.get(q, 0))].append(d)
            rows.append({
                "treatment": treat, "control": control, "n": len(deltas),
                "mean_delta": result.mean, "ci_low": result.ci_low,
                "ci_high": result.ci_high, "excludes_zero": result.excludes_zero,
                "wins": result.wins, "losses": result.losses, "ties": result.ties,
                "sign_p": result.sign_p,
                "by_query_length": {
                    k: {"n": len(v), "mean_delta": sum(v) / len(v)}
                    for k, v in sorted(strata.items())
                },
            })
        lines.append("")
        focus = next(
            (r for r in rows if (r["treatment"], r["control"]) == FOCUS), None
        )
        if focus:
            lines += [
                f"Per-query Δ for `{FOCUS[0]}` − `{FOCUS[1]}`, split by query length:",
                "",
                "| query length | queries | mean Δ nDCG@10 |",
                "|---|---:|---:|",
            ]
            for bucket in stats.BUCKET_ORDER:
                if bucket in focus["by_query_length"]:
                    cell = focus["by_query_length"][bucket]
                    lines.append(f"| {bucket} | {cell['n']} | {cell['mean_delta']:+.4f} |")
            lines.append("")
        out[collection_id] = {
            "snapshot": collection.snapshot, "qrels": variant, "n_queries": n_q,
            "absolute": {k: sum(v.values()) / len(v) for k, v in per_arm.items()},
            "contrasts": rows, "missing_arms": missing,
        }

    body = "\n".join(
        [
            (
                f"*{RESAMPLES:,} paired bootstrap resamples over query ids, seed {SEED}. "
                "Ties are exact per-query equality; the sign test excludes them. "
                "Qrels are click-derived on sci-2026-train, not human assessment.*"
            ),
            "",
        ]
        + lines
    )
    (EXP_DIR / "tables").mkdir(exist_ok=True)
    (EXP_DIR / "data").mkdir(exist_ok=True)
    (EXP_DIR / "tables" / "paired.md").write_text(body + "\n")
    (EXP_DIR / "data" / "paired.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
