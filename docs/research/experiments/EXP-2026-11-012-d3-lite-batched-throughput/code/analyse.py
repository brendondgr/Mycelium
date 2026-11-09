"""EXP-2026-11-012 — metrics and the like-for-like throughput table.

    python3 code/analyse.py

Reads data/bench.json (arm A, d3-lite in-process), data/qwen_real.json (arm B,
llama.cpp on real states) and the committed metrics of EXP-2026-11-008 (d3-lite
through decide) and EXP-2026-11-009 (Qwen3-4B on llama.cpp). Writes
data/metrics.json, data/metrics.csv and tables/summary.md. Calls no model.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

EXP = Path(__file__).resolve().parent.parent
ROOT = EXP.parent
E008 = ROOT / "EXP-2026-11-008-decision-port-throughput" / "data" / "metrics.json"
E009 = ROOT / "EXP-2026-11-009-qwen3-4b-llamacpp-decisions" / "data" / "metrics.json"
KS = (1, 4, 8)


def rate(entry):
    return round(entry["pairs"] / entry["wall_s"], 3)


def main() -> int:
    bench = json.loads((EXP / "data" / "bench.json").read_text())["results"]
    qwen = json.loads((EXP / "data" / "qwen_real.json").read_text())["levels"]
    e8 = json.loads(E008.read_text())
    e9 = json.loads(E009.read_text())

    m: dict = {}
    for name in ("synthetic", "real"):
        m[f"d3_{name}_seq"] = rate(bench[name]["seq"])
        for k in KS:
            b = bench[name][f"batch_{k}"]
            m[f"d3_{name}_batch{k}"] = rate(b)
            m[f"d3_{name}_batch{k}_max_abs_diff"] = round(b["max_abs_diff_vs_seq"], 6)
    m["d3_synthetic_gain_batch8_over_batch1"] = round(
        m["d3_synthetic_batch8"] / m["d3_synthetic_batch1"], 3
    )
    m["d3_real_gain_batch8_over_batch1"] = round(
        m["d3_real_batch8"] / m["d3_real_batch1"], 3
    )
    for c in KS:
        q = qwen[str(c)]
        m[f"qwen_real_c{c}"] = q["pairs_per_s"]
        m[f"qwen_real_latency_p50_ms_c{c}"] = q["latency_ms_p50"]
        m[f"qwen_real_failures_c{c}"] = q["failures"]
        m[f"d3_server_synthetic_c{c}"] = e8[f"throughput_c{c}"]
        m[f"qwen_synthetic_c{c}"] = e9[f"throughput_c{c}"]
    best_d3_real = max(m["d3_real_seq"], *(m[f"d3_real_batch{k}"] for k in KS))
    best_qwen_real = max(m[f"qwen_real_c{c}"] for c in KS)
    m["d3_best_real"] = best_d3_real
    m["qwen_best_real"] = best_qwen_real
    m["d3_over_qwen_best_real"] = round(best_d3_real / best_qwen_real, 3)

    (EXP / "data" / "metrics.json").write_text(json.dumps(m, indent=1, sort_keys=True))
    with (EXP / "data" / "metrics.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["metric", "value"])
        for k in sorted(m):
            w.writerow([k, m[k]])

    lines = [
        "Pairs per second (one pair = one state with all of its questions).",
        "",
        "| State | Parallelism | d3-lite, decide server | d3-lite, in-process | "
        "Qwen3-4B, llama.cpp |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for k in KS:
        lines.append(
            f"| synthetic (48) | {k} | {m[f'd3_server_synthetic_c{k}']} | "
            f"{m[f'd3_synthetic_batch{k}']} | {m[f'qwen_synthetic_c{k}']} |"
        )
    for k in KS:
        lines.append(
            f"| real (165) | {k} | — | {m[f'd3_real_batch{k}']} | {m[f'qwen_real_c{k}']} |"
        )
    lines += [
        "",
        "Parallelism: requests in flight (decide server, llama.cpp) or pairs per "
        "forward pass (d3-lite in-process). In-process one-pair-at-a-time "
        f"(`system_one`): synthetic {m['d3_synthetic_seq']}, real {m['d3_real_seq']}.",
        "",
        "| Batched vs sequential answers | max abs diff |",
        "| --- | ---: |",
    ]
    for name in ("synthetic", "real"):
        for k in (4, 8):
            lines.append(f"| {name}, {k} per pass | {m[f'd3_{name}_batch{k}_max_abs_diff']} |")
    (EXP / "tables").mkdir(exist_ok=True)
    (EXP / "tables" / "summary.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(m, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
