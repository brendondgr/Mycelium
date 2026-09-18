"""Turn the harness's output into this experiment's metrics and table.

Reads ``data/exp007.json`` (``python -m sandbox.collab consent``) and writes
``data/metrics.json``, ``data/metrics.csv`` and ``tables/summary.md``.

    python3 docs/research/experiments/EXP-2026-09-007-collab-consent-sandbox/code/analyse.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent


def main() -> None:
    report = json.loads((HERE / "data" / "exp007.json").read_text())
    metrics = dict(report["metrics"])
    metrics["results_withheld_share"] = round(
        metrics["results_withheld_by_cap"]
        / (metrics["results_withheld_by_cap"] + metrics["results_returned"]),
        4,
    )
    metrics["apply_seconds"] = report["apply_seconds"]
    metrics["check_seconds"] = report["check_seconds"]
    (HERE / "data" / "metrics.json").write_text(json.dumps(metrics, indent=1, sort_keys=True))
    with (HERE / "data" / "metrics.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "value"])
        for key in sorted(metrics):
            writer.writerow([key, metrics[key]])
    (HERE / "tables").mkdir(exist_ok=True)
    lines = ["| Metric | Value |", "|---|---:|"] + [
        f"| `{key}` | {metrics[key]} |" for key in sorted(metrics)
    ]
    (HERE / "tables" / "summary.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
