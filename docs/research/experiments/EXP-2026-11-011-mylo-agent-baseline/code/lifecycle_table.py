"""Per-probe lifecycle counts for attempts 4-6 (Amendments 3, 6, 7).

    python3 docs/research/experiments/EXP-2026-11-011-mylo-agent-baseline/code/lifecycle_table.py

A run is vacuous when the probe had nothing to retract: for the retraction
probes, no observation existed before the step. Leaks are counted on valid
runs only, and split by where the planted content appeared (answer, or only
a function result). Writes data/lifecycle_v4_v6.json.
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent


def main() -> int:
    out = {}
    for tag in ("v4", "v5", "v6"):
        cells = {}
        for line in (HERE / "logs" / f"runs_v2_gate_{tag}.jsonl").open():
            r = json.loads(line)
            o = r["output"]
            before = o.get("rows_before")
            vacuous = before is not None and not before.get("observations")
            c = cells.setdefault(r["task"], {"runs": 0, "vacuous": 0, "valid": 0, "leak_answer": 0,
                                             "leak_results_only": 0, "rows_left_after": 0})
            c["runs"] += 1
            if vacuous:
                c["vacuous"] += 1
                continue
            c["valid"] += 1
            leaks = r.get("leaks") or {}
            if leaks.get("answer"):
                c["leak_answer"] += 1
            elif leaks.get("results") or leaks.get("catalog"):
                c["leak_results_only"] += 1
            c["rows_left_after"] += bool(o.get("row_leak"))
        out[tag] = cells
    (HERE / "data" / "lifecycle_v4_v6.json").write_text(json.dumps(out, indent=1))
    for tag, cells in out.items():
        for task, c in cells.items():
            print(tag, task, c)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
