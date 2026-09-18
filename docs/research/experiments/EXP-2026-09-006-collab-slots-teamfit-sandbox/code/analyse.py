"""Turn the harness's output into this experiment's metrics and tables.

Reads ``data/exp006.json`` (written by ``python -m sandbox.collab calls``) and
writes ``data/metrics.json``, ``data/metrics.csv`` and ``tables/summary.md``.
Nothing in those files is typed by hand.

    python3 docs/research/experiments/EXP-2026-09-006-collab-slots-teamfit-sandbox/code/analyse.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
DATA = HERE / "data"
TABLES = HERE / "tables"


def main() -> None:
    report = json.loads((DATA / "exp006.json").read_text())
    m = report["metrics"]
    run = m["run"]
    metrics: dict = {
        "calls": m["calls"],
        "calls_clean": m["calls_clean"],
        "generator_slips": m["generator_slips"],
        "slot_recall_non_role": m["slot_recall_non_role"],
        "slot_precision": m["slot_precision"],
        "slot_required_agreement": m["slot_required_agreement"],
        "coverage_agreement_lab_canonical": m["coverage_agreement_lab_canonical"],
        "near_miss_false_cover": m["near_miss_false_cover"],
        "near_miss_false_cover_rate": m["near_miss_false_cover_rate"],
        "slots_model_calls": run["slots_model_calls"],
        "slots_model_failures": run["slots_model_failures"],
        "slots_seconds": run["slots_seconds"],
        "score_rows": run["score_rows"],
        "team_fit_labs_seconds": run["team_fit_labs_seconds"],
        "team_fit_people_seconds": run["team_fit_people_seconds"],
        "team_fit_rows_changed": run["team_fit_rows_changed"],
    }
    for facet, value in m["slot_recall_by_facet"].items():
        metrics[f"slot_recall__{facet}"] = value
    for bucket, value in m["coverage_agreement"].items():
        metrics[f"coverage_agreement__{bucket}"] = value
        metrics[f"coverage_pairs__{bucket}"] = m["coverage_pairs"][bucket]
    for name, value in m["invariants"].items():
        metrics[f"invariant__{name}"] = value

    (DATA / "metrics.json").write_text(json.dumps(metrics, indent=1, sort_keys=True))
    with (DATA / "metrics.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "value"])
        for key in sorted(metrics):
            writer.writerow([key, metrics[key]])

    TABLES.mkdir(exist_ok=True)
    lines = ["| Metric | Value |", "|---|---:|"]
    lines += [f"| `{key}` | {metrics[key]} |" for key in sorted(metrics)]
    (TABLES / "summary.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
