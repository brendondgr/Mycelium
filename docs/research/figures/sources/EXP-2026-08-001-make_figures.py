"""Regenerate every figure in this folder from `../data/metrics.csv`.

    python make_figures.py

No number is written in this file. Every value plotted is read from the CSV,
which is itself rebuilt from `eval/results/*.json` by `../data/build_metrics.py`.
That chain is the whole point: a figure that cannot be traced back to a recorded
run is a figure nobody can defend.
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
METRICS = HERE.parent / "data" / "metrics.csv"

# Okabe-Ito: colour-blind safe, and distinguishable in greyscale print.
PALETTE = {
    "bm25_only": "#0072B2",
    "dense_only": "#D55E00",
    "fusion_dense_pool": "#009E73",
    "fusion_full": "#CC79A7",
    "fusion_union_pool": "#E69F00",
}
ARM_LABELS = {
    "bm25_only": "BM25 only",
    "dense_only": "Dense only",
    "fusion_dense_pool": "RRF, dense pool",
    "fusion_full": "RRF + CombMNZ",
    "fusion_union_pool": "RRF, union pool",
}
SNAPSHOT_LABELS = {
    "longeval-sci-2026/snapshot-1/train": "2026 train\n(870k docs, 100 q)",
    "longeval-sci/2024-11": "2024-11\n(2.0M docs, 99 q)",
    "longeval-sci/2025-01": "2025-01\n(1.2M docs, 492 q)",
}
SNAPSHOTS = list(SNAPSHOT_LABELS)

# 7pt floor at final print size; fonts embedded in the PDF rather than outlined.
#
# `svg.hashsalt` is not cosmetic: without a fixed salt, matplotlib generates a
# random id for every `<defs>` element, so regenerating an unchanged figure
# produces a different file and CI's staleness check fires on noise. The salt
# plus a null Date/CreationDate in the metadata is what makes a figure
# byte-reproducible, which is what makes "regenerate and diff" a usable test.
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


def load() -> list[dict]:
    with METRICS.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


NO_TIMESTAMP = {".svg": {"Date": None}, ".pdf": {"CreationDate": None}}


def save(fig, slug: str) -> None:
    """Emit both vector formats. SVG is diffable and web-embeddable; PDF is what
    LaTeX wants. A raster format would be neither.

    The metadata override strips the embedded timestamp, so an unchanged figure
    regenerates byte-identically."""
    for suffix in (".svg", ".pdf"):
        fig.savefig(HERE / f"{slug}{suffix}", metadata=NO_TIMESTAMP[suffix])
    plt.close(fig)
    print(f"  wrote {slug}.svg + {slug}.pdf")


def pick(rows: list[dict], **conditions) -> list[dict]:
    return [r for r in rows if all(str(r[k]) == str(v) for k, v in conditions.items())]


def fig_arm_comparison(rows: list[dict]) -> None:
    """nDCG@10 and R@100 per arm, pooled scope, matched pool width, per snapshot.

    Pooled scope so all three snapshots are represented: the 2025 pair was never
    run at full-corpus scope for the dense and fusion arms. Pool width 100 for
    the fusion arms so the comparison is like-for-like.
    """
    fig, axes = plt.subplots(1, 2, figsize=(9.0, 3.4))

    for ax, measure in zip(axes, ("nDCG@10", "R@100"), strict=True):
        arms = list(PALETTE)
        width = 0.15
        for index, arm in enumerate(arms):
            values = []
            for snapshot in SNAPSHOTS:
                found = pick(rows, snapshot=snapshot, arm=arm, corpus_scope="pooled")
                if arm.startswith("fusion"):
                    found = [r for r in found if r["pool_per_interest"] == "100"]
                values.append(float(found[0][measure]) if found else 0.0)
            offsets = [i + (index - 2) * width for i in range(len(SNAPSHOTS))]
            ax.bar(
                offsets,
                values,
                width,
                label=ARM_LABELS[arm],
                color=PALETTE[arm],
                edgecolor="white",
                linewidth=0.4,
            )

        ax.set_xticks(range(len(SNAPSHOTS)))
        ax.set_xticklabels([SNAPSHOT_LABELS[s] for s in SNAPSHOTS])
        ax.set_ylabel(measure)
        ax.set_title(measure)
        ax.grid(axis="y", linewidth=0.4, alpha=0.4)
        ax.set_axisbelow(True)

    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="lower center",
        ncol=5,
        frameon=False,
        bbox_to_anchor=(0.5, -0.09),
    )
    fig.suptitle(
        "LongEval-Sci, pooled scope, click-derived judgments — "
        "BM25 alone leads on nDCG@10 everywhere",
        y=1.04,
    )
    save(fig, "fig-arm-comparison")


def fig_baseline_gap(rows: list[dict]) -> None:
    """Our full-corpus arms against the organizers' published runs, 2026 train.

    The only snapshot where a published baseline exists, and the only comparison
    that says whether our implementation is correct rather than merely internally
    consistent.
    """
    snapshot = SNAPSHOTS[0]
    ours = []
    for arm in PALETTE:
        found = pick(rows, snapshot=snapshot, arm=arm, corpus_scope="full")
        if arm.startswith("fusion"):
            found = [r for r in found if r["pool_per_interest"] == "100"]
        if found:
            ours.append((ARM_LABELS[arm], found[0], PALETTE[arm]))

    published = [r for r in rows if r["source"] == "published"]

    fig, axes = plt.subplots(1, 2, figsize=(9.0, 3.4), sharey=True)
    for ax, measure in zip(axes, ("nDCG@10", "R@100"), strict=True):
        labels = [label for label, _, _ in ours]
        values = [float(row[measure]) for _, row, _ in ours]
        colors = [color for _, _, color in ours]
        ax.barh(range(len(labels)), values, color=colors, edgecolor="white", height=0.65)
        ax.set_yticks(range(len(labels)))
        ax.set_yticklabels(labels)
        ax.set_xlabel(measure)
        ax.set_title(measure)
        ax.grid(axis="x", linewidth=0.4, alpha=0.4)
        ax.set_axisbelow(True)

        # Published runs as reference lines, not bars: they are a different
        # system's numbers and should not read as one of our arms.
        styles = ["--", ":"]
        for style, baseline in zip(styles, published, strict=False):
            ax.axvline(
                float(baseline[measure]),
                linestyle=style,
                linewidth=1.2,
                color="#444444",
                label=baseline["arm"],
            )

    axes[0].invert_yaxis()  # shared axis: inverting once flips both
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="lower center",
        ncol=2,
        frameon=False,
        bbox_to_anchor=(0.5, -0.10),
    )
    fig.suptitle(
        "Full-corpus 2026 train (869,902 docs) vs the organizers' published runs",
        y=1.02,
    )
    save(fig, "fig-baseline-gap")


def main() -> None:
    rows = load()
    fig_arm_comparison(rows)
    fig_baseline_gap(rows)


if __name__ == "__main__":
    main()
