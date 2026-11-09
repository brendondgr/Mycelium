"""EXP-2026-11-008 — gather decision_check's JSON summaries into the metrics files.

    python3 docs/research/experiments/EXP-2026-11-008-decision-port-throughput/code/collect.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

EXP = Path(__file__).resolve().parent.parent
LEVELS = (1, 4, 8)


def main() -> int:
    runs = {c: json.loads((EXP / "data" / f"run_c{c}.json").read_text()) for c in LEVELS}
    values: dict[str, float | int | str] = {"model": runs[1]["model"]}
    for c, r in runs.items():
        values[f"throughput_c{c}"] = r["throughput_calls_per_s"]
        values[f"latency_p50_ms_c{c}"] = r["latency_ms_p50"]
        values[f"latency_p95_ms_c{c}"] = r["latency_ms_p95"]
        values[f"failures_c{c}"] = r["failures"]
    values["throughput_gain_c8_over_c1"] = round(
        runs[8]["throughput_calls_per_s"] / runs[1]["throughput_calls_per_s"], 3
    )
    (EXP / "data" / "metrics.json").write_text(json.dumps(values, indent=1, sort_keys=True))
    with (EXP / "data" / "metrics.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["concurrency", "calls", "ok", "failures", "throughput_calls_per_s",
                    "latency_ms_p50", "latency_ms_p95", "latency_ms_max"])
        for c, r in runs.items():
            w.writerow([c, r["calls"], r["ok"], r["failures"], r["throughput_calls_per_s"],
                        r["latency_ms_p50"], r["latency_ms_p95"], r["latency_ms_max"]])
    lines = ["| In flight | Calls | Failures | Calls/s | p50 ms | p95 ms |",
             "| ---: | ---: | ---: | ---: | ---: | ---: |"]
    for c, r in runs.items():
        lines.append(f"| {c} | {r['calls']} | {r['failures']} | {r['throughput_calls_per_s']} "
                     f"| {r['latency_ms_p50']} | {r['latency_ms_p95']} |")
    (EXP / "tables").mkdir(exist_ok=True)
    (EXP / "tables" / "throughput.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(values, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
