"""Do C-008, C-014 and C-018 replicate on a second snapshot? (`Q-024`)

    IR_DATASETS_HOME=data/eval-cache/ir_datasets \
      uv run --project eval python .../code/replicate.py

`EXP-2026-08-011` established the ladder's only surviving positive findings, all
on `sci-2026-train` with click-derived judgments. This recomputes the identical
contrasts on `sci-2025-01` — 492 queries, released human assessments — and prints
the two snapshots **side by side**, because a replication is a statement about
agreement and is unreadable when the two halves live in different files.

`EXP-2026-08-009` already watched an effect flip sign between these snapshots, so
the columns are deliberately arranged to make a disagreement obvious rather than
something a reader has to derive.

Uses `harness.stats` — the same bootstrap as every interval since
`EXP-2026-08-009`. No LLM, no network.

Writes `tables/replication.md` and `data/replication.json`.
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
MEASURES = ["R@100", "nDCG@100", "nDCG@10"]

SNAPSHOTS = [
    ("sci-2026-train", "dctr", "longeval-sci-2026/snapshot-1/train"),
    ("sci-2025-01", "test", "longeval-sci/2025-01"),
]

ARMS = {
    "dense_only": "dense_only.toml",
    "fusion_dense_pool": "fusion_dense_pool.toml",
    "fusion_union_pool": "fusion_union_pool.toml",
    "fusion_bm25_dense_splade": "fusion_bm25_dense_splade.toml",
    "bm25_only": "bm25_only_pooled.toml",
}

#: `(treatment, control, claim)` — exactly the contrasts `EXP-2026-08-011` ran.
CONTRASTS = [
    ("fusion_union_pool", "fusion_dense_pool", "C-008"),
    ("fusion_bm25_dense_splade", "fusion_union_pool", "C-014"),
    ("fusion_union_pool", "bm25_only", "C-018"),
    ("fusion_bm25_dense_splade", "bm25_only", "—"),
]


def config_hash(name: str) -> str:
    return hashlib.sha256(
        json.dumps(tomllib.loads((CONFIGS / name).read_text()), sort_keys=True).encode()
    ).hexdigest()[:16]


def read_run(snapshot: str, name: str) -> dict[str, list[tuple[str, float]]] | None:
    digest = config_hash(name)
    prefix = snapshot.replace("/", "_")
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


def verdict(result) -> str:
    if not result.excludes_zero:
        return "spans 0"
    return "positive" if result.mean > 0 else "negative"


def main() -> int:
    import django

    django.setup()
    from harness import datasets, scoring, stats

    results: dict[str, dict] = {}
    absolutes: dict[str, dict[str, float]] = {}
    missing_by_snapshot: dict[str, list[str]] = {}

    for cid, variant, snapshot in SNAPSHOTS:
        collection = datasets.load_collections()[cid]
        dataset = datasets.load_dataset(collection, variant)
        qrels: dict[str, dict[str, int]] = defaultdict(dict)
        for q in dataset.qrels_iter():
            qrels[q.query_id][q.doc_id] = int(q.relevance)

        per_arm: dict[str, dict[str, dict[str, float]]] = {}
        missing = []
        for label, config_file in ARMS.items():
            run = read_run(snapshot, config_file)
            if run is None:
                missing.append(label)
                continue
            per_arm[label] = scoring.score_per_topic(
                run, dict(qrels), measures=MEASURES
            )
        missing_by_snapshot[cid] = missing
        absolutes[cid] = {
            label: sum(s["R@100"] for s in scores.values()) / len(scores)
            for label, scores in per_arm.items()
        }

        rows = {}
        for treat, control, claim in CONTRASTS:
            if treat not in per_arm or control not in per_arm:
                continue
            shared = sorted(set(per_arm[treat]) & set(per_arm[control]))
            for metric in MEASURES:
                deltas = [
                    per_arm[treat][q][metric] - per_arm[control][q][metric]
                    for q in shared
                ]
                rows[(claim, treat, control, metric)] = stats.paired_bootstrap(deltas)
        results[cid] = rows

    lines = [
        (
            "*Paired bootstrap, 10,000 resamples over query ids, fixed seed. "
            "`R@100` is recall **within each snapshot's pooled subset** — a "
            "re-ranking evaluation, not a claim about a full corpus.*"
        ),
        "",
        "### R@100 — the primary comparison",
        "",
        "| Claim | Contrast | 2026 (100q, `dctr`) | 2025-01 (492q, `test`) | replicates |",
        "|---|---|---|---|:--:|",
    ]

    summary = []
    for treat, control, claim in CONTRASTS:
        key = (claim, treat, control, "R@100")
        a = results.get("sci-2026-train", {}).get(key)
        b = results.get("sci-2025-01", {}).get(key)
        if a is None and b is None:
            continue

        def cell(r):
            if r is None:
                return "*not run*"
            return (
                f"{r.mean:+.4f} [{r.ci_low:+.4f}, {r.ci_high:+.4f}]<br>"
                f"{r.wins}W/{r.losses}L, p={r.sign_p:.2g}"
            )

        if a is None or b is None:
            agree = "—"
        elif verdict(a) == verdict(b) and verdict(a) != "spans 0":
            agree = "**yes**"
        elif verdict(a) != verdict(b):
            agree = "**NO**"
        else:
            agree = "both null"
        lines.append(
            f"| {claim} | {treat} − {control} | {cell(a)} | {cell(b)} | {agree} |"
        )
        summary.append({
            "claim": claim, "treatment": treat, "control": control,
            "replicates": agree.replace("*", ""),
            "sci-2026-train": a.as_dict() if a else None,
            "sci-2025-01": b.as_dict() if b else None,
        })

    for metric in ("nDCG@100", "nDCG@10"):
        lines += [
            "",
            f"### {metric}",
            "",
            "| Claim | Contrast | 2026 | 2025-01 |",
            "|---|---|---|---|",
        ]
        for treat, control, claim in CONTRASTS:
            key = (claim, treat, control, metric)
            a = results.get("sci-2026-train", {}).get(key)
            b = results.get("sci-2025-01", {}).get(key)
            if a is None and b is None:
                continue

            def brief(r):
                if r is None:
                    return "*not run*"
                mark = "" if r.excludes_zero else " (spans 0)"
                return f"{r.mean:+.4f}{mark}"

            lines.append(f"| {claim} | {treat} − {control} | {brief(a)} | {brief(b)} |")

    lines += ["", "### Absolute R@100 per arm", "", "| Arm | 2026 | 2025-01 |", "|---|---:|---:|"]
    for label in ARMS:
        a = absolutes.get("sci-2026-train", {}).get(label)
        b = absolutes.get("sci-2025-01", {}).get(label)
        lines.append(
            f"| {label} | {f'{a:.4f}' if a is not None else '—'} | "
            f"{f'{b:.4f}' if b is not None else '—'} |"
        )
    for cid, missing in missing_by_snapshot.items():
        if missing:
            lines += ["", f"*`{cid}` — no run file for: {', '.join(missing)}*"]

    body = "\n".join(lines)
    (EXP_DIR / "tables").mkdir(exist_ok=True)
    (EXP_DIR / "data").mkdir(exist_ok=True)
    (EXP_DIR / "tables" / "replication.md").write_text(body + "\n")
    (EXP_DIR / "data" / "replication.json").write_text(
        json.dumps({"summary": summary, "absolute_r100": absolutes},
                   indent=2, sort_keys=True) + "\n"
    )
    print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
