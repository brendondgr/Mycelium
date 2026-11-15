"""Regenerate this folder's figure from `../data/metrics.csv` (no number is typed here).

    python3 make_figures.py

fig-full-credit-by-kind: full-credit rate per question kind and arm (primary
grading; for the unanswerable kind, full credit = declined and stated no fact),
with Wilson 95% intervals over runs.
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
METRICS = HERE.parent / "data" / "metrics.csv"
KINDS = ["field", "list", "project", "people", "join", "unanswerable"]
ARMS = {"a": ("Mylo as shipped", "#0072B2"), "b": ("one search + one call", "#E69F00"),
        "c": ("Mylo, corpus functions only", "#009E73")}


def main():
    rows = [r for r in csv.DictReader(METRICS.open())
            if r["grading"] == "primary" and r["metric"] == "full_credit" and r["kind"] in KINDS]
    fig, ax = plt.subplots(figsize=(8, 3.6))
    width = 0.26
    for i, (arm, (label, colour)) in enumerate(ARMS.items()):
        xs, ys, lo, hi = [], [], [], []
        for j, kind in enumerate(KINDS):
            r = next((r for r in rows if r["arm"] == arm and r["kind"] == kind), None)
            if r is None:
                continue
            v = float(r["value"])
            xs.append(j + (i - 1) * width)
            ys.append(v)
            lo.append(v - float(r["lo"]))
            hi.append(float(r["hi"]) - v)
        ax.bar(xs, ys, width, label=label, color=colour, yerr=[lo, hi], capsize=2, error_kw={"lw": 0.8})
    ax.set_xticks(range(len(KINDS)))
    ax.set_xticklabels(KINDS)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("full credit (share of runs)")
    ax.legend(frameon=False, fontsize=8, ncol=3, loc="upper center", bbox_to_anchor=(0.5, 1.15))
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    for ext in ("svg", "pdf"):
        fig.savefig(HERE / f"fig-full-credit-by-kind.{ext}")


if __name__ == "__main__":
    main()
