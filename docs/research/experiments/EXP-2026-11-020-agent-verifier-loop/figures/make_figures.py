"""Regenerate this folder's figure from `../data/metrics.csv` (no number is typed here).

    python3 make_figures.py

fig-forced-draft-outcomes: what the loop did with each forced draft, per error
class (5a): repaired, removed with the notice, still in the final answer, not
flagged by the current checker, other.
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
METRICS = HERE.parent / "data" / "metrics.csv"
CLASSES = ["cite", "figure", "factline"]
OUTCOMES = [("repaired", "#009E73"), ("removed_with_notice", "#0072B2"), ("still_in_final", "#D55E00"),
            ("not_flagged", "#BBBBBB"), ("other", "#E69F00"), ("harness_error", "#555555")]


def main():
    rows = [r for r in csv.DictReader(METRICS.open()) if r["part"] == "5a"]
    fig, ax = plt.subplots(figsize=(6, 3.2))
    left = [0.0] * len(CLASSES)
    for outcome, colour in OUTCOMES:
        vals = []
        for cls in CLASSES:
            r = next((r for r in rows if r["group"] == cls and r["metric"] == outcome), None)
            vals.append(float(r["k"]) if r else 0.0)
        ax.barh(CLASSES, vals, left=left, color=colour, label=outcome.replace("_", " "))
        left = [a + b for a, b in zip(left, vals)]
    ax.set_xlabel("forced drafts")
    ax.legend(frameon=False, fontsize=7, ncol=3, loc="upper center", bbox_to_anchor=(0.5, 1.3))
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    for ext in ("svg", "pdf"):
        fig.savefig(HERE / f"fig-forced-draft-outcomes.{ext}")


if __name__ == "__main__":
    main()
