"""Turn the harness's outputs into this experiment's metrics and tables.

Reads ``data/exp006-arm-a.json``, ``-arm-b.json`` and ``-arm-c.json`` (written
by ``python -m sandbox.collab calls``) and writes ``data/metrics.json``,
``data/metrics.csv`` and ``tables/summary.md``. Nothing there is typed by hand.

    python3 docs/research/experiments/EXP-2026-09-006-collab-slots-teamfit-sandbox/code/analyse.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
DATA = HERE / "data"
TABLES = HERE / "tables"
ARMS = {"a_s1": "exp006-arm-a.json", "b_s2": "exp006-arm-b.json", "c_s3": "exp006-arm-c.json"}
ROWS = [
    "slot_recall_non_role",
    "slot_precision",
    "slot_required_agreement",
    "slot_recall__problem",
    "slot_recall__method",
    "slot_recall__data",
    "slot_recall__role",
    "coverage_agreement__lab_canonical",
    "coverage_agreement__lab_variant",
    "coverage_agreement__lab_problem_data",
    "coverage_agreement__person_canonical",
    "coverage_agreement__person_variant",
    "coverage_agreement__person_problem_data",
    "near_miss_false_cover",
    "near_miss_false_cover_rate",
    "extra_slots",
    "extra_slots_verbatim_in_call",
    "slots_model_calls",
    "slots_seconds",
    "team_fit_labs_seconds",
    "team_fit_people_seconds",
    "score_rows",
]


def flatten(report: dict) -> dict:
    m = report["metrics"]
    run = m["run"]
    out = {k: m.get(k) for k in (
        "calls", "calls_clean", "generator_slips", "slot_recall_non_role",
        "slot_precision", "slot_required_agreement", "near_miss_false_cover",
        "near_miss_false_cover_rate", "extra_slots", "extra_slots_verbatim_in_call",
    )}
    for facet, value in m["slot_recall_by_facet"].items():
        out[f"slot_recall__{facet}"] = value
    for bucket, value in m["coverage_agreement"].items():
        out[f"coverage_agreement__{bucket}"] = value
        out[f"coverage_pairs__{bucket}"] = m["coverage_pairs"][bucket]
    for name, value in m["invariants"].items():
        out[f"invariant__{name}"] = value
    for key in ("slots_model_calls", "slots_model_failures", "slots_seconds", "score_rows",
                "team_fit_labs_seconds", "team_fit_people_seconds", "team_fit_rows_changed"):
        out[key] = run[key]
    return out


def main() -> None:
    arms = {arm: flatten(json.loads((DATA / name).read_text())) for arm, name in ARMS.items()}
    metrics = {f"{arm}__{k}": v for arm, values in arms.items() for k, v in values.items()}
    (DATA / "metrics.json").write_text(json.dumps(metrics, indent=1, sort_keys=True))
    with (DATA / "metrics.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "value"])
        for key in sorted(metrics):
            writer.writerow([key, metrics[key]])
    TABLES.mkdir(exist_ok=True)
    lines = ["| Metric | Arm A (s1) | Arm B (s2) | Arm C (s3) |", "|---|---:|---:|---:|"]
    for key in ROWS + sorted(k for k in arms["c_s3"] if k.startswith("invariant__")):
        lines.append(f"| `{key}` | " + " | ".join(str(arms[a].get(key)) for a in ARMS) + " |")
    (TABLES / "summary.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
