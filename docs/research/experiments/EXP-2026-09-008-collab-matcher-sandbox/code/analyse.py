"""Turn the matcher harness's output into this experiment's metrics and table.

Reads ``data/exp008-arm{A,B,C}.json`` (``python -m sandbox.collab match``;
A = as registered, concept threshold 0.70; B = shipped concept threshold 0.80;
C = B plus the slot-by-slot lane fill, post hoc) and writes
``data/metrics.json``, ``data/metrics.csv`` and ``tables/summary.md``.

    python3 docs/research/experiments/EXP-2026-09-008-collab-matcher-sandbox/code/analyse.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
ARMS = {"A": "registered (concept 0.70)", "B": "concept 0.80", "C": "B + slot-by-slot fill (post hoc)"}
QUALITY = (
    "searches",
    "rows_checked",
    "method_bridge_hit_rate",
    "method_bridge_precision",
    "method_bridge_recall_at_k",
    "method_slots_with_truth",
    "in_field_precision",
    "problem_bridge_returned",
    "latency_p50",
    "latency_p95",
)
LOAD = ("latency_p50", "latency_p95", "max_distinct_seekers", "gini_distinct_seekers", "violations_cap")


def main() -> None:
    metrics: dict = {}
    rows = []
    for arm in ARMS:
        path = HERE / "data" / f"exp008-arm{arm}.json"
        if not path.exists():
            continue
        report = json.loads(path.read_text())
        violations = sum(
            v
            for section in ("quality_institution", "quality_anywhere", "load_capped")
            for k, v in report[section].items()
            if k.startswith("violations")
        )
        metrics[f"{arm}_violations_total"] = violations
        for scope in ("institution", "anywhere"):
            q = report[f"quality_{scope}"]
            for key in QUALITY:
                metrics[f"{arm}_{scope}_{key}"] = q.get(key, 0)
            rows.append({"arm": arm, "scope": scope, **{k: q.get(k, 0) for k in QUALITY}})
        for kind in ("capped", "uncapped"):
            for key in LOAD:
                metrics[f"{arm}_load_{kind}_{key}"] = report[f"load_{kind}"].get(key)
    (HERE / "data" / "metrics.json").write_text(json.dumps(metrics, indent=1, sort_keys=True))
    with (HERE / "data" / "metrics.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    lines = [
        "| Arm | Scope | Searches | Hit rate | Precision | Recall@3 | In-field precision | Problem-bridge rows | p50 s | p95 s |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ] + [
        f"| {r['arm']} — {ARMS[r['arm']]} | {r['scope']} | {r['searches']} | {r['method_bridge_hit_rate']} "
        f"| {r['method_bridge_precision']} | {r['method_bridge_recall_at_k']} | {r['in_field_precision']} "
        f"| {r['problem_bridge_returned']} | {r['latency_p50']} | {r['latency_p95']} |"
        for r in rows
    ]
    (HERE / "tables").mkdir(exist_ok=True)
    (HERE / "tables" / "summary.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
