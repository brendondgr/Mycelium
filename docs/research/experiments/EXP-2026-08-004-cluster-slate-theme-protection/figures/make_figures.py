"""Regenerate this experiment's figures from `../data/*.csv`.

    python make_figures.py

Every plotted value comes from the CSVs. No number appears in this file.
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
METRICS = HERE.parent / "data" / "metrics.csv"
SURFACING = HERE.parent / "data" / "surfacing.csv"

WHOLE_SET = "cluster_coverage@1000"
GROUPINGS = ("coherent", "imbalanced", "random")
GROUPING_COLOUR = {
    "coherent": "#0072B2",
    "imbalanced": "#D55E00",
    "random": "#999999",
}
ARM_COLOUR = {
    "flat_profile": "#009E73",
    "clustered_profile": "#0072B2",
    "slate_profile": "#CC79A7",
}

NO_TIMESTAMP = {".svg": {"Date": None}, ".pdf": {"CreationDate": None}}

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


def _save(fig, slug: str) -> None:
    for suffix in (".svg", ".pdf"):
        fig.savefig(HERE / f"{slug}{suffix}", metadata=NO_TIMESTAMP[suffix])
    plt.close(fig)


def _find(rows, condition, grouping, comparison, measure):
    for row in rows:
        if (
            row["condition"] == condition
            and row["grouping"] == grouping
            and row["comparison"] == comparison
            and row["measure"] == measure
        ):
            return row
    return None


def fig_slate_size_matched(rows: list[dict]) -> None:
    """The falsifier-3 figure: how much of the slate's gain survives equal slots.

    Left bar of each pair is the slate against the cluster path at *its own*
    smaller cut — the comparison that looks favourable. Right bar is the same
    slate against a cluster path given the slate's own surfaced-set size. If the
    allocation rule is doing the work, the two are similar; if the extra items
    are doing the work, the right bar collapses.
    """
    fig, ax = plt.subplots(figsize=(6.0, 3.8))
    ax.axhline(0, color="#cccccc", lw=0.8, zorder=0)

    width = 0.35
    for i, grouping in enumerate(GROUPINGS):
        unequal = _find(rows, "cut30", grouping, "slate−clustered", WHOLE_SET)
        matched = _find(rows, "matched", grouping, "slate−clustered@34", WHOLE_SET)
        if not unequal or not matched:
            continue
        for offset, row, hatch, label in (
            (-width / 2, unequal, "", "vs cluster path at a 30-item cut"),
            (width / 2, matched, "//", "vs cluster path at the slate's own size"),
        ):
            delta = float(row["delta"])
            low, high = float(row["ci_low"]), float(row["ci_high"])
            ax.bar(
                i + offset,
                delta,
                width,
                color=GROUPING_COLOUR[grouping],
                hatch=hatch,
                edgecolor="white",
                linewidth=0.6,
                label=label if i == 0 else None,
            )
            ax.errorbar(
                i + offset,
                delta,
                yerr=[[max(0.0, delta - low)], [max(0.0, high - delta)]],
                fmt="none",
                ecolor="#333333",
                elinewidth=0.9,
                capsize=3,
            )

    ax.set_xticks(range(len(GROUPINGS)))
    ax.set_xticklabels(GROUPINGS)
    ax.set_ylabel(f"Δ {WHOLE_SET}  (slate − baseline)")
    ax.set_title("Does the slate's theme coverage survive an equal number of slots?")
    ax.legend(frameon=False, loc="upper left")
    _save(fig, "fig-slate-size-matched")


def fig_slate_surfacing(rows: list[dict]) -> None:
    """What each arm actually surfaced, per condition.

    The `prod` panel is the product finding: at the deployed 250-item backstop
    every arm surfaces exactly 250 out of a ~575-candidate pool, so each theme's
    top ten is already inside the cut and the slate adds nothing at all.
    """
    conditions = ["prod", "cut30", "cut34"]
    present = [
        c for c in conditions if any(row["condition"] == c for row in rows)
    ]
    fig, axes = plt.subplots(
        1, len(present), figsize=(2.6 * len(present) + 1.2, 3.4), sharey=False
    )
    if len(present) == 1:
        axes = [axes]

    for ax, condition in zip(axes, present, strict=True):
        arms = sorted({row["arm"] for row in rows if row["condition"] == condition})
        for i, arm in enumerate(arms):
            values = [
                float(row["mean_surfaced"])
                for row in rows
                if row["condition"] == condition and row["arm"] == arm
            ]
            ax.bar(
                i,
                sum(values) / len(values),
                0.6,
                color=ARM_COLOUR.get(arm, "#888888"),
            )
        ax.set_xticks(range(len(arms)))
        ax.set_xticklabels([a.replace("_profile", "") for a in arms], rotation=20)
        ax.set_title(f"`{condition}`")
        ax.grid(axis="y", linewidth=0.4, alpha=0.4)
        ax.set_axisbelow(True)

    axes[0].set_ylabel("mean items surfaced")
    fig.suptitle(
        "Surfaced-set size per arm — the slate buys coverage with slots", y=1.03
    )
    _save(fig, "fig-slate-surfacing")


def main() -> None:
    rows = list(csv.DictReader(METRICS.open(encoding="utf-8")))
    surfacing = list(csv.DictReader(SURFACING.open(encoding="utf-8")))
    fig_slate_size_matched(rows)
    fig_slate_surfacing(surfacing)
    print("Wrote fig-slate-size-matched, fig-slate-surfacing")


if __name__ == "__main__":
    main()
