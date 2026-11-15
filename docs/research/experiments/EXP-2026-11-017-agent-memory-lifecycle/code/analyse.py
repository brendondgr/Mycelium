"""EXP-2026-11-017: every number in RESULTS.md, from the logs.

    python code/analyse.py

Reads logs/lifecycle_main*.jsonl (not the dry run); writes data/metrics.json,
data/metrics.csv and tables/summary.md.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE.parent / "EXP-2026-11-016-agent-gate-replication" / "code"))
import stats  # noqa: E402

TARGETS = {"delete_thread": 60, "delete_obs": 60, "message": 20, "forget": 20, "optout": 20,
           "excluded": 20, "delete_thread_production": 60, "isolation": 120}


def main() -> int:
    rows = []
    for path in sorted((HERE / "logs").glob("lifecycle_main*.jsonl")):
        rows += [json.loads(line) for line in path.open()]
    by = defaultdict(list)
    for r in rows:
        by[r["probe"]].append(r)
    out = {}
    for probe, rs in by.items():
        if probe == "isolation_plant":
            out[probe] = {"attempts": len(rs), "recorded": sum(bool(r.get("valid")) for r in rs),
                          "errors": sum("error" in r for r in rs)}
            continue
        errors = [r for r in rs if "error" in r]
        valid = [r for r in rs if r.get("valid") and "error" not in r]
        leaks = [r for r in valid if r.get("leak")]
        asked = sum("ask_user" in ((r.get("turn") or {}).get("calls") or []) for r in rs)
        cell = {"ended_on_question": asked,
                "target": TARGETS.get(probe), "attempts": len(rs), "valid": len(valid),
                "invalid": len(rs) - len(valid) - len(errors), "errors": len(errors),
                "leaks": len(leaks), "rate": round(len(leaks) / len(valid), 4) if valid else None,
                "ci": stats.clopper_pearson(len(leaks), len(valid)),
                "upper95": stats.upper_one_sided(len(leaks), len(valid)),
                "seconds_mean": round(sum(r["seconds"] for r in rs) / len(rs), 1)}
        if probe in ("delete_thread", "delete_obs", "message", "forget",
                     "delete_thread_production"):
            cell["leak_rows"] = sum(bool(r.get("leak_rows")) for r in valid)
            cell["leak_derived_only"] = sum(bool(r.get("leak_derived_only")) for r in valid)
            cell["recalled_any"] = sum(bool(r.get("leak_recalled")) for r in valid)
            cell["recalled_own_chat"] = sum(bool(r["where"]["own_chat"]) for r in valid)
            cell["in_answer"] = sum(bool(r["where"]["answer"]) for r in valid)
            cell["pending_edges_before"] = sum(r["rows_before"]["pending_edges_citing"] > 0
                                               for r in valid)
            cell["observations_before_mean"] = round(
                sum(r["rows_before"]["observations"] for r in valid) / len(valid), 2) if valid else None
        if probe == "optout":
            for k in ("leak_rows", "b_from_ambient", "b_in_answer", "b_from_own_chat",
                      "a_recalled"):
                cell[k] = sum(bool(r.get(k)) for r in valid)
        if probe == "excluded":
            cell["leak_rows"] = sum(bool(r.get("leak_rows")) for r in valid)
            cell["own_chat_recall"] = sum(bool(r.get("own_chat_recall")) for r in valid)
        if probe == "isolation":
            split = defaultdict(lambda: [0, 0])
            for r in valid:
                key = f"{r['asker']}/phrasing{r['phrasing']}"
                split[key][0] += bool(r.get("leak"))
                split[key][1] += 1
            cell["by_asker_phrasing"] = {k: {"leaks": v[0], "n": v[1]} for k, v in split.items()}
            cell["at_answer"] = sum(bool(r["points"]["answer"]) for r in valid)
            cell["at_results"] = sum(bool(r["points"]["results"]) for r in valid)
            cell["statements_recorded"] = len({r["statement"] for r in valid})
        out[probe] = cell
    (HERE / "data").mkdir(exist_ok=True)
    (HERE / "data" / "metrics.json").write_text(json.dumps(out, indent=2, default=str))
    keys = ["probe", "target", "attempts", "valid", "invalid", "errors", "leaks", "rate",
            "ci_lo", "ci_hi", "upper95"]
    with (HERE / "data" / "metrics.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(keys)
        for probe, c in out.items():
            if probe == "isolation_plant":
                continue
            w.writerow([probe, c["target"], c["attempts"], c["valid"], c["invalid"], c["errors"],
                        c["leaks"], c["rate"], *c["ci"], c["upper95"]])
    lines = ["| Probe | Target | Attempted | Valid | Invalid | Errors | Leaks | 95% CI (upper, if 0) |",
             "|---|---:|---:|---:|---:|---:|---:|---|"]
    order = ["delete_thread", "delete_thread_production", "delete_obs", "message", "forget",
             "optout", "excluded", "isolation"]
    for probe in [p for p in order if p in out]:
        c = out[probe]
        span = f"≤ {c['upper95']}" if c["leaks"] == 0 else f"{c['ci'][0]}–{c['ci'][1]}"
        lines.append(f"| {probe} | {c['target']} | {c['attempts']} | {c['valid']} | {c['invalid']} | "
                     f"{c['errors']} | {c['leaks']} | {span} |")
    (HERE / "tables").mkdir(exist_ok=True)
    (HERE / "tables" / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk not in ("ci",)}
                      for k, v in out.items()}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
