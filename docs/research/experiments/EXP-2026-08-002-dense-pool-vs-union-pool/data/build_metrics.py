"""Rebuild this experiment's metrics from EXP-2026-08-001's recorded runs.

This ablation shares its runs with `EXP-2026-08-001` — the arms were run once and
answer two different questions. Rather than duplicate the run records, this
script reads that experiment's `metrics.csv` and derives the paired comparison.

    python build_metrics.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = (
    HERE.parents[1]
    / "EXP-2026-08-001-longeval-retrieval-baseline"
    / "data"
    / "metrics.csv"
)

MEASURES = ["R@100", "nDCG@100", "AP", "nDCG@10"]
SNAPSHOTS = [
    "longeval-sci-2026/snapshot-1/train",
    "longeval-sci/2024-11",
    "longeval-sci/2025-01",
]
POOL_WIDTHS = ["100", "1000"]
COLUMNS = [
    "snapshot",
    "pool_per_interest",
    "n_queries",
    *[f"dense_{m}" for m in MEASURES],
    *[f"union_{m}" for m in MEASURES],
    *[f"delta_pct_{m}" for m in MEASURES],
]


SHORT_SNAPSHOT = {
    "longeval-sci-2026/snapshot-1/train": "2026 train",
    "longeval-sci/2024-11": "2024-11",
    "longeval-sci/2025-01": "2025-01",
}


def markdown_table(paired: list[dict]) -> str:
    lines = [
        "| Snapshot | Pool | Q | dense R@100 | union R@100 | **ΔR@100** | "
        "dense nDCG@10 | union nDCG@10 | ΔnDCG@10 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in paired:
        lines.append(
            "| `{snap}` | {pool} | {q} | {dr:.4f} | {ur:.4f} | **{dd:+.1f}%** | "
            "{dn:.4f} | {un:.4f} | {nd:+.1f}% |".format(
                snap=SHORT_SNAPSHOT[row["snapshot"]],
                pool=row["pool_per_interest"],
                q=row["n_queries"],
                dr=row["dense_R@100"],
                ur=row["union_R@100"],
                dd=row["delta_pct_R@100"],
                dn=row["dense_nDCG@10"],
                un=row["union_nDCG@10"],
                nd=row["delta_pct_nDCG@10"],
            )
        )
    return "\n".join(lines)


def inject_table(paired: list[dict]) -> None:
    table = markdown_table(paired)
    tables_dir = HERE.parent / "tables"
    tables_dir.mkdir(exist_ok=True)
    (tables_dir / "pool-comparison.md").write_text(table + "\n", encoding="utf-8")

    results = HERE.parent / "RESULTS.md"
    if not results.is_file():
        return
    text = results.read_text(encoding="utf-8")
    begin, end = "<!-- BEGIN GENERATED TABLE -->", "<!-- END GENERATED TABLE -->"
    if begin not in text or end not in text:
        return
    head, rest = text.split(begin, 1)
    _, tail = rest.split(end, 1)
    results.write_text(f"{head}{begin}\n\n{table}\n\n{end}{tail}", encoding="utf-8")


def main() -> None:
    rows = list(csv.DictReader(SOURCE.open(encoding="utf-8")))

    def find(snapshot: str, arm: str, pool: str) -> dict | None:
        for row in rows:
            if (
                row["snapshot"] == snapshot
                and row["arm"] == arm
                and row["corpus_scope"] == "pooled"
                and row["pool_per_interest"] == pool
            ):
                return row
        return None

    paired = []
    for snapshot in SNAPSHOTS:
        for pool in POOL_WIDTHS:
            dense = find(snapshot, "fusion_dense_pool", pool)
            union = find(snapshot, "fusion_union_pool", pool)
            if not dense or not union:
                continue
            row = {
                "snapshot": snapshot,
                "pool_per_interest": pool,
                "n_queries": dense["n_queries"],
            }
            for measure in MEASURES:
                d, u = float(dense[measure]), float(union[measure])
                row[f"dense_{measure}"] = round(d, 6)
                row[f"union_{measure}"] = round(u, 6)
                row[f"delta_pct_{measure}"] = round(100 * (u - d) / d, 2) if d else ""
            paired.append(row)

    with (HERE / "metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(paired)

    recall_deltas = [r["delta_pct_R@100"] for r in paired]
    payload = {
        "experiment": "EXP-2026-08-002",
        "generated_from": (
            "docs/research/experiments/EXP-2026-08-001-longeval-retrieval-baseline"
            "/data/metrics.csv (shared runs)"
        ),
        "primary": "R@100 relative gain, union pool over dense pool",
        "note": (
            "Paired comparison at matched pool width and matched corpus scope. "
            "Each cell is one deterministic run (n=1). The comparison is within "
            "snapshot and within pool width; nothing is compared across scopes."
        ),
        "headline": {
            "at_pool_100": {
                r["snapshot"]: r["delta_pct_R@100"]
                for r in paired
                if r["pool_per_interest"] == "100"
            },
            "at_pool_1000": {
                r["snapshot"]: r["delta_pct_R@100"]
                for r in paired
                if r["pool_per_interest"] == "1000"
            },
            "max_gain_pct": max(recall_deltas) if recall_deltas else None,
            "min_gain_pct": min(recall_deltas) if recall_deltas else None,
        },
        "rows": paired,
    }
    (HERE / "metrics.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    inject_table(paired)
    print(
        f"Wrote metrics.csv, metrics.json, tables/pool-comparison.md "
        f"({len(paired)} paired rows)"
    )


if __name__ == "__main__":
    main()
