"""Turn the harness's raw outputs into this experiment's metrics and tables.

Reads ``data/exp005-arm-a.json``, ``data/exp005-arm-b.json``,
``data/exp005-sweep.json`` and ``data/exp005-arm-b-rescored.json`` (all written
by ``python -m sandbox.collab``), and writes ``data/metrics.json``,
``data/metrics.csv``, ``tables/summary.md``, ``tables/sweep.md`` and
``tables/splits.md``. Nothing in those files is typed by hand.

    python3 docs/research/experiments/EXP-2026-09-005-knowledge-demonstrated-sandbox/code/analyse.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
DATA = HERE / "data"
TABLES = HERE / "tables"

SUMMARY_KEYS = [
    "q2_declared_and_demonstrated_recall",
    "method_split_total",
    "wrong_merge_total",
    "method_recall",
    "method_term_contamination",
    "field_ruler_accuracy",
    "q2_declared_only_recall",
    "q2_undeclared_method_shown_recall",
    "q1_recall",
    "q1_precision",
    "thin_rate_on_clean",
    "neutral_present_rate",
    "concepts_global",
    "concepts_private",
]


def load(name: str) -> dict:
    return json.loads((DATA / name).read_text())


def main() -> None:
    arms = {"a_w1": load("exp005-arm-a.json"), "b_w2": load("exp005-arm-b.json")}
    sweep = load("exp005-sweep.json")["sweep"]
    rescored = load("exp005-arm-b-rescored.json")["metrics"]

    metrics: dict = {}
    for arm, report in arms.items():
        m = report["metrics"]
        for key in SUMMARY_KEYS:
            metrics[f"{arm}__{key}"] = m[key]
        for name, value in m["invariants"].items():
            metrics[f"{arm}__invariant__{name}"] = value
        run = m["run"]
        metrics[f"{arm}__model_calls"] = run["model_calls"]
        metrics[f"{arm}__model_failures"] = run["model_failures"]
        metrics[f"{arm}__model_seconds_mean"] = run["model_seconds_mean"]
        metrics[f"{arm}__first_pass_seconds"] = run["first_pass_seconds"]
        metrics[f"{arm}__projection_seconds"] = run["projection_seconds"]
        metrics[f"{arm}__works"] = m["works_total"]
        metrics[f"{arm}__corpus_generator_slips"] = m["corpus_generator_slips"]
        metrics[f"{arm}__demonstrated_edges"] = m["edges_by_tier"].get("demonstrated", 0)
    metrics["b_minus_a__q2_declared_and_demonstrated_recall"] = round(
        metrics["b_w2__q2_declared_and_demonstrated_recall"]
        - metrics["a_w1__q2_declared_and_demonstrated_recall"],
        4,
    )
    metrics["b_minus_a__method_split_total"] = (
        metrics["b_w2__method_split_total"] - metrics["a_w1__method_split_total"]
    )
    for row in sweep:
        tag = f"sweep_{row['threshold']:.2f}".replace(".", "")
        for key in (
            "method_split_total",
            "wrong_merge_total",
            "q2_declared_and_demonstrated_recall",
            "q2_undeclared_method_shown_recall",
            "q1_recall",
            "q1_precision",
            "field_ruler_accuracy",
            "concepts_global",
        ):
            metrics[f"{tag}__{key}"] = row[key]
    metrics["rescored_092__method_split_total"] = rescored["method_split_total"]
    metrics["rescored_092__q2_declared_and_demonstrated_recall"] = rescored[
        "q2_declared_and_demonstrated_recall"
    ]

    (DATA / "metrics.json").write_text(json.dumps(metrics, indent=1, sort_keys=True))
    with (DATA / "metrics.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "value"])
        for key in sorted(metrics):
            writer.writerow([key, metrics[key]])

    TABLES.mkdir(exist_ok=True)
    lines = [
        "| Metric | Arm A (w1) | Arm B (w2) |",
        "|---|---:|---:|",
    ]
    for key in SUMMARY_KEYS + ["model_calls", "model_seconds_mean", "first_pass_seconds"]:
        lines.append(
            f"| `{key}` | {metrics.get(f'a_w1__{key}')} | {metrics.get(f'b_w2__{key}')} |"
        )
    for name in arms["a_w1"]["metrics"]["invariants"]:
        lines.append(
            f"| invariant `{name}` | {metrics[f'a_w1__invariant__{name}']} "
            f"| {metrics[f'b_w2__invariant__{name}']} |"
        )
    (TABLES / "summary.md").write_text("\n".join(lines) + "\n")

    lines = [
        "| Threshold | Splits | Wrong merges | Q2 both | Undeclared shown | Q1 recall | Q1 precision | Field ruler | Concepts |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in sweep:
        lines.append(
            f"| {row['threshold']:.2f} | {row['method_split_total']} | {row['wrong_merge_total']} "
            f"| {row['q2_declared_and_demonstrated_recall']} | {row['q2_undeclared_method_shown_recall']} "
            f"| {row['q1_recall']} | {row['q1_precision']} | {row['field_ruler_accuracy']} "
            f"| {row['concepts_global']} |"
        )
    (TABLES / "sweep.md").write_text("\n".join(lines) + "\n")

    lines = ["| Method | Concept | Papers | Surfaces |", "|---|---:|---:|---|"]
    for method, rows in sorted(rescored["split_examples"].items()):
        for row in rows:
            surfaces = "; ".join(row["surfaces"])
            lines.append(f"| {method} | {row['concept']} | {row['papers']} | {surfaces} |")
    (TABLES / "splits.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
