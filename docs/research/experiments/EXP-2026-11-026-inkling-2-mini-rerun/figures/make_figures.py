"""Regenerate this folder's figures from `../data/compare.csv` (no number is typed here).

    python3 make_figures.py

`code/analyse.py` writes compare.csv: one row per (part, group, model, metric)
with the count k of n, the value, and a Wilson 95% interval where the value
is a share of runs. Gemma 4 31B's and Qwen 3.8 27B's rows are the paper's,
read from the source experiments; Inkling 2 Mini's are this experiment's. A
figure whose part has no Inkling rows yet is skipped.

fig-leaks-code-vs-prompt   share of replies that leaked, rules in code vs in the
                           prompt: access probes (part 3) and collaborator
                           search (part 5), with Wilson 95% intervals.
fig-full-credit-by-kind    full-credit rate per question kind, Mylo as shipped
                           (part 4, arm a), with Wilson 95% intervals.
fig-latency                median seconds per answer, model calls and tokens
                           per turn, by question group, one at a time (part 2).
fig-memory-lifecycle       leaks over valid runs per memory-lifecycle probe
                           (part 6).

Colours: the three models take categorical slots 1–3 of the dataviz reference
palette, in a fixed order (validated all-pairs, light surface). The third slot
is below 3:1 contrast on white, so every bar carries a legend entry and the
numbers are in RESULTS.md's tables.
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

HERE = Path(__file__).resolve().parent
COMPARE = HERE.parent / "data" / "compare.csv"
MODELS = {"Gemma 4 31B": "#2a78d6", "Qwen 3.8 27B": "#eb6834", "Inkling 2 Mini": "#1baf7a"}
INK = "Inkling 2 Mini"
INK_TEXT = "#0b0b0b"
MUTED = "#52514e"
GRID = "#e4e3df"

plt.rcParams.update({"font.size": 8, "axes.edgecolor": MUTED, "axes.labelcolor": INK_TEXT,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.linewidth": 0.6,
                     "svg.fonttype": "none", "pdf.fonttype": 42})


def load():
    rows = list(csv.DictReader(COMPARE.open()))
    for r in rows:
        for f in ("k", "n", "value", "lo", "hi"):
            r[f] = float(r[f]) if r[f] not in ("", None) else None
    return rows


def get(rows, part, group, model, metric):
    return next((r for r in rows if r["part"] == part and r["group"] == group
                 and r["model"] == model and r["metric"] == metric), None)


def has_ink(rows, part):
    return any(r["part"] == part and r["model"] == INK for r in rows)


def style(ax, ylabel=None):
    ax.spines[["top", "right"]].set_visible(False)
    ax.yaxis.grid(True, color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    if ylabel:
        ax.set_ylabel(ylabel)


def grouped(ax, rows, part, groups, metric, labels, width=0.26, counts=False):
    """Bars per group, one per model, with Wilson whiskers where present."""
    for i, (model, colour) in enumerate(MODELS.items()):
        for j, g in enumerate(groups):
            r = get(rows, part, g, model, metric)
            if r is None or r["value"] is None:
                continue
            x = j + (i - 1) * width
            v = r["value"]
            err = None
            if r["lo"] is not None:
                err = [[v - r["lo"]], [r["hi"] - v]]
            ax.bar(x, v, width, color=colour, edgecolor="white", lw=1,
                   label=model if j == 0 else None, yerr=err, capsize=1.5,
                   error_kw={"lw": 0.7, "ecolor": MUTED})
            if counts and r["k"] is not None:
                top = r["hi"] if r["hi"] is not None else v
                ax.text(x, top + 0.02, f"{int(r['k'])}/{int(r['n'])}", ha="center", va="bottom",
                        fontsize=5.5, color=MUTED, rotation=90)
    ax.set_xticks(range(len(groups)))
    ax.set_xticklabels(labels)


def legend(fig):
    handles, names = fig.axes[0].get_legend_handles_labels()
    fig.legend(handles, names, frameon=False, ncol=3, loc="upper center", bbox_to_anchor=(0.5, 1.0))


def save(fig, name):
    for ext in ("svg", "pdf"):
        fig.savefig(HERE / f"{name}.{ext}", bbox_inches="tight")
    plt.close(fig)
    print("wrote", name)


def fig_leaks(rows):
    panels = [(p, t) for p, t in (("p3", "Access probes (part 3)"), ("p5", "Collaborator search (part 5)"))
              if has_ink(rows, p)]
    if not panels:
        return
    fig, axes = plt.subplots(1, len(panels), figsize=(3.4 * len(panels), 3.0), squeeze=False)
    for ax, (part, title) in zip(axes[0], panels):
        metric = "leaks" if part == "p3" else "named"
        grouped(ax, rows, part, ["gate", "prompt_only"], metric, ["rules in code", "rules in the prompt"],
                counts=True)
        ax.set_ylim(0, 1.15)
        ax.set_title(title, fontsize=8, color=INK_TEXT)
        style(ax, "share of replies that leaked" if ax is axes[0][0] else None)
    legend(fig)
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    save(fig, "fig-leaks-code-vs-prompt")


def fig_full_credit(rows):
    if not has_ink(rows, "p4"):
        return
    kinds = ["field", "list", "project", "people", "join", "unanswerable", "answerable"]
    fig, ax = plt.subplots(figsize=(7.0, 3.0))
    grouped(ax, rows, "p4", [f"a.{k}" for k in kinds], "full_credit",
            kinds[:-1] + ["all answerable"])
    ax.set_ylim(0, 1.05)
    ax.axvline(len(kinds) - 1.5, color=GRID, lw=0.8)
    style(ax, "full credit (share of runs)")
    legend(fig)
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    save(fig, "fig-full-credit-by-kind")


def fig_latency(rows):
    if not has_ink(rows, "p2"):
        return
    groups = ["idle.single", "idle.few", "idle.compound"]
    labels = ["one lookup", "a few", "compound"]
    panels = [("median_s", "median seconds to an answer"), ("model_calls", "model calls per turn (median)"),
              ("tokens", "tokens per turn (median)")]
    fig, axes = plt.subplots(1, 3, figsize=(9.0, 2.8))
    for ax, (metric, ylabel) in zip(axes, panels):
        grouped(ax, rows, "p2", groups, metric, labels)
        style(ax, ylabel)
        ax.set_ylim(bottom=0)
        if metric == "tokens":
            ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y / 1000:g}k"))
    legend(fig)
    fig.text(0.5, -0.02, "one question at a time, idle server (part 2)", ha="center", color=MUTED)
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    save(fig, "fig-latency")


LIFE = [("delete_thread", "delete the chat (lowered thresholds)"),
        ("delete_thread_production", "delete the chat (default settings)"),
        ("delete_obs", "delete what was learned"),
        ("message", "delete the message"),
        ("forget", "ask Mylo to forget"),
        ("optout", "learning switched off"),
        ("excluded", "recording excluded"),
        ("isolation", "another member asks")]


def fig_memory(rows):
    if not has_ink(rows, "p6"):
        return
    probes = [(k, label) for k, label in LIFE if any(get(rows, "p6", k, m, "leaks") for m in MODELS)]
    fig, ax = plt.subplots(figsize=(6.0, 0.42 * len(probes) + 0.9))
    h = 0.26
    for i, (model, colour) in enumerate(MODELS.items()):
        for j, (key, _) in enumerate(probes):
            r = get(rows, "p6", key, model, "leaks")
            if r is None:
                continue
            y = j + (i - 1) * h
            v = r["value"]
            ax.barh(y, v, h, color=colour, edgecolor="white", lw=1, label=model if j == 0 else None,
                    xerr=[[v - r["lo"]], [r["hi"] - v]], capsize=1.5, error_kw={"lw": 0.7, "ecolor": MUTED})
            ax.text(r["hi"] + 0.02, y, f"{int(r['k'])}/{int(r['n'])}", va="center", fontsize=5.5, color=MUTED)
    ax.set_yticks(range(len(probes)))
    ax.set_yticklabels([label for _, label in probes])
    ax.invert_yaxis()
    ax.set_xlim(0, 1.15)
    ax.spines[["top", "right"]].set_visible(False)
    ax.xaxis.grid(True, color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    ax.set_xlabel("share of valid runs that leaked")
    legend(fig)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    save(fig, "fig-memory-lifecycle")


def main():
    rows = load()
    for f in (fig_leaks, fig_full_credit, fig_latency, fig_memory):
        f(rows)


if __name__ == "__main__":
    main()
