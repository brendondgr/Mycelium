"""Turn the benchmark's output into this experiment's metrics and table.

Reads ``data/exp011.json`` (arm A, the pre-registered graphs) and, if present,
``data/exp011-hubs.json`` (arm B, exploratory: 1% prolific co-authors), both
written by ``python -m sandbox.collab bench``, and writes ``data/metrics.json``,
``data/metrics.csv`` and ``tables/summary.md``.

    python3 docs/research/experiments/EXP-2026-09-011-coauthorship-store-benchmark/code/analyse.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
WALKS = ("intro", "network", "distance")


def rows(report: dict, arm: str):
    for size, row in sorted(report["sizes"].items(), key=lambda kv: int(kv[0])):
        for store in ("pg", "neo4j"):
            if store not in row:
                continue
            for walk in WALKS:
                t = row[store][walk]
                yield {
                    "arm": arm,
                    "people": int(size),
                    "edges": row["edges"],
                    "max_degree": row["max_degree"],
                    "store": store,
                    "walk": walk,
                    "p50_ms": t["p50_ms"],
                    "p95_ms": t["p95_ms"],
                    "max_ms": t["max_ms"],
                    "disagreements": row.get(f"{store}_disagreements"),
                }


def main() -> None:
    table = list(rows(json.loads((HERE / "data" / "exp011.json").read_text()), "A"))
    hubs = HERE / "data" / "exp011-hubs.json"
    if hubs.exists():
        table += list(rows(json.loads(hubs.read_text()), "B (hubs)"))
    metrics = {
        f"{r['arm'][0].lower()}_{r['store']}_{r['walk']}_p95_ms_{r['people']}": r["p95_ms"]
        for r in table
    }
    metrics["disagreements_total"] = sum(r["disagreements"] or 0 for r in table) // 3
    a20 = {r["walk"]: r["p95_ms"] for r in table if r["arm"] == "A" and r["people"] == 20000 and r["store"] == "pg"}
    metrics["pg_intro_p95_ms"] = a20.get("intro")
    (HERE / "data" / "metrics.json").write_text(json.dumps(metrics, indent=1, sort_keys=True))
    fields = list(table[0])
    with (HERE / "data" / "metrics.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(table)
    lines = [
        "| Arm | People | Edges | Max degree | Store | Walk | p50 ms | p95 ms | max ms | Disagreements |",
        "|---|---:|---:|---:|---|---|---:|---:|---:|---:|",
    ] + [
        f"| {r['arm']} | {r['people']:,} | {r['edges']:,} | {r['max_degree']} | {r['store']} | {r['walk']} "
        f"| {r['p50_ms']} | {r['p95_ms']} | {r['max_ms']} | {r['disagreements']} |"
        for r in table
    ]
    (HERE / "tables").mkdir(exist_ok=True)
    (HERE / "tables" / "summary.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
