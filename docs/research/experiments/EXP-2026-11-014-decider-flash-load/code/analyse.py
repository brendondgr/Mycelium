"""EXP-2026-11-014: summarise data/bench_<tag>.json.

    python3 docs/research/experiments/EXP-2026-11-014-decider-flash-load/code/analyse.py

Standard library only. Per tag, shape and level: the median of the timed
passes (and min/max across passes) for requests/s, decisions/s, input
tokens/s, latency p50/p95/p99, error rate. Consistency: joint vs single, and
concurrency 1 vs the highest level, on identical bodies (first timed pass at
those levels keeps per-request answers). Writes data/metrics.json,
data/metrics.csv, tables/summary.md.
"""

from __future__ import annotations

import csv
import json
import statistics as st
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
FIELDS = ("req_per_s", "decisions_per_s", "input_tok_per_s", "lat_p50", "lat_p95", "lat_p99", "error_rate")


def first_option_prob(ans):
    """yes-probability for noul; P(first listed option) otherwise."""
    if "yes" in ans and len(ans) == 1:
        return ans["yes"]
    keys = list(ans)
    return ans[keys[0]] if keys else None


def argmax(ans):
    if "yes" in ans and len(ans) == 1:
        return "yes" if ans["yes"] >= 0.5 else "no"
    return max(ans, key=ans.get) if ans else None


def compare(rows_a, rows_b, split_b=False):
    """Per-question differences between two answer sets on the same pairs."""
    a = {r["id"]: r.get("ans") or {} for r in rows_a if r["status"] == 200}
    b = {}
    for r in rows_b:
        if r["status"] != 200:
            continue
        if split_b:  # single: id is "<pair>#<question>"
            pid, q = r["id"].split("#", 1)
            b.setdefault(pid, {}).update(r.get("ans") or {})
        else:
            b[r["id"]] = r.get("ans") or {}
    diffs, agree, n = [], 0, 0
    for pid, qa in a.items():
        for q, ans in qa.items():
            other = (b.get(pid) or {}).get(q)
            if not other:
                continue
            pa, pb = first_option_prob(ans), first_option_prob(other)
            if pa is None or pb is None:
                continue
            diffs.append(abs(pa - pb))
            agree += argmax(ans) == argmax(other)
            n += 1
    if not n:
        return None
    return {"questions": n, "max_abs_diff": round(max(diffs), 6), "mean_abs_diff": round(st.mean(diffs), 6),
            "share_over_0.05": round(sum(d > 0.05 for d in diffs) / n, 4),
            "argmax_agreement": round(agree / n, 4)}


KEPT = {}


def main() -> int:
    out, flat = {}, []
    for path in sorted((HERE / "data").glob("bench_*.json")):
        d = json.loads(path.read_text())
        tag = d["tag"]
        entry = {"started": d["started"], "n_pairs": d["n_pairs"], "states_sha256": d["states_sha256"],
                 "health_before": d["health_before"], "health_after": d.get("health_after"),
                 "stopped": d.get("stopped"), "shapes": {}, "consistency": {}}
        for shape, sd in d["shapes"].items():
            levels = {}
            for lvl, runs in sd["levels"].items():
                sums = [r["summary"] for r in runs]
                row = {"passes": len(sums)}
                for f in FIELDS:
                    vals = [s[f] for s in sums if s.get(f) is not None]
                    if vals:
                        row[f] = round(st.median(vals), 4)
                        row[f + "_min"], row[f + "_max"] = round(min(vals), 4), round(max(vals), 4)
                if row.get("req_per_s") and row.get("input_tok_per_s"):
                    row["input_tokens_per_request"] = round(row["input_tok_per_s"] / row["req_per_s"], 1)
                row["foreign_requests"] = sum(max(0, s["health_requests_delta"] - s["requests"]) for s in sums)
                row["server_errors_delta"] = sum(s["health_errors_delta"] for s in sums)
                levels[lvl] = row
                flat.append({"tag": tag, "shape": shape, "level": int(lvl), **row})
            entry["shapes"][shape] = {"n_requests": sd["n_requests"], "levels": levels}
            best = max(levels.items(), key=lambda kv: kv[1].get("req_per_s", 0)) if levels else None
            if best:
                entry["shapes"][shape]["peak"] = {"level": int(best[0]), "req_per_s": best[1]["req_per_s"],
                                                  "decisions_per_s": best[1].get("decisions_per_s")}
        for shape, sd in d["shapes"].items():
            for lvl, runs in sd["levels"].items():
                for r in runs:
                    if "rows" in r and all(x["status"] == 200 for x in r["rows"]):
                        KEPT.setdefault((shape, int(lvl)), (tag, r["rows"]))
        out[tag] = entry
    # Consistency across runs (answers are kept for the first clean pass at a
    # run's lowest and highest level): same bodies, different batching or load.
    cons = {}
    if ("joint", 1) in KEPT and ("single", 1) in KEPT:
        cons["joint_vs_single@1"] = compare(KEPT[("joint", 1)][1], KEPT[("single", 1)][1], split_b=True)
        cons["joint_vs_single@1"]["runs"] = [KEPT[("joint", 1)][0], KEPT[("single", 1)][0]]
    joint_levels = sorted(l for (s, l) in KEPT if s == "joint" and l > 1)
    if ("joint", 1) in KEPT and joint_levels:
        hi = joint_levels[-1]
        cons[f"joint@1_vs_joint@{hi}"] = compare(KEPT[("joint", 1)][1], KEPT[("joint", hi)][1])
        cons[f"joint@1_vs_joint@{hi}"]["runs"] = [KEPT[("joint", 1)][0], KEPT[("joint", hi)][0]]
    out["_consistency"] = cons
    (HERE / "data" / "metrics.json").write_text(json.dumps(out, indent=1))
    keys = sorted({k for r in flat for k in r})
    with (HERE / "data" / "metrics.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(flat)
    lines = ["| Run | Shape | In flight | Req/s | Decisions/s | Input tok/s | p50 s | p95 s | p99 s | Errors |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in flat:
        lines.append(f"| {r['tag']} | {r['shape']} | {r['level']} | {r.get('req_per_s')} | {r.get('decisions_per_s')} | "
                     f"{r.get('input_tok_per_s')} | {r.get('lat_p50')} | {r.get('lat_p95')} | {r.get('lat_p99')} | {r.get('error_rate')} |")
    lines.append(f"\nConsistency: {json.dumps(out['_consistency'])}")
    (HERE / "tables").mkdir(exist_ok=True)
    (HERE / "tables" / "summary.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({t: {"peaks": {s: v.get("peak") for s, v in e["shapes"].items()},
                          "stopped": e["stopped"]} for t, e in out.items() if t != "_consistency"}, indent=1))
    print(json.dumps(out["_consistency"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
