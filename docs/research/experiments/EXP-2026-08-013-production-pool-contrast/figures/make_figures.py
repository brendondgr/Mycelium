"""Regenerate this experiment's figures from `../data/*.csv`.

    python make_figures.py

No number is written in this file. Panel values are computed from the per-interest
and per-target rows `../code/run.py` recorded, so a figure that disagrees with
`RESULTS.md` means the CSVs changed, not that somebody edited a plot.
"""

from __future__ import annotations

import csv
import statistics
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"

# Okabe-Ito, matching the rest of the record.
PAPERS = "#0072B2"
OPPORTUNITIES = "#D55E00"
CORPUS_WIDE = "#009E73"
GREY = "#666666"

#: The two thresholds `PROTOCOL.md` fixed before the run.
INERT_AT = 0.90
LIVE_AT = 0.50

ARMS = (
    ("a2p_union_prod", "union\n(shippable)"),
    ("a2_union_harness", "union\n(harness arm)"),
    ("a4_union_fts_or", "union via FTS\n(OR)"),
    ("a3_union_fts", "union via FTS\n(`websearch`)"),
)

plt.rcParams.update({
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
})

NO_TIMESTAMP = {".svg": {"Date": None}, ".pdf": {"CreationDate": None}}


def read(name: str) -> list[dict]:
    with (DATA / name).open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def save(fig, slug: str) -> None:
    for suffix in (".svg", ".pdf"):
        fig.savefig(HERE / f"{slug}{suffix}", metadata=NO_TIMESTAMP[suffix])
    plt.close(fig)
    print(f"  wrote {slug}.svg + {slug}.pdf")


def fig_reachability(rows: list[dict]) -> None:
    """How much of corpus-wide BM25's top-100 the dense pool already holds.

    Plotted against corpus size because that is what the quantity is a function
    of: a fixed 100-per-interest pull covers a small gather batch and cannot
    cover a corpus. Both deployed regimes are marked separately from the
    corpus-wide paper scope, which the feed does not use.
    """
    by_regime: dict[str, list[float]] = {}
    size: dict[str, int] = {}
    for row in rows:
        value = row["bm25_reachability"]
        if value in ("", "None"):
            continue
        by_regime.setdefault(row["regime"], []).append(float(value))
        size[row["regime"]] = int(row["scope_size"])

    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    ax.axhspan(INERT_AT, 1.0, color=GREY, alpha=0.10)
    ax.axhline(INERT_AT, color=GREY, lw=0.8, ls="--")
    ax.axhline(LIVE_AT, color=GREY, lw=0.8, ls=":")
    ax.text(
        330, INERT_AT + 0.015, "pre-registered: inert at ≥ 0.90",
        fontsize=7.5, color=GREY,
    )
    ax.text(330, LIVE_AT + 0.015, "live at ≤ 0.50", fontsize=7.5, color=GREY)

    groups = {
        "R1: papers, one gather day (deployed)": (PAPERS, "o"),
        "R3: opportunities, whole corpus (deployed)": (OPPORTUNITIES, "s"),
        "R2: papers, whole corpus": (CORPUS_WIDE, "D"),
    }
    prefixes = {"R1:": 0, "R3:": 1, "R2:": 2}
    for label, (colour, marker) in groups.items():
        index = list(groups).index(label)
        xs, mids, los, his = [], [], [], []
        for regime, values in by_regime.items():
            if prefixes[regime[:3]] != index:
                continue
            ordered = sorted(values)
            xs.append(size[regime])
            mids.append(statistics.median(ordered))
            los.append(ordered[len(ordered) // 4])
            his.append(ordered[(len(ordered) * 3) // 4])
        if not xs:
            continue
        order = sorted(range(len(xs)), key=lambda i: xs[i])
        xs = [xs[i] for i in order]
        mids = [mids[i] for i in order]
        errs = [
            [mids[i] - los[order[i]] for i in range(len(order))],
            [his[order[i]] - mids[i] for i in range(len(order))],
        ]
        ax.errorbar(
            xs, mids, yerr=errs, fmt=marker, color=colour, ms=5, lw=0,
            elinewidth=1.0, capsize=2.5, label=label,
        )

    ax.set_xscale("log")
    ax.set_xlim(250, 60_000)
    ax.set_ylim(0, 1.0)
    ax.set_xlabel("documents in scope for one run (log)")
    ax.set_ylabel("BM25 reachability@100  (median, IQR)")
    ax.set_title("What the dense-restricted pool already reaches")
    ax.legend(loc="lower left", frameon=False)
    save(fig, "fig-reachability-vs-corpus")


def fig_entrants(rows: list[dict]) -> None:
    """Documents a wider pool adds to what a reader sees — under two gates.

    The deployed surfacing gate compares `best_cosine` against the match
    threshold, and `best_cosine` is populated only by the dense channel, so a
    union-only candidate is compared at 0.0. The left bars are what that costs.
    """
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    labels = [label for _arm, label in ARMS]
    positions = range(len(ARMS))
    deployed = [
        sum(int(r[f"{arm}__entrants_deployed_union_only"]) for r in rows)
        for arm, _ in ARMS
    ]
    completed = [
        sum(int(r[f"{arm}__entrants_union_only"]) for r in rows) for arm, _ in ARMS
    ]
    width = 0.38
    ax.bar(
        [p - width / 2 for p in positions], deployed, width,
        color=GREY, label="deployed gate (as the code stands)",
    )
    ax.bar(
        [p + width / 2 for p in positions], completed, width,
        color=PAPERS, label="gate completed over the whole pool",
    )
    for position, value in zip(positions, deployed, strict=True):
        ax.text(
            position - width / 2, 120, str(value), ha="center", fontsize=8,
            color=GREY, fontweight="bold",
        )
    ax.set_xticks(list(positions))
    ax.set_xticklabels(labels)
    ax.set_ylabel("union-only documents surfaced\n(sum over 126 target × regime pairs)")
    ax.set_title("A wider pool reaches the reader only if the cosine gate is fixed too")
    ax.legend(frameon=False, loc="upper right")
    save(fig, "fig-entrants-by-gate")


if __name__ == "__main__":
    fig_reachability(read("per_interest.csv"))
    fig_entrants(read("metrics.csv"))
