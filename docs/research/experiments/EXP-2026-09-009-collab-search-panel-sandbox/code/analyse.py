"""Turn the panel harness's and the browser check's output into metrics and a table.

Reads ``data/exp009.json`` (``python -m sandbox.collab panel``, run 2) and
``data/browser.json`` (``code/browser_check.py``), writes ``data/metrics.json``,
``data/metrics.csv`` and ``tables/summary.md``.

    python3 docs/research/experiments/EXP-2026-09-009-collab-search-panel-sandbox/code/analyse.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent


def main() -> None:
    api = json.loads((HERE / "data" / "exp009.json").read_text())["api"]
    browser = json.loads((HERE / "data" / "browser.json").read_text())
    metrics = {f"api_{k}": v for k, v in api.items()}
    metrics["api_violations_total"] = sum(
        v for k, v in api.items() if k.startswith("violations")
    )
    for width in ("desktop", "phone"):
        for key, value in browser[width].items():
            if key == "console_errors":
                value = len(value)
            if isinstance(value, list):
                value = "; ".join(value)
            metrics[f"browser_{width}_{key}"] = value
    metrics["browser_failures"] = len(browser["invariant_failures"])
    (HERE / "data" / "metrics.json").write_text(json.dumps(metrics, indent=1, sort_keys=True))
    with (HERE / "data" / "metrics.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "value"])
        for key in sorted(metrics):
            writer.writerow([key, metrics[key]])
    keep = [
        "api_seekers_done",
        "api_searches_call",
        "api_searches_project",
        "api_searches_manual",
        "api_hits",
        "api_hits_method_bridge",
        "api_hits_problem_bridge",
        "api_hits_resource",
        "api_hits_in_field",
        "api_empty_results",
        "api_saved_checked",
        "api_foreign_project_hidden_403",
        "api_unverified_checked",
        "api_violations_total",
        "api_latency_call_p50",
        "api_latency_call_p95",
        "api_latency_project_p50",
        "api_latency_project_p95",
        "api_latency_manual_p50",
        "api_latency_manual_p95",
        "browser_desktop_call_chips",
        "browser_desktop_project_chips",
        "browser_desktop_hits_shown",
        "browser_desktop_console_errors",
        "browser_phone_panel_no_page_scroll",
        "browser_phone_palette_text_carried",
        "browser_failures",
    ]
    lines = ["| Metric | Value |", "|---|---:|"] + [
        f"| `{k}` | {metrics.get(k, 0)} |" for k in keep
    ]
    (HERE / "tables" / "summary.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
