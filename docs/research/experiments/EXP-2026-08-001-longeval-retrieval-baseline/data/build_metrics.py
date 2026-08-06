"""Rebuild `metrics.csv` and `metrics.json` from the harness's own run files.

The run files in `eval/results/` are the primary record — this script never
computes a metric, it only reshapes what the harness already wrote. That is why
the figures can be trusted: they read this output, and this output reads the
runs.

    python build_metrics.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[4]
RESULTS = REPO_ROOT / "eval" / "results"
BASELINES = REPO_ROOT / "eval" / "baselines.json"

MEASURES = ["nDCG@10", "nDCG@100", "AP", "R@100", "RR", "P@10"]
COLUMNS = [
    "snapshot",
    "qrels",
    "arm",
    "corpus_scope",
    "pool_per_interest",
    "corpus_docs",
    "n_queries",
    *MEASURES,
    "git_sha",
    "dirty",
    "wall_clock_s",
    "source",
]

# Snapshot display order: the 2026 training snapshot first (it carries the
# published baselines), then the 2025 persistence pair in time order.
SNAPSHOT_ORDER = {
    "longeval-sci-2026/snapshot-1/train": 0,
    "longeval-sci/2024-11": 1,
    "longeval-sci/2025-01": 2,
}
ARM_ORDER = {
    "bm25_only": 0,
    "dense_only": 1,
    "fusion_dense_pool": 2,
    "fusion_full": 3,
    "fusion_union_pool": 4,
}


def rows() -> list[dict]:
    collected = []
    for path in sorted(RESULTS.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        row = {
            "snapshot": record["snapshot"],
            "qrels": record["qrels"],
            "arm": record["arm"],
            "corpus_scope": record["corpus_scope"],
            "pool_per_interest": (record.get("params") or {}).get(
                "pool_per_interest", ""
            ),
            "corpus_docs": record["corpus_docs"],
            "n_queries": record["n_queries"],
            "git_sha": record["git_sha"],
            "dirty": record["dirty"],
            "wall_clock_s": record.get("wall_clock_s", ""),
            "source": "mycelium",
        }
        for measure in MEASURES:
            row[measure] = round(record["metrics"][measure], 6)
        collected.append(row)

    published = json.loads(BASELINES.read_text(encoding="utf-8"))
    for baseline in published["baselines"]:
        row = {
            "snapshot": baseline["snapshot"],
            "qrels": baseline["qrels"],
            "arm": baseline["name"],
            "corpus_scope": baseline["corpus_scope"],
            "pool_per_interest": "",
            "corpus_docs": "",
            "n_queries": baseline["n_queries"],
            "git_sha": "",
            "dirty": False,
            "wall_clock_s": "",
            "source": "published",
        }
        for measure in MEASURES:
            row[measure] = round(baseline["metrics"][measure], 6)
        collected.append(row)

    collected.sort(
        key=lambda r: (
            SNAPSHOT_ORDER.get(r["snapshot"], 99),
            r["corpus_scope"],
            ARM_ORDER.get(r["arm"], 98),
            str(r["pool_per_interest"]),
        )
    )
    return collected


def markdown_table(data: list[dict]) -> str:
    """The results table, generated. Nobody types a number into RESULTS.md."""
    lines = [
        "| Snapshot | Scope | Arm | Pool | Docs | Q | "
        + " | ".join(MEASURES)
        + " | Run |",
        "|---|---|---|---:|---:|---:|" + "---:|" * len(MEASURES) + "---|",
    ]
    for row in data:
        pool = row["pool_per_interest"] or "—"
        docs = f"{int(row['corpus_docs']):,}" if row["corpus_docs"] else "—"
        run = f"`{row['git_sha']}`" if row["git_sha"] else "_published_"
        if row["dirty"] in (True, "True", "true"):
            run += " ⚠️"
        cells = " | ".join(f"{float(row[m]):.4f}" for m in MEASURES)
        lines.append(
            f"| `{row['snapshot']}` | {row['corpus_scope']} | `{row['arm']}` | "
            f"{pool} | {docs} | {row['n_queries']} | {cells} | {run} |"
        )
    return "\n".join(lines)


def inject_table(data: list[dict]) -> None:
    """Write the table into tables/ and into RESULTS.md between its markers."""
    table = markdown_table(data)
    tables_dir = HERE.parent / "tables"
    tables_dir.mkdir(exist_ok=True)
    (tables_dir / "results.md").write_text(table + "\n", encoding="utf-8")

    results = HERE.parent / "RESULTS.md"
    if not results.is_file():
        return
    text = results.read_text(encoding="utf-8")
    begin, end = "<!-- BEGIN GENERATED TABLE -->", "<!-- END GENERATED TABLE -->"
    if begin not in text or end not in text:
        return
    head, rest = text.split(begin, 1)
    _, tail = rest.split(end, 1)
    results.write_text(
        f"{head}{begin}\n\n{table}\n\n{end}{tail}", encoding="utf-8"
    )


def main() -> None:
    data = rows()

    with (HERE / "metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(data)

    # metrics.json carries the canonical headline numbers the manifest mirrors.
    ours = [r for r in data if r["source"] == "mycelium"]
    best_by_snapshot = {}
    for snapshot in SNAPSHOT_ORDER:
        pooled = [
            r for r in ours if r["snapshot"] == snapshot and r["corpus_scope"] == "pooled"
        ]
        if not pooled:
            continue
        best_by_snapshot[snapshot] = {
            "best_arm_nDCG@10": max(pooled, key=lambda r: r["nDCG@10"])["arm"],
            "best_nDCG@10": max(r["nDCG@10"] for r in pooled),
            "bm25_nDCG@10": next(
                (r["nDCG@10"] for r in pooled if r["arm"] == "bm25_only"), None
            ),
        }

    payload = {
        "experiment": "EXP-2026-08-001",
        "generated_from": "eval/results/*.json + eval/baselines.json",
        "n_runs_recorded": len(ours),
        "measures": MEASURES,
        "primary": "nDCG@10",
        "note": (
            "Each row is a single deterministic run (n=1), not a mean over seeds. "
            "The arms use fixed embeddings and exact similarity, so repeating a "
            "run reproduces the number exactly; there is no variance to report."
        ),
        "per_snapshot_pooled": best_by_snapshot,
        "rows": data,
    }
    (HERE / "metrics.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    inject_table(data)
    print(f"Wrote metrics.csv, metrics.json, tables/results.md ({len(data)} rows)")


if __name__ == "__main__":
    main()
