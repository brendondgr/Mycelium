"""EXP-2026-09-016's table, from the browser check's output.

Reads ``data/browser-run{1..4}.json`` and writes ``data/metrics.json``,
``data/metrics.csv`` and ``tables/summary.md``.

    python3 docs/research/experiments/EXP-2026-09-016-ambient-web-browser-a11y/code/analyse.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
RUNS = {
    "run1": "registered harness, UI @fcfe239",
    "run2": "UI fixes @1f181c5",
    "run3": "undo + reader r5 @bf94544",
    "run4": "harness date-input fix @a9d4ab3",
}


def main() -> None:
    metrics: dict[str, dict] = {}
    for run, label in RUNS.items():
        data = json.loads((HERE / "data" / f"browser-{run}.json").read_text())
        serious = sum(
            len(page["axe"]["serious"])
            for tag in ("phone", "desktop")
            for page in data.get(tag, {}).get("survey", {}).get("pages", {}).values()
        )
        other = sum(
            len(page["axe"]["other"])
            for tag in ("phone", "desktop")
            for page in data.get(tag, {}).get("survey", {}).get("pages", {}).values()
        )
        failures = data["failures"]
        metrics[run] = {
            "label": label,
            "failures": len(failures),
            "axe_serious_rule_page_pairs": serious,
            "axe_moderate_minor": other,
            "flow_failures": sum(1 for f in failures if ".flows." in f or f.startswith("desktop:")),
            "keyboard_failures": sum(1 for f in failures if "keyboard" in f),
            "page_scroll_failures": sum(1 for f in failures if "page_scroll" in f),
            "console_error_passes": sum(1 for f in failures if "console_errors" in f),
            "missing_surfaces": sum(1 for f in failures if ".missing_" in f),
            "failure_list": failures,
        }
    (HERE / "data" / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    keys = [k for k in next(iter(metrics.values())) if k not in ("label", "failure_list")]
    with (HERE / "data" / "metrics.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["run", *keys])
        for run, row in metrics.items():
            writer.writerow([run, *(row[k] for k in keys)])
    lines = ["| Run | " + " | ".join(keys) + " |", "|---|" + "---:|" * len(keys)]
    for run, row in metrics.items():
        lines.append(f"| {run} — {row['label']} | " + " | ".join(str(row[k]) for k in keys) + " |")
    (HERE / "tables" / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
