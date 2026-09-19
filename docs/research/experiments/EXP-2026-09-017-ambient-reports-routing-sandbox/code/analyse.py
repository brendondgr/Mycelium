"""EXP-2026-09-017's table, from ``data/exp017-run{1,2}.json``.

    python3 docs/research/experiments/EXP-2026-09-017-ambient-reports-routing-sandbox/code/analyse.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
RUNS = {"run1": "registered @3955910", "run2": "harness row matching + undo mark @2babb96"}


def main() -> None:
    metrics = {}
    for run, label in RUNS.items():
        data = json.loads((HERE / "data" / f"exp017-{run}.json").read_text())
        c = data["checks"]
        metrics[run] = {
            "label": label,
            "violations_total": data["violations_total"],
            "rows_expected": c["H1_routing"]["rows_expected"],
            "rows_missing": c["H1_routing"]["missing"],
            "rows_duplicated": c["H1_routing"]["duplicated"],
            "rows_leaked": c["H1_routing"]["leaked"],
            "o_citations": c["H2_citations"]["cited"],
            "o_unresolved": c["H2_citations"]["unresolved"],
            "model_sentences_citing_o": c["H2_citations"]["model_sentences_citing_O"],
            "interpretation_ok": c["H3_interpretation"]["ok"],
            "dailies": c["H4_dailies"]["generated"],
            "daily_mismatch": len(c["H4_dailies"]["mismatch"]),
            "lab_development_lines": c["H4_dailies"]["lab_development_lines"],
            "weeklies": data["counts"]["people"] + data["counts"]["labs"],
            "seconds": data["timings"]["total_s"],
        }
    (HERE / "data" / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    keys = [k for k in next(iter(metrics.values())) if k != "label"]
    with (HERE / "data" / "metrics.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["run", *keys])
        for run, row in metrics.items():
            writer.writerow([run, *(row[k] for k in keys)])
    lines = ["| Run | " + " | ".join(keys) + " |", "|---|" + "---:|" * len(keys)]
    for run, row in metrics.items():
        lines.append(f"| {run} — {row['label']} | " + " | ".join(str(row[k]) for k in keys) + " |")
    (HERE / "tables" / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
