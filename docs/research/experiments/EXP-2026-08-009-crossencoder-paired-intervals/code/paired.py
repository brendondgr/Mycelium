"""Paired bootstrap intervals over per-query nDCG@10, on both snapshots.

    IR_DATASETS_HOME=data/eval-cache/ir_datasets \
      uv run --project eval python .../code/paired.py

Every contrast in this record so far has been a difference of two means with no
statement about whether it would survive a different sample of queries. Twice that
has left a question unanswerable (`Q-011`, `Q-013`), and `Q-016` exists because it
was about to happen a third time to C-013.

The method is the standard one for IR and it is chosen because the alternative is
wrong here: arms are **paired** — every arm answers the same queries — so the unit
of resampling is the query, not the run. Resampling queries with replacement and
recomputing the mean per-query delta preserves that pairing; comparing two
independent samples would throw it away and inflate the interval.

Reported alongside the interval, deliberately:

* **win / loss / tie counts.** A mean delta carried by three queries and one earned
  across two hundred are different findings with identical means.
* **a two-sided sign test.** Distribution-free, and it answers "does this help more
  queries than it hurts" — which the decision rule in PROTOCOL.md requires
  separately from the mean.

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
SEED = 20260821  # fixed: an interval that moves between runs is not an interval
METRIC = "nDCG@10"

#: `(collection id, qrels variant, label -> config file)`. The config file names
#: the arm and its params; the run file is found by the config hash the harness
#: stamped, so a label can never silently resolve to a different setting.
SNAPSHOTS = [
    (
        "sci-2026-train",
        "dctr",
        {
            "bm25_only": "bm25_only_pooled.toml",
            "fusion_union_pool": "fusion_union_pool.toml",
            "xenc over fusion d50": "xenc_rerank_d50.toml",
            "xenc over fusion d100": "xenc_rerank_d100.toml",
            "xenc over bm25 d50": "xenc_rerank_bm25base_d50.toml",
            "xenc over bm25 d100": "xenc_rerank_bm25base_d100.toml",
        },
    ),
    (
        "sci-2025-01",
        "test",
        {
            "bm25_only": "bm25_only_pooled.toml",
            "fusion_union_pool": "fusion_union_pool.toml",
            "xenc over fusion d50": "xenc_rerank_d50.toml",
            "xenc over fusion d100": "xenc_rerank_d100.toml",
            "xenc over bm25 d50": "xenc_rerank_bm25base_d50.toml",
            "xenc over bm25 d100": "xenc_rerank_bm25base_d100.toml",
        },
    ),
]

#: The contrasts the protocol names, `(treatment, control)`.
CONTRASTS = [
    ("xenc over bm25 d50", "bm25_only"),
    ("xenc over bm25 d100", "bm25_only"),
    ("xenc over fusion d50", "bm25_only"),
    ("xenc over fusion d50", "fusion_union_pool"),
    ("xenc over fusion d100", "fusion_union_pool"),
    ("fusion_union_pool", "bm25_only"),
]


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
    """The run file for one config, located by the hash the harness stamped."""
    digest = config_hash(CONFIGS / config_file)
    prefix = snapshot.replace("/", "_")
    hits = sorted(
        RUNS.glob(f"{prefix}__*__{digest}__*.txt.gz"), key=lambda p: p.stat().st_mtime
    )
    return hits[-1] if hits else None


# The bootstrap and the sign test moved to `harness.stats` when
# `EXP-2026-08-010` needed them too — one implementation, so two experiments
# cannot compute subtly different intervals and then be compared. Verified
# behaviour-identical: this script's numbers are unchanged by the move.


def main() -> int:
    import django

    django.setup()
    from harness import datasets, scoring, stats

    out: dict = {}
    lines: list[str] = []

    for collection_id, variant, arms in SNAPSHOTS:
        collection = datasets.load_collections()[collection_id]
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
            scores = scoring.score_per_topic(
                read_run(path), dict(qrels), measures=[METRIC]
            )
            per_arm[label] = {q: v[METRIC] for q, v in scores.items() if METRIC in v}

        n_q = len(next(iter(per_arm.values()))) if per_arm else 0
        header = f"## `{collection.snapshot}` — qrels `{variant}`, {n_q} queries"
        lines += [header, ""]
        if missing:
            lines += [f"*Not yet run: {', '.join(missing)}*", ""]

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
            result = stats.paired_bootstrap(
                deltas, resamples=RESAMPLES, seed=SEED
            )
            mean, lo, hi = result.mean, result.ci_low, result.ci_high
            wins, losses, ties = result.wins, result.losses, result.ties
            p = result.sign_p
            excludes = "**yes**" if result.excludes_zero else "no"
            lines.append(
                f"| {treat} − {control} | {mean:+.4f} | "
                f"[{lo:+.4f}, {hi:+.4f}] | {excludes} | "
                f"{wins}/{losses}/{ties} | {p:.3g} |"
            )
            # Stratify by query length. A cross-encoder is trained on
            # natural-language questions; a one-word keyword query gives it almost
            # nothing to read, while BM25's rare-term exact match is at its best
            # there. If that is the mechanism, the per-query delta should improve
            # with query length — so the analysis tests it rather than asserting it.
            strata: dict[str, list[float]] = defaultdict(list)
            for q, d in zip(shared, deltas, strict=True):
                n_words = query_len.get(q, 0)
                strata[stats.length_bucket(n_words)].append(d)
            by_len = {
                k: {"n": len(v), "mean_delta": sum(v) / len(v)}
                for k, v in sorted(strata.items())
            }
            rows.append({
                "treatment": treat, "control": control, "n": len(deltas),
                "by_query_length": by_len,
                "mean_delta": mean, "ci_low": lo, "ci_high": hi,
                "excludes_zero": lo > 0 or hi < 0,
                "wins": wins, "losses": losses, "ties": ties, "sign_p": p,
            })
        lines.append("")

        # The stratification, for the decisive contrast only — it is a diagnostic
        # of one result, not a table to repeat six times.
        focus = next(
            (r for r in rows
             if r["treatment"] == "xenc over bm25 d100" and r["control"] == "bm25_only"),
            None,
        )
        if focus:
            lines += [
                (
                    f"Per-query Δ for `{focus['treatment']}` − "
                    f"`{focus['control']}`, split by query length:"
                ),
                "",
                "| query length | queries | mean Δ nDCG@10 |",
                "|---|---:|---:|",
            ]
            order = list(stats.BUCKET_ORDER)
            for bucket in order:
                if bucket in focus["by_query_length"]:
                    cell = focus["by_query_length"][bucket]
                    lines.append(
                        f"| {bucket} | {cell['n']} | {cell['mean_delta']:+.4f} |"
                    )
            lines.append("")

        out[collection_id] = {
            "snapshot": collection.snapshot, "qrels": variant, "n_queries": n_q,
            "absolute": {k: sum(v.values()) / len(v) for k, v in per_arm.items()},
            "contrasts": rows, "missing_arms": missing,
        }

    body = "\n".join(
        [(
            f"*{RESAMPLES:,} paired bootstrap resamples over query ids, seed "
            f"{SEED}. Ties are exact per-query equality; the sign test excludes "
            "them.*"
        ), ""]
        + lines
    )
    (EXP_DIR / "tables").mkdir(exist_ok=True)
    (EXP_DIR / "data").mkdir(exist_ok=True)
    (EXP_DIR / "tables" / "paired.md").write_text(body + "\n")
    (EXP_DIR / "data" / "paired.json").write_text(
        json.dumps(out, indent=2, sort_keys=True) + "\n"
    )
    print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
