"""EXP-2026-09-015's metrics and table, from the harness's output.

Reads ``data/exp015-run{1..4}.json`` (``python -m sandbox.ambient replies``
output; run 1 registered, 2-4 post hoc) and writes ``data/metrics.json``,
``data/metrics.csv`` and ``tables/summary.md``.

    python3 docs/research/experiments/EXP-2026-09-015-ambient-dialogue-replies-sandbox/code/analyse.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
RUNS = {
    "run1": ("registered, reader r1 @60fd1c3", "exp015-run1.json"),
    "run2": ("post hoc, reader r2 @75b35c9", "exp015-run2.json"),
    "run3": ("post hoc, reader r3 @2792c59", "exp015-run3.json"),
    "run4": ("post hoc, reader r4 @377fbed", "exp015-run4.json"),
}
INTENTS = ["yes", "other", "no", "later", "correction", "ambiguous", "offtopic"]


def main() -> None:
    metrics: dict[str, dict] = {}
    for run, (label, name) in RUNS.items():
        data = json.loads((HERE / "data" / name).read_text())
        replies = data["metrics"]["replies"]
        score = replies["score"]
        shut = data["metrics"]["shutoff"]
        row = {
            "label": label,
            "questions": replies["questions"],
            "replies": score["replies"],
            "unread": score["unread"],
            "harmful_yes": score["harmful_yes"],
            "harmful_yes_rate": score["harmful_yes_rate"],
            "harmful_yes_rate_clean": score.get("harmful_yes_rate_clean"),
            "truth_contradicted": score.get("truth_contradicted"),
            "overall_accuracy": score["overall_accuracy"],
            "effects_applied": replies["effects"]["applied"],
            "effect_mismatch": replies["effects"]["effect_mismatch"],
            "shutoff_literal_caught": shut["requests_caught"] / shut["requests"],
            "shutoff_literal_decoys_tripped": shut["decoys_tripped"] / shut["decoys"],
            "shutoff_model_caught": (
                shut["requests_caught_with_model"] / shut["requests"]
                if "requests_caught_with_model" in shut
                else None
            ),
            "shutoff_model_decoys_tripped": (
                shut["decoys_tripped_with_model"] / shut["decoys"]
                if "decoys_tripped_with_model" in shut
                else None
            ),
            "minutes": round(sum(data["timings"].values()) / 60, 1),
        }
        for intent in INTENTS:
            row[f"accuracy_{intent}"] = score["by_intent"].get(intent, {}).get("accuracy")
        metrics[run] = row
    (HERE / "data" / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    keys = [k for k in next(iter(metrics.values())) if k != "label"]
    with (HERE / "data" / "metrics.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["run", *keys])
        for run, row in metrics.items():
            writer.writerow([run, *(row[k] for k in keys)])
    shown = [
        "harmful_yes",
        "harmful_yes_rate",
        "overall_accuracy",
        "accuracy_yes",
        "accuracy_no",
        "accuracy_ambiguous",
        "accuracy_offtopic",
        "effect_mismatch",
        "shutoff_literal_caught",
        "shutoff_model_caught",
        "shutoff_model_decoys_tripped",
        "minutes",
    ]
    lines = ["| Run | " + " | ".join(shown) + " |", "|---|" + "---:|" * len(shown)]
    for run, row in metrics.items():
        cells = []
        for k in shown:
            v = row[k]
            cells.append("—" if v is None else (f"{v:.4g}" if isinstance(v, float) else str(v)))
        lines.append(f"| {run} — {row['label']} | " + " | ".join(cells) + " |")
    (HERE / "tables" / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
