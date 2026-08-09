"""Regenerate this experiment's figures from `../data/metrics.csv`.

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

PRIMARY = "min_cluster_recall@10"
GUARDRAIL = "nDCG@10"

# Okabe-Ito, matched to the arm colours used by EXP-2026-08-001 and -002.
GROUPING_COLOUR = {
    "coherent": "#0072B2",
    "imbalanced": "#D55E00",
    "random": "#999999",
}
GROUPING_ORDER = ("coherent", "imbalanced", "random")
BETA_MARKER = {"0.0": "o", "0.15": "s", "0.3": "^"}

# `svg.hashsalt` fixes matplotlib's otherwise-random `<defs>` ids so an unchanged
# figure regenerates byte-identically, which is what lets CI diff for staleness.
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


def _beta_key(value: str) -> str:
    """Normalise `0.3` / `0.30` to the key the marker map uses."""
    return str(float(value))


def _find(rows: list[dict], grouping: str, beta: str, measure: str) -> dict | None:
    for row in rows:
        if (
            row["grouping"] == grouping
            and _beta_key(row["beta"]) == _beta_key(beta)
            and row["measure"] == measure
        ):
            return row
    return None


#: The two backends spell the timestamp key differently, and nulling the wrong
#: one leaves a live clock in the file — which makes `make figures-check` fail on
#: an unchanged figure. Matched to EXP-2026-08-002's generator.
NO_TIMESTAMP = {".svg": {"Date": None}, ".pdf": {"CreationDate": None}}


def _save(fig, slug: str) -> None:
    for suffix in (".svg", ".pdf"):
        fig.savefig(HERE / f"{slug}{suffix}", metadata=NO_TIMESTAMP[suffix])
    plt.close(fig)


def fig_cluster_coverage_tradeoff(rows: list[dict]) -> None:
    """Coverage gain against relevance cost — the two-axis picture, not one number.

    A point above and right of the origin is a free win; below and right is the
    tradeoff C-003 would have to be rewritten as. The `random` points are the
    control: they belong at the origin, and if they do not, the metric is
    measuring something other than cluster structure.
    """
    fig, ax = plt.subplots(figsize=(5.6, 4.4))
    ax.axhline(0, color="#cccccc", lw=0.8, zorder=0)
    ax.axvline(0, color="#cccccc", lw=0.8, zorder=0)

    for grouping in GROUPING_ORDER:
        for beta in BETA_MARKER:
            coverage = _find(rows, grouping, beta, PRIMARY)
            relevance = _find(rows, grouping, beta, GUARDRAIL)
            if not coverage or not relevance:
                continue
            x, y = float(coverage["delta"]), float(relevance["delta"])
            ax.errorbar(
                x,
                y,
                # `max(0, ...)`: a percentile interval can sit fractionally to one
                # side of the point estimate, and matplotlib rejects a negative
                # error bar outright rather than clipping it.
                xerr=[
                    [max(0.0, x - float(coverage["ci_low"]))],
                    [max(0.0, float(coverage["ci_high"]) - x)],
                ],
                yerr=[
                    [max(0.0, y - float(relevance["ci_low"]))],
                    [max(0.0, float(relevance["ci_high"]) - y)],
                ],
                fmt=BETA_MARKER[beta],
                color=GROUPING_COLOUR[grouping],
                ecolor=GROUPING_COLOUR[grouping],
                elinewidth=0.9,
                capsize=2,
                markersize=6,
                alpha=0.9,
            )

    ax.set_xlabel(f"Δ {PRIMARY}  (clustered − flat)")
    ax.set_ylabel(f"Δ {GUARDRAIL}  (clustered − flat)")
    ax.set_title("Coverage gain against relevance cost, with 95% paired-bootstrap CIs")

    handles = [
        plt.Line2D([], [], color=GROUPING_COLOUR[g], marker="o", ls="", label=g)
        for g in GROUPING_ORDER
    ] + [
        plt.Line2D([], [], color="#444444", marker=m, ls="", label=f"β = {b}")
        for b, m in BETA_MARKER.items()
    ]
    ax.legend(handles=handles, ncol=2, frameon=False, loc="best")
    _save(fig, "fig-cluster-coverage-tradeoff")


def fig_cluster_beta_sweep(rows: list[dict]) -> None:
    """The primary delta against β, per grouping mode.

    β is on the x-axis because the prediction is directional: at β = 0 the breadth
    bonus vanishes and the arms differ only by mean-vs-max, and as β rises flat
    scoring increasingly rewards the paper that touches everything shallowly. If
    C-003 describes a real mechanism, the gap widens left to right — and the
    `random` line stays flat at zero regardless.
    """
    fig, ax = plt.subplots(figsize=(5.6, 3.6))
    ax.axhline(0, color="#cccccc", lw=0.8, zorder=0)

    for grouping in GROUPING_ORDER:
        betas, deltas, lows, highs = [], [], [], []
        for beta in sorted(BETA_MARKER, key=float):
            found = _find(rows, grouping, beta, PRIMARY)
            if not found:
                continue
            betas.append(float(beta))
            deltas.append(float(found["delta"]))
            lows.append(float(found["ci_low"]))
            highs.append(float(found["ci_high"]))
        if not betas:
            continue
        ax.fill_between(
            betas, lows, highs, color=GROUPING_COLOUR[grouping], alpha=0.15, lw=0
        )
        ax.plot(
            betas,
            deltas,
            marker="o",
            color=GROUPING_COLOUR[grouping],
            label=grouping,
            lw=1.6,
        )

    ax.set_xlabel("β (breadth bonus)")
    ax.set_ylabel(f"Δ {PRIMARY}  (clustered − flat)")
    ax.set_title("Does the gap widen as flat scoring rewards breadth more?")
    ax.legend(frameon=False)
    _save(fig, "fig-cluster-beta-sweep")


def main() -> None:
    rows = list(csv.DictReader(METRICS.open(encoding="utf-8")))
    fig_cluster_coverage_tradeoff(rows)
    fig_cluster_beta_sweep(rows)
    print("Wrote fig-cluster-coverage-tradeoff, fig-cluster-beta-sweep")


if __name__ == "__main__":
    main()
