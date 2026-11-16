"""Round three's first counted chain (2026-11-16, 17:06-18:36 UTC) ran into a
model-server outage. Count what every registered log holds, so the failed run
is recorded with numbers read from the logs, not typed by hand.

    python3 docs/research/experiments/EXP-2026-11-019-agent-collab-scenarios/code/outage_r3.py

The logs were moved into ``logs/outage-20261116/`` and ``data/outage-20261116/``
so the registered file names stay free for a counted run. Writes, per experiment folder, ``data/outage_r3.json`` and
``tables/outage_r3.md`` (EXP-2026-11-019, -016, -018, -010).
"""

from __future__ import annotations

import collections
import json
import re
from pathlib import Path

EXPS = Path(__file__).resolve().parents[2]
E19 = EXPS / "EXP-2026-11-019-agent-collab-scenarios"
E16 = EXPS / "EXP-2026-11-016-agent-gate-replication"
E18 = EXPS / "EXP-2026-11-018-agent-answers-gold"
E10 = EXPS / "EXP-2026-11-010-agent-loop-cost"

LOGS = {
    E19: [("019 repeated", E19 / "logs/outage-20261116/runs_r3_repeated_instance_r3.jsonl"),
          ("019 fresh", E19 / "logs/outage-20261116/runs_r3_fresh_instance_r3.jsonl")],
    E16: [(f"016 gate seed {s}", E16 / f"logs/outage-20261116/runs_r3_s{s}_gate_instance.jsonl") for s in (101, 202, 303)],
    E18: [("018 arms a-c", E18 / "data/outage-20261116/runs_r3.jsonl")],
    E10: [("010 A6 idle", E10 / "data/outage-20261116/a2_a6idle.jsonl"), ("010 A6 8 in flight", E10 / "data/outage-20261116/a2_a6p8.jsonl")],
}


def kind(text: str) -> str:
    for pat, name in (("ConnectError", "connection refused (ConnectError)"),
                      ("ConnectTimeout", "connect timeout"), ("ReadError", "read error"),
                      ("Timeout|timed out", "request timeout"), ("APIConnectionError", "connection error")):
        if re.search(pat, text):
            return name
    return "other"


def rows_of(path: Path) -> list[dict]:
    return [r for r in (json.loads(x) for x in path.open()) if "marker" not in r]


def cls(r: dict) -> str:
    if "outcome" in r:  # r3turns classes (019, 016)
        return r["outcome"]
    if (r.get("final_text") or "").strip():
        return "answered"
    errs = r.get("errors") or []
    if any(isinstance(e, dict) and e.get("code") == "turn_failed" for e in errs) or r.get("error"):
        return "failed"
    return "blank"


def errors_text(r: dict) -> list[str]:
    out = list(r.get("call_exceptions") or [])
    for e in r.get("errors") or []:
        out.append(json.dumps(e) if isinstance(e, dict) else str(e))
    if r.get("error"):
        out.append(str(r["error"]))
    return out


def summarise(label: str, path: Path) -> dict:
    rows = rows_of(path)
    by = collections.Counter(cls(r) for r in rows)
    kinds = collections.Counter(kind(" ".join(errors_text(r))) for r in rows if cls(r) == "failed")
    at = sorted(r.get("at") for r in rows if r.get("at"))
    answered = [r for r in rows if cls(r) == "answered"]
    out = {"run": label, "log": str(path.relative_to(EXPS.parents[2])), "rows": len(rows),
           "outcomes": dict(sorted(by.items())), "failure_kinds": dict(kinds.most_common()),
           "first_row_at": at[0] if at else None, "last_row_at": at[-1] if at else None,
           "last_answered_at": max((r.get("at") for r in answered), default=None),
           "empty_calls": sum(int(r.get("empty_calls") or 0) for r in rows)}
    if answered and "must_named" in answered[0]:
        out["answered_named_planted"] = sum(1 for r in answered if r.get("must_named"))
        out["answered_with_violation"] = sum(1 for r in answered if r.get("violation_any"))
        out["answered_scenarios"] = dict(collections.Counter(r.get("scenario") for r in answered))
        out["answered_seconds"] = sorted(r.get("seconds") for r in answered)
    return out


def table(items: list[dict]) -> str:
    lines = ["| Run | Rows | Answered | Failed (server) | Other classes | Empty model calls | First row | Last row | Last answered |",
             "|---|---|---|---|---|---|---|---|---|"]
    for s in items:
        o = dict(s["outcomes"])
        a, f = o.pop("answered", 0), o.pop("failed", 0)
        other = ", ".join(f"{k} {v}" for k, v in o.items()) or "none"
        lines.append(f"| {s['run']} | {s['rows']} | {a} | {f} | {other} | {s['empty_calls']} | "
                     f"{s['first_row_at']} | {s['last_row_at']} | {s['last_answered_at'] or '—'} |")
    lines.append("")
    lines.append("Failure kinds (by the first model-server error in the row):")
    lines.append("")
    for s in items:
        lines.append(f"- {s['run']}: " + ", ".join(f"{k} {v}" for k, v in s["failure_kinds"].items()))
    for s in items:
        if "answered_named_planted" in s:
            lines.append("")
            lines.append(f"Answered turns in {s['run']}: {sum(s['answered_scenarios'].values())} "
                         f"({', '.join(f'{k} {v}' for k, v in s['answered_scenarios'].items())}); "
                         f"named the planted person {s['answered_named_planted']}; "
                         f"named someone outside the rules {s['answered_with_violation']}; "
                         f"seconds {', '.join(str(x) for x in s['answered_seconds'])}.")
    return "\n".join(lines) + "\n"


def main() -> int:
    for exp, logs in LOGS.items():
        items = [summarise(label, p) for label, p in logs]
        (exp / "data" / "outage_r3.json").write_text(json.dumps(items, indent=2) + "\n")
        (exp / "tables").mkdir(exist_ok=True)
        (exp / "tables" / "outage_r3.md").write_text(
            "<!-- generated by EXP-2026-11-019 code/outage_r3.py; do not edit -->\n" + table(items))
        print(exp.name)
        print(table(items))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
