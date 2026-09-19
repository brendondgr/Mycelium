"""Turn the graph harness's output into this experiment's metrics and table.

Reads ``data/exp010-run1.json`` (registered), ``data/exp010-run2.json`` (post
hoc: team covers from concepts only) and ``data/exp010-smoke240.json`` (the
240-person smoke, before the concept threshold), all from
``python -m sandbox.collab graph``; writes ``data/metrics.json``,
``data/metrics.csv`` and ``tables/summary.md``.

    python3 docs/research/experiments/EXP-2026-09-010-collab-graph-features-sandbox/code/analyse.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
RUNS = {
    "smoke240": "smoke, 240 people, concept 0.70",
    "run1": "registered, 600 people",
    "run2": "post hoc: covers from concepts only",
}
KEYS = (
    "violations_total",
    "searches_institution",
    "shown_institution",
    "shown_anywhere",
    "introductions_asked",
    "introduction_share",
    "mean_path_length",
    "outside_network_shown",
    "teams",
    "mean_team_size",
    "team_gap_coverage",
    "team_cover_precision",
)


def main() -> None:
    metrics, rows = {}, []
    for run in RUNS:
        graph = json.loads((HERE / "data" / f"exp010-{run}.json").read_text())["graph"]
        graph["violations_total"] = sum(
            v for k, v in graph.items() if k.startswith("violations")
        )
        row = {"run": run, **{k: graph.get(k) for k in KEYS}}
        rows.append(row)
        for k in KEYS:
            metrics[f"{run}_{k}"] = graph.get(k)
        for name, lat in graph["latency_seconds"].items():
            if lat:
                metrics[f"{run}_latency_{name}_p95"] = lat["p95"]
    (HERE / "data" / "metrics.json").write_text(json.dumps(metrics, indent=1, sort_keys=True))
    with (HERE / "data" / "metrics.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    lines = ["| Run | " + " | ".join(KEYS) + " |", "|---|" + "---:|" * len(KEYS)] + [
        f"| {r['run']} — {RUNS[r['run']]} | " + " | ".join(str(r[k]) for k in KEYS) + " |"
        for r in rows
    ]
    (HERE / "tables" / "summary.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
