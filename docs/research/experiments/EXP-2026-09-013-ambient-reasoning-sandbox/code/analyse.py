"""Turn the ambient harness's output into this experiment's metrics and table.

Reads ``data/exp013-run*.json`` (from ``python -m sandbox.ambient all``) and
writes ``data/metrics.json``, ``data/metrics.csv`` and ``tables/summary.md``.
Runs 1 and 2 left no valid output (see ISSUES.md) and have no file.

    python3 docs/research/experiments/EXP-2026-09-013-ambient-reasoning-sandbox/code/analyse.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
RUNS = {
    "run3": "registered: prompt a2",
    "run4": "post hoc: prompt a4, unattributed self intents as interests",
    "run5": "post hoc: run 4 + a retired row never counts as live",
}
KEYS = (
    "plants_in_truth",
    "recall",
    "kind_accuracy",
    "colleague_read_as_self",
    "strict_precision",
    "outcome_accuracy",
    "false_suggestion_rate",
    "explained_rate",
    "harm_total",
)


def main() -> None:
    metrics: dict[str, dict] = {}
    for run, label in RUNS.items():
        path = HERE / "data" / f"exp013-{run}.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        m = data["metrics"]
        row = {key: m.get(key) for key in KEYS}
        row["minutes"] = round(sum(data["timings"].values()) / 60, 1)
        for plant, value in (m.get("recall_by_plant") or {}).items():
            row[f"recall_{plant}"] = value
        row["harm"] = m["harm"]
        row["outcome_confusion"] = m["outcome_confusion"]
        row["findings_by_reason"] = m["findings_by_reason"]
        row["kind_confusion"] = m["kind_confusion"]
        row["label"] = label
        metrics[run] = row
    (HERE / "data" / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    flat = [
        {"run": run, **{k: v for k, v in row.items() if not isinstance(v, dict)}}
        for run, row in metrics.items()
    ]
    if flat:
        fields = list(dict.fromkeys(k for row in flat for k in row))
        with (HERE / "data" / "metrics.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(flat)
    head = ["Run", *KEYS, "minutes"]
    lines = [
        "| " + " | ".join(head) + " |",
        "|---|" + "---:|" * (len(head) - 1),
    ]
    for run, row in metrics.items():
        cells = [f"{run} — {row['label']}"] + [
            "" if row.get(k) is None else str(row.get(k)) for k in (*KEYS, "minutes")
        ]
        lines.append("| " + " | ".join(cells) + " |")
    (HERE / "tables" / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
