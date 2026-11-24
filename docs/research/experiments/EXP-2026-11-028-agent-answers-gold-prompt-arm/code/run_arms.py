"""EXP-2026-11-028: EXP-2026-11-018's arm (a) (Mylo as shipped) against the same
arm with the gate off and the access policy in the system prompt, on the
sandbox database only.

    <container, -e SANDBOX_DB=mycelium_sandbox_exp028 -e R4_GOLD=s28>
    python …/code/run_arms.py gold                       # EXP-2026-11-018 r4.py gold, on the sandbox
    python …/code/run_arms.py run --arm code   --conc 30 # writes EXP-018/data/runs_s28_code.jsonl
    python …/code/run_arms.py run --arm prompt --conc 30 # writes EXP-018/data/runs_s28_prompt.jsonl

Both commands connect through ``sandbox.collab.bootstrap`` and refuse to go
on unless the database name begins ``mycelium_sandbox_`` and every count of
``check_sandbox.counts()`` is zero. The prompt arm makes every function
return everything in the database and lists every project with its members
in the prompt, so it must never see the live database.

``--arm prompt`` calls EXP-2026-11-011's ``run_v2.bypass_gate()``. It patches
the whole process, so the two arms are two processes, not threads of one.
Jobs are the questions kept in ``data/gold_<R4_GOLD>.json`` × 3 repetitions,
shuffled with seed 20261115 (the same order in both arms, so the same
question is asked at about the same time in each). A failed job (exception,
deadline, no final text) is kept and retried once at the end, as in
EXP-2026-11-018's ``run.py``; its ``failed_reason`` is copied and
``mylo_turn.run_question`` is used unchanged.

Each row also records, from the first model call of the turn, whether the
system prompt carried the policy text (``policy_in_prompt``), and how many
function calls of the turn the gate would have refused or held for
confirmation had it been asked first (``gate_would_not_allow``; counted in
both arms, enforced only in the code arm).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPS = HERE.parents[1]
E18 = EXPS / "EXP-2026-11-018-agent-answers-gold"
E11 = EXPS / "EXP-2026-11-011-mylo-agent-baseline" / "code"
E13 = EXPS / "EXP-2026-11-013-agent-answers-human-judged" / "code"
sys.path[:0] = [str(HERE), str(E18 / "code"), str(E13), "/app/web/backend", "/app"]

VISITOR = "EXP-2026-11-028"
SEED = 20261115
REPS = 3
GOLD = os.environ.get("R4_GOLD", "s28")
_local = threading.local()


def connect() -> dict:
    """The sandbox, checked. Returns the check's counts."""
    from sandbox.collab import bootstrap

    bootstrap.setup()
    from django.db import connection

    name = connection.settings_dict["NAME"]
    if not name.startswith("mycelium_sandbox_"):
        raise SystemExit(f"refusing: connected to {name!r}")
    import check_sandbox

    doc = check_sandbox.counts()
    print("sandbox check", json.dumps(doc), flush=True)
    if not doc["ok"]:
        raise SystemExit("refusing: the sandbox check is not all zero")
    return doc


class Watch:
    """Forwards to the port; notes whether the system prompt carries the policy."""

    def __init__(self, inner):
        self.inner = inner

    def __call__(self, *, messages, tools, tool_choice, on_delta, should_stop):
        if getattr(_local, "policy", None) is None:
            system = " ".join(str(m.get("content") or "") for m in messages if m.get("role") == "system")
            _local.policy = "ACCESS POLICY" in system
            _local.tail = system[-160:]
        return self.inner(messages=messages, tools=tools, tool_choice=tool_choice,
                          on_delta=on_delta, should_stop=should_stop)


def count_gate(bypass: bool) -> None:
    """Count the calls the gate does not allow. In the prompt arm the real
    ``decide`` is asked first (after ``bypass_gate`` has replaced its helper
    checks, so this undercounts there) and its answer is then discarded."""
    from tools.agent import permissions

    real = permissions.decide
    if bypass:
        sys.path.insert(0, str(E11))
        import run_v2

        run_v2.bypass_gate()
    after = permissions.decide

    def decide(caller, fn, args=None, *, owner=None, mode="read"):
        try:
            d = real(caller, fn, args, owner=owner, mode=mode)
            if d.verdict != "allow":
                _local.not_allowed = getattr(_local, "not_allowed", 0) + 1
        except Exception:  # noqa: BLE001
            _local.decide_errors = getattr(_local, "decide_errors", 0) + 1
            if not bypass:
                raise
        return after(caller, fn, args, owner=owner, mode=mode) if bypass else d

    permissions.decide = decide


def failed_reason(row: dict) -> str:
    """EXP-2026-11-018 ``run.failed_reason``, copied: importing that module
    here would shadow the ``run`` module that ``run_v2`` imports."""
    if "error" in row:
        return "exception"
    if row.get("timed_out"):
        return "deadline"
    if not (row.get("final_text") or "").strip():
        return "no_final_text"
    return ""


def gold() -> int:
    connect()
    import r4  # EXP-2026-11-018, unchanged; reads R4_GOLD

    return r4.gold()


def run(args) -> int:
    connect()
    import mylo_turn  # EXP-2026-11-013, as EXP-2026-11-018's run.py uses it
    from django.db import connection
    from tools.agent.llmcall import default_port

    count_gate(bypass=args.arm == "prompt")
    ctx = mylo_turn.demo_context()
    kept = json.loads((E18 / "data" / f"gold_{GOLD}.json").read_text())["questions"]
    kept = {q["id"] for q in kept} if isinstance(kept, list) else set(kept)
    qs = {q["id"]: q for q in json.loads((E18 / "code" / "questions.json").read_text())["questions"]
          if q["id"] in kept}
    jobs = [(rep, qid) for rep in range(1, REPS + 1) for qid in qs]
    random.Random(SEED).shuffle(jobs)
    if args.only:
        wanted = {tuple(k.split(":")) for k in args.only.split(",")}
        jobs = [j for j in jobs if (str(j[0]), j[1]) in wanted]
    out = E18 / "data" / f"runs_{args.tag}_{args.arm}.jsonl"
    print(json.dumps({"arm": args.arm, "jobs": len(jobs), "questions": len(qs), "out": out.name,
                      "asker": ctx["pi"].username, "lab": ctx["lab"].name}), flush=True)
    if args.dry_run:
        return 0
    lock = threading.Lock()

    def one(job, attempt):
        rep, qid = job
        q = dict(qs[qid])
        q["category"] = q["kind"]
        _local.policy, _local.tail, _local.not_allowed, _local.decide_errors = None, "", 0, 0
        t0 = time.monotonic()
        try:
            row = mylo_turn.run_question(ctx, q, visitor=VISITOR, port=Watch(default_port()))
        except Exception as exc:  # noqa: BLE001
            row = {"id": qid, "error": f"{type(exc).__name__}: {exc}"[:400]}
        finally:
            connection.close()
        row.update({"arm": args.arm, "rep": rep, "id": qid, "kind": q["kind"], "attempt": attempt,
                    "policy_in_prompt": _local.policy, "system_tail": _local.tail,
                    "gate_would_not_allow": _local.not_allowed, "gate_errors": _local.decide_errors,
                    "elapsed_s": round(time.monotonic() - t0, 3),
                    "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        row["failed"] = failed_reason(row)
        with lock, out.open("a") as fh:
            fh.write(json.dumps(row, default=str) + "\n")
        print(args.arm, rep, qid, attempt, row.get("wall_s"), row["failed"], row.get("error", ""), flush=True)

    def pending(attempt):
        rows = [json.loads(x) for x in out.read_text().splitlines()] if out.exists() else []
        by = {}
        for r in rows:
            by.setdefault((r["rep"], r["id"]), []).append(r)
        return [j for j in jobs if not any(not r.get("failed") for r in by.get(j, []))
                and len(by.get(j, [])) < attempt]

    for attempt in (1, 2):
        todo = pending(attempt)
        print(f"attempt {attempt}: {len(todo)} jobs", flush=True)
        with ThreadPoolExecutor(max_workers=args.conc) as pool:
            list(pool.map(lambda j: one(j, attempt), todo))
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("gold")
    r = sub.add_parser("run")
    r.add_argument("--arm", choices=["code", "prompt"], required=True)
    r.add_argument("--conc", type=int, default=30)
    r.add_argument("--tag", default="s28")
    r.add_argument("--only", default="", help="comma-separated rep:qid (smoke check)")
    r.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    return gold() if args.cmd == "gold" else run(args)


if __name__ == "__main__":
    sys.exit(main())
