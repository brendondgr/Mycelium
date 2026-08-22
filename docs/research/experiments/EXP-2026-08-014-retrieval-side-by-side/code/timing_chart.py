"""The timing figure, kept separate so both the booklet and `make figures` build it.

`code/build_pdf.py` needs reportlab; the research-record figure runner
(`scripts/research`) has matplotlib and not reportlab. Putting the chart here —
matplotlib only, no other dependency — lets the booklet embed it and
`figures/make_figures.py` regenerate it, from the same code and the same
`data/lists.json`. Two chart implementations would be two charts.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

EXP_DIR = Path(__file__).resolve().parent.parent

#: Fixed so an unchanged figure regenerates byte-identically and the record's
#: staleness check does not fire on noise.
NO_TIMESTAMP = {".svg": {"Date": None}, ".pdf": {"CreationDate": None}, ".png": {}}


def medians_by_letter(data: dict) -> dict[str, float]:
    """Median seconds per query for each blinded arm, from the recorded rows."""
    by_arm: dict[str, list[float]] = {}
    for row in data["timing"]:
        by_arm.setdefault(row["arm"], []).append(row["seconds"])
    labels = data["blind_labels"]
    return {
        letter: statistics.median(by_arm.get(labels[letter], [0.0]))
        for letter in sorted(labels)
    }


def make_chart(medians: dict[str, float], *, out_dir: Path, formats=(".png",)) -> Path:
    plt.rcParams.update({
        "svg.hashsalt": "mycelium-research-record",
        "font.size": 9,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.dpi": 200,
        "savefig.bbox": "tight",
        "pdf.fonttype": 42,
        "svg.fonttype": "none",
    })
    letters = sorted(medians)
    values = [max(medians[letter], 1e-4) for letter in letters]
    fig, ax = plt.subplots(figsize=(11.5, 4.9))
    bars = ax.bar(letters, values, color="#0072B2", width=0.62)
    ax.set_yscale("log")
    ax.set_ylabel("median seconds per query (log)")
    ax.set_xlabel("arm (blinded)")
    ax.set_title("Query-time cost per retrieval arm")
    ax.grid(axis="y", color="#dddddd", lw=0.6)
    ax.set_axisbelow(True)
    for bar, value in zip(bars, values, strict=True):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            value * 1.12,
            f"{value:.2f}s" if value >= 0.01 else f"{value * 1000:.0f}ms",
            ha="center",
            fontsize=8,
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    for suffix in formats:
        fig.savefig(out_dir / f"fig-timing{suffix}", metadata=NO_TIMESTAMP[suffix])
    plt.close(fig)
    return out_dir / "fig-timing.png"


def build(out_dir: Path | None = None, formats=(".png", ".svg", ".pdf")) -> Path:
    data = json.loads((EXP_DIR / "data" / "lists.json").read_text())
    return make_chart(
        medians_by_letter(data), out_dir=out_dir or (EXP_DIR / "figures"), formats=formats
    )


if __name__ == "__main__":
    print(f"  wrote {build().name} (+ .svg, .pdf)")
