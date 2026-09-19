"""EXP-2026-09-019's table, from ``data/exp019-run1.json``.

    python3 docs/research/experiments/EXP-2026-09-019-ambient-drift-weight-ablation/code/analyse.py
"""

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
KEYS = [
    "people",
    "declared_slate_jaccard_mean",
    "declared_slate_jaccard_min",
    "declared_displaced_from_top25_mean",
    "declared_displaced_from_top25_max",
    "exploration_own_papers_at_top_mean",
]


def main() -> None:
    data = json.loads((HERE / "data" / "exp019-run1.json").read_text())
    drift = data["drift"]
    weights = sorted(drift, key=float)
    passing = [
        w
        for w in weights
        if drift[w]["declared_slate_jaccard_mean"] >= 0.95
        and drift[w]["declared_displaced_from_top25_mean"] <= 1
    ]
    metrics = {
        "per_weight": {w: {k: drift[w][k] for k in KEYS} for w in weights},
        "recommended_weight_by_rule": max(passing, key=float) if passing else None,
        "seconds": sum(data["timings"].values()),
    }
    (HERE / "data" / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    with (HERE / "data" / "metrics.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["weight", *KEYS])
        for w in weights:
            writer.writerow([w, *(drift[w][k] for k in KEYS)])
    lines = ["| Weight | " + " | ".join(KEYS) + " |", "|---:|" + "---:|" * len(KEYS)]
    lines += [f"| {w} | " + " | ".join(str(drift[w][k]) for k in KEYS) + " |" for w in weights]
    (HERE / "tables" / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(json.dumps({k: v for k, v in metrics.items() if k != "per_weight"}))


if __name__ == "__main__":
    main()
