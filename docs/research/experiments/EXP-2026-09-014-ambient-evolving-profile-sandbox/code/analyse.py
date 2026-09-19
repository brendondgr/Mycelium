"""EXP-2026-09-014's metrics and table, from the harness's output.

Reads ``data/exp014-run3.json`` (registered) and ``data/exp014-run4.json``
(post hoc), trimmed copies of ``python -m sandbox.ambient nights`` output;
writes ``data/metrics.json``, ``data/metrics.csv`` and ``tables/summary.md``.
Runs 1 and 2 produced no valid output (see ISSUES.md).

    python3 docs/research/experiments/EXP-2026-09-014-ambient-evolving-profile-sandbox/code/analyse.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
RUNS = {
    "run3": "registered",
    "run4": "post hoc: forgotten evidence leaves at once",
}


def main() -> None:
    metrics: dict[str, dict] = {}
    for run, label in RUNS.items():
        data = json.loads((HERE / "data" / f"exp014-{run}.json").read_text())
        nights = data["metrics"]["nights"]
        drift = data["metrics"]["drift"]
        low, high = drift["0.15"], drift["1.0"]
        metrics[run] = {
            "label": label,
            "violations_total": nights["violations_total"],
            "violations": nights["violations"],
            "said_yes": nights["said_yes"],
            "said_no": nights["said_no"],
            "faded": nights["faded"],
            "reinforced_topics": nights["reinforced_topics"],
            "reinforced_still_active": nights["reinforced_still_active"],
            "forgotten_people": nights["forgotten_people"],
            "context_version_moves": nights["context_version_moves"],
            "people_with_explorations": low["people"],
            "declared_slate_jaccard_mean": low["declared_slate_jaccard_mean"],
            "declared_slate_jaccard_min": low["declared_slate_jaccard_min"],
            "exploration_slate_precision_mean": low["exploration_slate_precision_mean"],
            "exploration_own_papers_at_top_mean": low.get("exploration_own_papers_at_top_mean"),
            "displaced_top25_w015_mean": low["declared_displaced_from_top25_mean"],
            "displaced_top25_w015_max": low["declared_displaced_from_top25_max"],
            "displaced_top25_w1_mean": high["declared_displaced_from_top25_mean"],
            "displaced_top25_w1_max": high["declared_displaced_from_top25_max"],
            "minutes": round(sum(data["timings"].values()) / 60, 1),
        }
    (HERE / "data" / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    keys = [k for k in next(iter(metrics.values())) if k not in ("label", "violations")]
    with (HERE / "data" / "metrics.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["run", *keys])
        for run, row in metrics.items():
            writer.writerow([run, *(row[k] for k in keys)])
    shown = [
        "violations_total",
        "faded",
        "reinforced_still_active",
        "declared_slate_jaccard_mean",
        "exploration_slate_precision_mean",
        "exploration_own_papers_at_top_mean",
        "displaced_top25_w015_mean",
        "displaced_top25_w1_mean",
        "minutes",
    ]
    lines = ["| Run | " + " | ".join(shown) + " |", "|---|" + "---:|" * len(shown)]
    for run, row in metrics.items():
        lines.append(
            f"| {run} — {row['label']} | " + " | ".join(str(row[k]) for k in shown) + " |"
        )
    (HERE / "tables" / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
