"""Regenerate this experiment's figure from `../data/metrics.csv`.

    python make_figures.py

Every plotted value comes from the CSV. No number appears in this file.
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
METRICS = HERE.parent / "data" / "metrics.csv"

DENSE = "#009E73"  # Okabe-Ito, matched to EXP-2026-08-001's arm colours
UNION = "#E69F00"
SNAPSHOT_LABELS = {
    "longeval-sci-2026/snapshot-1/train": "2026 train",
    "longeval-sci/2024-11": "2024-11",
    "longeval-sci/2025-01": "2025-01",
}

# `svg.hashsalt` fixes matplotlib's otherwise-random `<defs>` ids; together with
# a null Date/CreationDate this makes an unchanged figure regenerate
# byte-identically, which is what lets CI check for staleness by diffing.
plt.rcParams.update(
    {
        "svg.hashsalt": "mycelium-research-record",
        "font.size": 9,
        "axes.titlesize": 10,
        "axes.labelsize": 9,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 8,
        "figure.dpi": 150,
        "savefig.bbox": "tight",
        "pdf.fonttype": 42,
        "svg.fonttype": "none",
        "axes.spines.top": False,
        "axes.spines.right": False,
    }
)


def fig_pool_recall_gap(rows: list[dict]) -> None:
    """R@100 for both pool constructions, at both pool widths, per snapshot.

    Two panels because the answer depends on pool width: at width 100 the gap is
    enormous, at width 1000 it mostly closes. Plotting only one width would make
    the finding look either alarming or negligible, and it is neither.
    """
    fig, axes = plt.subplots(1, 2, figsize=(8.4, 3.4), sharey=True)

    for ax, pool in zip(axes, ("100", "1000"), strict=True):
        selected = [r for r in rows if r["pool_per_interest"] == pool]
        labels = [SNAPSHOT_LABELS[r["snapshot"]] for r in selected]
        dense = [float(r["dense_R@100"]) for r in selected]
        union = [float(r["union_R@100"]) for r in selected]
        positions = range(len(selected))
        width = 0.36

        ax.bar(
            [p - width / 2 for p in positions],
            dense,
            width,
            label="Dense pool (deployed)",
            color=DENSE,
            edgecolor="white",
        )
        ax.bar(
            [p + width / 2 for p in positions],
            union,
            width,
            label="Union pool",
            color=UNION,
            edgecolor="white",
        )

        for position, row in zip(positions, selected, strict=True):
            delta = float(row["delta_pct_R@100"])
            ax.annotate(
                f"{delta:+.0f}%",
                xy=(position, max(dense[position], union[position])),
                xytext=(0, 4),
                textcoords="offset points",
                ha="center",
                fontsize=8,
                color="#333333",
            )

        ax.set_xticks(list(positions))
        ax.set_xticklabels(labels)
        ax.set_title(f"pool width {pool}")
        ax.set_ylim(0, 0.85)
        ax.grid(axis="y", linewidth=0.4, alpha=0.4)
        ax.set_axisbelow(True)

    axes[0].set_ylabel("R@100")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles, labels, loc="lower center", ncol=2, frameon=False,
        bbox_to_anchor=(0.5, -0.08),
    )
    fig.suptitle(
        "Recall cost of confining BM25 to the dense-retrieved pool "
        "(LongEval-Sci, pooled scope)",
        y=1.02,
    )
    no_timestamp = {".svg": {"Date": None}, ".pdf": {"CreationDate": None}}
    for suffix in (".svg", ".pdf"):
        fig.savefig(
            HERE / f"fig-pool-recall-gap{suffix}", metadata=no_timestamp[suffix]
        )
    plt.close(fig)
    print("  wrote fig-pool-recall-gap.svg + fig-pool-recall-gap.pdf")


def main() -> None:
    with METRICS.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    fig_pool_recall_gap(rows)


if __name__ == "__main__":
    main()
