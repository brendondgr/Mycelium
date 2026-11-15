"""EXP-2026-11-016: function results that failed, per configuration database.

    python code/function_errors.py      (inside a backend container)

Counts ``tool_result`` events by status and error code in every
``mycelium_agent_eval_r2_<seed>_<arm>_<model>`` database and writes
``data/function_errors.json``. ``failed`` ("… failed inside Mycelium") is an
internal exception in the function (Q-069: a non-id project reference).
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path

import psycopg

HERE = Path(__file__).resolve().parent.parent
base = os.environ["DATABASE_URL"]
out = {}
for seed in (101, 202, 303):
    for arm in ("gate", "prompt_only"):
        for model in ("instance", "second"):
            db = f"mycelium_agent_eval_r2_{seed}_{arm}_{model}"
            with psycopg.connect(re.sub(r"/[^/]+$", f"/{db}", base)) as conn:
                rows = conn.execute("SELECT payload FROM agent_agentevent "
                                    "WHERE type='tool_result'").fetchall()
            codes = Counter()
            failed_by_fn = Counter()
            for (p,) in rows:
                status = (p or {}).get("status") or "ok"
                code = ((p or {}).get("error") or {}).get("code") or ""
                codes[f"{status}:{code}" if code else status] += 1
                if code == "failed":
                    failed_by_fn[p.get("name")] += 1
            out[db] = {"tool_results": len(rows), "by_status_code": dict(codes),
                       "failed_inside_by_function": dict(failed_by_fn)}
totals = Counter()
for db, v in out.items():
    arm = "gate" if "_gate_" in db else "prompt_only"
    totals[f"{arm}:tool_results"] += v["tool_results"]
    totals[f"{arm}:failed_inside"] += sum(v["failed_inside_by_function"].values())
out["_totals"] = dict(totals)
(HERE / "data").mkdir(exist_ok=True)
(HERE / "data" / "function_errors.json").write_text(json.dumps(out, indent=2))
print(json.dumps(out["_totals"], indent=1))
