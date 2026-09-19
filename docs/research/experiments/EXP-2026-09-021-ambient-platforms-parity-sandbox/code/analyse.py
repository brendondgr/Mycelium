"""EXP-2026-09-021's table, from ``data/exp021-run{1,2}.json``.

    python3 docs/research/experiments/EXP-2026-09-021-ambient-platforms-parity-sandbox/code/analyse.py
"""

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
RUNS = {"run1": "registered", "run2": "post hoc: a fixed gate mix"}
REASONS = ["dropped_not_opted_in", "dropped_free_tier", "dropped_unlinked", "dropped_too_short"]


def main() -> None:
    rows = []
    for run, label in RUNS.items():
        data = json.loads((HERE / "data" / f"exp021-{run}.json").read_text())
        for platform, result in data["platforms"].items():
            rows.append(
                {
                    "run": f"{run} ({label})",
                    "platform": platform,
                    "people_kept": result["people_kept"],
                    "differ_from_discord": result["people_kept_differ_from_discord"],
                    "mylo_lines_kept": result["mylo_lines_kept"],
                    "mylo_not_delivered": result["mylo_not_delivered"],
                    **{reason: result["drops"].get(reason, 0) for reason in REASONS},
                    "drops_equal_discord": result["drops_equal_discord"],
                }
            )
    (HERE / "data" / "metrics.json").write_text(json.dumps(rows, indent=2) + "\n")
    with (HERE / "data" / "metrics.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    keys = list(rows[0])
    lines = ["| " + " | ".join(keys) + " |", "|" + "---|" * len(keys)]
    lines += ["| " + " | ".join(str(row[k]) for k in keys) + " |" for row in rows]
    (HERE / "tables" / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
