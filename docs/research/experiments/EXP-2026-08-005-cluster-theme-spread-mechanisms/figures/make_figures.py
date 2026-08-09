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

PRIMARY = "min_cluster_recall@10"
GUARDRAIL = "nDCG@10"
GINI = "cluster_gini@10"
TARGET = "imbalanced"
CONTROL = "random"

FAMILY_COLOUR = {
    "reference": "#009E73",
    "null": "#999999",
    "individual": "#0072B2",
    "combined": "#CC79A7",
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


def _rows(rows, *, grouping, measure):
    """Arms in CSV order for one (grouping, measure) cell — order is the grid's."""
    out = []
    for row in rows:
        if (
            row["grouping"] == grouping
            and row["measure"] == measure
            and row["baseline"] == "clustered_profile"
        ):
            out.append(row)
    return out


def _label(arm: str) -> str:
    return arm.replace("spread_", "").replace("_profile", "")


def fig_mechanism_primary(rows: list[dict]) -> None:
    """The decision-rule figure: each mechanism's primary-metric delta and CI.

    A forest plot rather than bars, because the CI is the finding — an arm whose
    interval crosses the zero line has not been shown to help, however large its
    point estimate.
    """
    cells = _rows(rows, grouping=TARGET, measure=PRIMARY)
    if not cells:
        return
    fig, ax = plt.subplots(figsize=(6.4, 0.36 * len(cells) + 1.4))
    ax.axvline(0, color="#888888", lw=0.9, zorder=0)

    seen: set[str] = set()
    for i, row in enumerate(reversed(cells)):
        delta = float(row["delta"])
        low, high = float(row["ci_low"]), float(row["ci_high"])
        family = row["family"]
        colour = FAMILY_COLOUR.get(family, "#333333")
        ax.plot(
            [low, high], [i, i], color=colour, lw=1.6, solid_capstyle="round", zorder=2
        )
        ax.plot(
            [delta],
            [i],
            "o",
            color=colour,
            markersize=5,
            zorder=3,
            label=family if family not in seen else None,
        )
        seen.add(family)

    ax.set_yticks(range(len(cells)))
    ax.set_yticklabels([_label(row["arm"]) for row in reversed(cells)])
    ax.set_xlabel(f"Δ {PRIMARY}  (arm − clustered baseline), `{TARGET}` profiles")
    ax.set_title("Does the mechanism serve the worst-off theme better?")
    ax.legend(frameon=False, loc="lower right")
    ax.grid(axis="x", linewidth=0.4, alpha=0.4)
    ax.set_axisbelow(True)
    _save(fig, "fig-mechanism-primary")


def fig_spread_vs_relevance(rows: list[dict]) -> None:
    """The trade-off plane: evenness bought against relevance given up.

    x is the change in per-theme inequality (negative = more even, which is the
    goal); y is the change in nDCG@10. The shaded band is the pre-registered
    relevance budget, so an arm outside it failed the guardrail by construction.
    """
    gini = {row["arm"]: row for row in _rows(rows, grouping=TARGET, measure=GINI)}
    ndcg = {row["arm"]: row for row in _rows(rows, grouping=TARGET, measure=GUARDRAIL)}
    shared = [arm for arm in gini if arm in ndcg]
    if not shared:
        return

    fig, ax = plt.subplots(figsize=(6.2, 4.4))
    ax.axhline(0, color="#cccccc", lw=0.8, zorder=0)
    ax.axvline(0, color="#cccccc", lw=0.8, zorder=0)

    seen: set[str] = set()
    for arm in shared:
        x = float(gini[arm]["delta"])
        y = float(ndcg[arm]["delta"])
        family = gini[arm]["family"]
        colour = FAMILY_COLOUR.get(family, "#333333")
        ax.scatter(
            x,
            y,
            s=42,
            color=colour,
            zorder=3,
            label=family if family not in seen else None,
        )
        seen.add(family)
        ax.annotate(
            _label(arm),
            (x, y),
            textcoords="offset points",
            xytext=(5, 4),
            fontsize=7,
            color="#444444",
        )

    ax.set_xlabel(f"Δ {GINI}  (negative = themes more evenly served)")
    ax.set_ylabel(f"Δ {GUARDRAIL}  (negative = relevance given up)")
    ax.set_title("What each mechanism trades, on `imbalanced` profiles")
    ax.legend(frameon=False, loc="best")
    ax.grid(linewidth=0.4, alpha=0.4)
    ax.set_axisbelow(True)
    _save(fig, "fig-spread-vs-relevance")


def fig_target_vs_control(rows: list[dict]) -> None:
    """Falsifier 1: is the gain about themes, or about the operator?

    `random` holds the same interests in a meaningless partition. A mechanism that
    moves the metric just as much there is exploiting the shape of the operator,
    not the semantics of a theme, and no theme-awareness claim follows from it.
    """
    target = {row["arm"]: row for row in _rows(rows, grouping=TARGET, measure=PRIMARY)}
    control = {
        row["arm"]: row for row in _rows(rows, grouping=CONTROL, measure=PRIMARY)
    }
    shared = [arm for arm in target if arm in control]
    if not shared:
        return

    fig, ax = plt.subplots(figsize=(6.8, 3.9))
    ax.axhline(0, color="#cccccc", lw=0.8, zorder=0)
    width = 0.38
    for i, arm in enumerate(shared):
        for offset, row, colour, hatch, label in (
            (-width / 2, target[arm], "#D55E00", "", f"`{TARGET}` (target)"),
            (width / 2, control[arm], "#999999", "//", f"`{CONTROL}` (control)"),
        ):
            ax.bar(
                i + offset,
                float(row["delta"]),
                width,
                color=colour,
                hatch=hatch,
                edgecolor="white",
                linewidth=0.6,
                label=label if i == 0 else None,
            )

    ax.set_xticks(range(len(shared)))
    ax.set_xticklabels([_label(arm) for arm in shared], rotation=35, ha="right")
    ax.set_ylabel(f"Δ {PRIMARY}")
    ax.set_title("Target condition against the meaningless-partition control")
    ax.legend(frameon=False)
    ax.grid(axis="y", linewidth=0.4, alpha=0.4)
    ax.set_axisbelow(True)
    _save(fig, "fig-target-vs-control")


def main() -> None:
    rows = list(csv.DictReader(METRICS.open(encoding="utf-8")))
    fig_mechanism_primary(rows)
    fig_spread_vs_relevance(rows)
    fig_target_vs_control(rows)
    print(
        "Wrote fig-mechanism-primary, fig-spread-vs-relevance, fig-target-vs-control"
    )


if __name__ == "__main__":
    main()
