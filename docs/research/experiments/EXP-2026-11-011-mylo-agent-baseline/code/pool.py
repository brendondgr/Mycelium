"""EXP-2026-11-011: pool the gate arm's access probes over attempts 3 and 3b.

    python3 docs/research/experiments/EXP-2026-11-011-mylo-agent-baseline/code/pool.py

Writes data/metrics_pooled.json: graded leaks to the answer over all access
probes, and the same excluding `probe-channel-personal`, whose attempt-1
grader fails on the asker's own word (ISSUES.md).
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "code"))
from analyse_v2 import clopper  # noqa: E402

rows = []
for tag in ("v3", "v3b"):
    rows += [json.loads(x) for x in (HERE / "logs" / f"runs_v2_gate_{tag}.jsonl").read_text().splitlines() if x.strip()]
access = [r for r in rows if r["probe"] and r["category"] != "memory_probe" and not r.get("check_error")]
k = sum(r.get("check_no_leak_answer") is False for r in access)
rest = [r for r in access if r["task"] != "probe-channel-personal"]
k2 = sum(r.get("check_no_leak_answer") is False for r in rest)
controls = [r for r in rows if r["category"] == "scope_control"]
out = {
    "gate_access_runs": len(access), "gate_access_leaks_answer": k, "gate_access_ci95": clopper(k, len(access)),
    "gate_access_runs_excl_own_word_probe": len(rest), "gate_access_leaks_excl_own_word_probe": k2,
    "gate_access_ci95_excl_own_word_probe": clopper(k2, len(rest)),
    "gate_controls_passed": sum(r["passed"] for r in controls), "gate_controls_runs": len(controls),
}
(HERE / "data" / "metrics_pooled.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
