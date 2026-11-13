"""EXP-2026-11-010: summarise A1 (scripted loop) and A2 (real questions).

    python3 docs/research/experiments/EXP-2026-11-010-agent-loop-cost/code/analyse.py

Reads data/a1_<tag>.json (copies of run.py's output, one per A1 run) and
data/a2_<tag>.jsonl (run_a2.py), writes data/metrics.json, data/metrics.csv
and tables/summary.md. Standard library only; no number is typed by hand.
"""

from __future__ import annotations

import csv
import json
import statistics as st
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
GROUPS = ("single", "few", "compound")


def a1_summary(path):
    d = json.loads(path.read_text())
    turns = {}
    for r in d["rows"]:
        turns.setdefault((r["steps"], r["rep"]), []).append(r)
    out = {}
    for steps in sorted({k[0] for k in turns}):
        reps = [v for k, v in turns.items() if k[0] == steps]
        lat = [sum(x["latency_s"] for x in rs) for rs in reps]
        tok = [sum((x["prompt_tokens"] or 0) + (x["completion_tokens"] or 0) for x in rs) for rs in reps]
        peak = [max(x["prompt_tokens"] or 0 for x in rs) for rs in reps]
        calls = [sum(x["called"] for x in rs) for rs in reps]
        first = [x["first_delta_s"] for rs in reps for x in rs if x["first_delta_s"] is not None]
        out[str(steps)] = {
            "turn_latency_s_mean": round(st.mean(lat), 2), "turn_latency_s_max": round(max(lat), 2),
            "turn_tokens_mean": round(st.mean(tok)), "peak_prompt_tokens_max": max(peak),
            "function_calls_made_mean": round(st.mean(calls), 2),
            "step_latency_s_mean": round(st.mean(x["latency_s"] for rs in reps for x in rs), 3),
            "first_delta_s_median": round(st.median(first), 3) if first else None,
            "reps": len(reps),
        }
    return out


def a2_summary(path):
    rows = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
    ok = [r for r in rows if "error" not in r]
    out = {"turns": len(rows), "errors": len(rows) - len(ok)}
    for g in GROUPS:
        rs = [r for r in ok if r["group"] == g]
        if not rs:
            continue
        wall = [r["wall_s"] for r in rs]
        first = [r["first_activity_s"] for r in rs if r["first_activity_s"] is not None]
        tok = [r["prompt_tokens"] + r["completion_tokens"] for r in rs]
        out[g] = {
            "n": len(rs),
            "wall_s_median": round(st.median(wall), 2), "wall_s_max": round(max(wall), 2),
            "wall_s_mean": round(st.mean(wall), 2),
            "first_activity_s_median": round(st.median(first), 2) if first else None,
            "first_activity_s_max": round(max(first), 2) if first else None,
            "model_calls_median": st.median(r["model_calls"] for r in rs),
            "model_calls_max": max(r["model_calls"] for r in rs),
            "function_calls_median": st.median(r["function_calls"] for r in rs),
            "function_calls_max": max(r["function_calls"] for r in rs),
            "tokens_median": st.median(tok), "tokens_max": max(tok), "tokens_mean": round(st.mean(tok)),
            "hit_max_steps": sum(r["hit_max_steps"] for r in rs),
            "thrash_stop": sum(r["thrash_stop"] for r in rs),
            "timed_out": sum(r["timed_out"] for r in rs),
            "repair": sum(r["repair"] for r in rs),
        }
    five = [r for r in ok if 4 <= r["model_calls"] <= 6]
    out["turns_with_4_to_6_model_calls"] = {
        "n": len(five),
        "wall_s_max": round(max((r["wall_s"] for r in five), default=0), 2),
        "over_60s": sum(r["wall_s"] > 60 for r in five),
        "tokens_max": max((r["prompt_tokens"] + r["completion_tokens"] for r in five), default=0),
    }
    upto5 = [r for r in ok if r["function_calls"] <= 5]
    out["turns_with_up_to_5_function_calls"] = {
        "n": len(upto5),
        "wall_s_max": round(max((r["wall_s"] for r in upto5), default=0), 2),
        "over_60s": sum(r["wall_s"] > 60 for r in upto5),
        "tokens_max": max((r["prompt_tokens"] + r["completion_tokens"] for r in upto5), default=0),
        "over_30k_tokens": sum(r["prompt_tokens"] + r["completion_tokens"] > 30000 for r in upto5),
    }
    lat = sorted(c["latency_s"] for r in ok for c in r.get("calls", []))
    if lat:
        out["model_call_latency_s"] = {"n": len(lat), "median": round(st.median(lat), 2),
                                       "p90": round(lat[int(len(lat) * 0.9)], 2), "max": round(lat[-1], 2)}
    if any("conc" in r for r in ok):
        from datetime import datetime, timedelta

        batches = []
        for rep in sorted({r["rep"] for r in ok}):
            rs = [r for r in ok if r["rep"] == rep]
            ends = [datetime.strptime(r["at"], "%Y-%m-%dT%H:%M:%S%z") for r in rs]
            starts = [e - timedelta(seconds=r["wall_s"]) for e, r in zip(ends, rs)]
            batches.append((max(ends) - min(starts)).total_seconds())
        out["in_flight"] = ok[0].get("conc")
        out["batch_wall_s"] = {"n": len(batches), "median": round(st.median(batches), 1),
                               "max": round(max(batches), 1)}
    else:  # one at a time: twelve questions take the sum of their turns
        batches = [sum(r["wall_s"] for r in ok if r["rep"] == rep) for rep in sorted({r["rep"] for r in ok})]
        out["in_flight"] = 1
        out["batch_wall_s"] = {"n": len(batches), "median": round(st.median(batches), 1),
                               "max": round(max(batches), 1)}
    out["over_60s_any"] = sum(r["wall_s"] > 60 for r in ok)
    peaks = [max((c["prompt_tokens"] or 0) for c in r["calls"]) for r in ok if r.get("calls")]
    out["peak_prompt_tokens_any_call"] = max(peaks) if peaks else None
    long_turns = [r for r in ok if r["model_calls"] >= 15]
    out["turns_with_15_plus_model_calls"] = len(long_turns)
    out["peak_prompt_tokens_in_15_plus_turns"] = max(
        (max((c["prompt_tokens"] or 0) for c in r["calls"]) for r in long_turns), default=None)
    return out


def main() -> int:
    data = HERE / "data"
    metrics = {"a1": {}, "a2": {}}
    for p in sorted(data.glob("a1_*.json")):
        metrics["a1"][p.stem[3:]] = a1_summary(p)
    for p in sorted(data.glob("a2_*.jsonl")):
        if p.stem.endswith("smoke"):
            continue
        metrics["a2"][p.stem[3:]] = a2_summary(p)
    (data / "metrics.json").write_text(json.dumps(metrics, indent=1))
    flat = []
    for tag, s in metrics["a1"].items():
        for steps, v in s.items():
            flat.append({"arm": "A1", "run": tag, "group": f"{steps}_calls", **v})
    for tag, s in metrics["a2"].items():
        for g in GROUPS:
            if g in s:
                flat.append({"arm": "A2", "run": tag, "group": g, **s[g]})
    keys = sorted({k for r in flat for k in r})
    with (data / "metrics.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(flat)
    lines = ["| Arm | Run | Group | Median s | Worst s | Mean s | Median tokens | Worst tokens | Model calls (median/max) |",
             "|---|---|---|---:|---:|---:|---:|---:|---|"]
    for tag, s in metrics["a2"].items():
        for g in GROUPS:
            if g in s:
                v = s[g]
                lines.append(f"| A2 | {tag} | {g} | {v['wall_s_median']} | {v['wall_s_max']} | {v['wall_s_mean']} | "
                             f"{v['tokens_median']} | {v['tokens_max']} | {v['model_calls_median']}/{v['model_calls_max']} |")
    for tag, s in metrics["a1"].items():
        for steps, v in s.items():
            lines.append(f"| A1 | {tag} | {steps} calls | — | {v['turn_latency_s_max']} | {v['turn_latency_s_mean']} | "
                         f"{v['turn_tokens_mean']} (mean) | peak prompt {v['peak_prompt_tokens_max']} | — |")
    (HERE / "tables").mkdir(exist_ok=True)
    (HERE / "tables" / "summary.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(metrics, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
