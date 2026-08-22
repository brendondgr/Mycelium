"""Do the recall claims survive a paired interval? (`Q-022`)

    IR_DATASETS_HOME=data/eval-cache/ir_datasets \
      uv run --project eval python .../code/recall.py

After `EXP-2026-08-009` and `EXP-2026-08-010`, C-008 and C-014 are the only
positive findings left in the ladder and neither has ever had an interval. This
computes them with the same `harness.stats` bootstrap the two refutations used, so
the surviving claims are held to the bar that killed the others rather than a
lower one.

Also reported: the same contrasts on nDCG@100. Recall that never surfaces in a
ranking is worth little, so a recall gain that moves the deeper ranking metric is
a stronger finding than one that does not.

Writes `tables/recall.md` and `data/recall.json`.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import sys
import tomllib
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
SNAPSHOT = "longeval-sci-2026/snapshot-1/train"
MEASURES = ["R@100", "nDCG@100", "nDCG@10"]

ARMS = {
    "dense_only": "dense_only.toml",
    "fusion_dense_pool": "fusion_dense_pool.toml",
    "fusion_union_pool": "fusion_union_pool.toml",
    "fusion_bm25_dense_splade": "fusion_bm25_dense_splade.toml",
    "bm25_only": "bm25_only_pooled.toml",
}

#: `(treatment, control, which claim it tests)`.
CONTRASTS = [
    ("fusion_union_pool", "fusion_dense_pool", "C-008"),
    ("fusion_bm25_dense_splade", "fusion_union_pool", "C-014"),
    ("fusion_bm25_dense_splade", "bm25_only", "—"),
    ("fusion_union_pool", "bm25_only", "—"),
]

#: The values these arms must reproduce, from the committed leaderboard. A
#: comparison built on an arm that has silently changed is not about what it says.
EXPECTED_R100 = {
    "dense_only": 0.6120,
    "fusion_dense_pool": 0.5988,
    "fusion_union_pool": 0.6511,
    "fusion_bm25_dense_splade": 0.7141,
    "bm25_only": 0.6903,
}


def config_hash(name: str) -> str:
    return hashlib.sha256(
        json.dumps(tomllib.loads((CONFIGS / name).read_text()), sort_keys=True).encode()
    ).hexdigest()[:16]


def read_run(name: str) -> dict[str, list[tuple[str, float]]] | None:
    digest = config_hash(name)
    prefix = SNAPSHOT.replace("/", "_")
    hits = sorted(
        RUNS.glob(f"{prefix}__*__{digest}__*.txt.gz"), key=lambda p: p.stat().st_mtime
    )
    if not hits:
        return None
    ranking: dict[str, list[tuple[str, float]]] = defaultdict(list)
    with gzip.open(hits[-1], "rt") as handle:
        for line in handle:
            parts = line.split()
            if len(parts) >= 5:
                ranking[parts[0]].append((parts[2], float(parts[4])))
    return dict(ranking)


def main() -> int:
    import django

    django.setup()
    from harness import datasets, scoring, stats

    collection = datasets.load_collections()["sci-2026-train"]
    dataset = datasets.load_dataset(collection, "dctr")
    qrels: dict[str, dict[str, int]] = defaultdict(dict)
    for q in dataset.qrels_iter():
        qrels[q.query_id][q.doc_id] = int(q.relevance)

    per_arm: dict[str, dict[str, dict[str, float]]] = {}
    missing = []
    for label, config_file in ARMS.items():
        run = read_run(config_file)
        if run is None:
            missing.append(label)
            continue
        per_arm[label] = scoring.score_per_topic(run, dict(qrels), measures=MEASURES)

    # Gate: every arm must reproduce its recorded R@100 before any contrast is read.
    gate = []
    for label, scores in per_arm.items():
        got = sum(s["R@100"] for s in scores.values()) / len(scores)
        want = EXPECTED_R100[label]
        ok = abs(got - want) < 5e-4
        gate.append((label, got, want, ok))
    failed = [g for g in gate if not g[3]]

    lines = [
        (
            f"*Snapshot `{collection.snapshot}`, qrels `dctr`, pooled scope. "
            f"{stats.DEFAULT_RESAMPLES:,} paired bootstrap resamples over query "
            f"ids, seed {stats.DEFAULT_SEED}. R@100 here is recall **within the "
            "pooled subset** — a re-ranking evaluation, not a claim about a full "
            "corpus.*"
        ),
        "",
        "### Reproduction gate",
        "",
        "| Arm | R@100 now | R@100 recorded | matches |",
        "|---|---:|---:|:--:|",
    ]
    for label, got, want, ok in gate:
        lines.append(
            f"| {label} | {got:.4f} | {want:.4f} | {'yes' if ok else '**NO**'} |"
        )
    if missing:
        lines += ["", f"*No run file for: {', '.join(missing)}*"]
    if failed:
        lines += ["", "**Gate failed — contrasts below are not trustworthy.**"]

    out: dict = {"gate": [
        {"arm": g[0], "r100": g[1], "expected": g[2], "ok": g[3]} for g in gate
    ], "contrasts": []}

    for metric in ("R@100", "nDCG@100", "nDCG@10"):
        lines += [
            "",
            f"### {metric}",
            "",
            "| Contrast | claim | mean Δ | 95% CI | excludes 0 | win/loss/tie | sign p |",
            "|---|:--:|---:|---|:--:|---|---:|",
        ]
        for treat, control, claim in CONTRASTS:
            if treat not in per_arm or control not in per_arm:
                continue
            shared = sorted(set(per_arm[treat]) & set(per_arm[control]))
            deltas = [
                per_arm[treat][q][metric] - per_arm[control][q][metric] for q in shared
            ]
            result = stats.paired_bootstrap(deltas)
            lines.append(
                f"| {treat} − {control} | {claim} | {result.mean:+.4f} | "
                f"[{result.ci_low:+.4f}, {result.ci_high:+.4f}] | "
                f"{'**yes**' if result.excludes_zero else 'no'} | "
                f"{result.wins}/{result.losses}/{result.ties} | {result.sign_p:.3g} |"
            )
            out["contrasts"].append(
                {"metric": metric, "treatment": treat, "control": control,
                 "claim": claim, **result.as_dict()}
            )

    body = "\n".join(lines)
    (EXP_DIR / "tables").mkdir(exist_ok=True)
    (EXP_DIR / "data").mkdir(exist_ok=True)
    (EXP_DIR / "tables" / "recall.md").write_text(body + "\n")
    (EXP_DIR / "data" / "recall.json").write_text(
        json.dumps(out, indent=2, sort_keys=True) + "\n"
    )
    print(body)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
