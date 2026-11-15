"""EXP-2026-11-018: generate every answer — three arms × three repetitions × 60 questions.

    docker compose run --rm --no-deps -T --user $(id -u):$(id -g) -e HOME=/tmp \
        -e AGENT_PARALLEL_CALLS=0 -v $PWD/docs/research:/app/docs/research backend \
        uv run --no-sync --project web/backend python \
        docs/research/experiments/EXP-2026-11-018-agent-answers-gold/code/run.py [--conc 3] [--dry-run]

Arms (same instance model, same port):
- ``a``: Mylo as shipped (EXP-2026-11-013's ``mylo_turn.run_question``: a fresh
  demo thread per question, the Celery task's own loop, verifier on).
- ``b``: one ``corpus_search`` and one model call, EXP-2026-11-013's
  ``generate.arm_b`` unchanged, with a fixed budget of 27,100 tokens (round
  one's arm (a) mean; a ceiling arm (b) does not reach).
- ``c``: as ``a``, but the function catalog holds only the agent's own
  housekeeping functions and the corpus functions (``corpus_*``,
  ``fulltext_*``). The restriction is a proxy over the cached registry inside
  this process, switched per worker thread, so arms ``a`` and ``c`` can run
  side by side. Nothing in product code changes.

Jobs are shuffled with seed 20261115 so arms and repetitions interleave over
the night. Rows are appended to ``data/runs.jsonl``; a rerun skips finished
jobs. A failed job (exception, deadline hit, or no final text) is kept and
retried once at the end; both rows stay.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
R1 = EXP.parent / "EXP-2026-11-013-agent-answers-human-judged" / "code"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(R1))
import mylo_turn  # noqa: E402

VISITOR = "EXP-2026-11-018"
SEED = 20261115
REPS = 3
ARMS = ("a", "b", "c")
BUDGET_B = 27100
#: Arm c keeps these groups / prefixes; everything else is removed.
C_KEEP_PREFIX = ("corpus_", "fulltext_")
C_KEEP_NAMES = ("ask_user", "update_todos", "find_functions", "load_functions",
                "read_skill", "read_result", "thread_search")

_local = threading.local()


def install_arm_c_proxy():
    """Swap the cached registry for a proxy that serves a corpus-only copy to
    a worker thread whose ``_local.arm == 'c'``."""
    from dataclasses import replace

    from tools.agent import registry as regmod

    full = regmod.registry()
    keep = {n: fn for n, fn in full.functions.items()
            if n in C_KEEP_NAMES or n.startswith(C_KEEP_PREFIX)}
    corpus_only = replace(full, functions=keep,
                          owner={n: full.owner[n] for n in keep})

    class Proxy:
        def __getattr__(self, name):
            target = corpus_only if getattr(_local, "arm", "a") == "c" else full
            return getattr(target, name)

    regmod._cached = Proxy()
    return sorted(full.functions), sorted(keep)


def failed_reason(row: dict) -> str:
    if "error" in row:
        return "exception"
    if row.get("timed_out"):
        return "deadline"
    if not (row.get("final_text") or "").strip():
        return "no_final_text"
    return ""


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--conc", type=int, default=3)
    p.add_argument("--dry-run", action="store_true", help="list the jobs and the arm-c catalog; no model call")
    p.add_argument("--only", default="", help="comma-separated job keys arm:rep:qid (smoke tests)")
    p.add_argument("--out", default="data/runs.jsonl")
    args = p.parse_args()
    mylo_turn.setup()
    import generate  # EXP-2026-11-013 arm b, unchanged
    from django.db import connection

    full, kept = install_arm_c_proxy()
    ctx = mylo_turn.demo_context()
    qs = {q["id"]: q for q in json.loads((HERE / "questions.json").read_text())["questions"]}
    jobs = [(arm, rep, qid) for rep in range(1, REPS + 1) for arm in ARMS for qid in qs]
    random.Random(SEED).shuffle(jobs)
    if args.only:
        wanted = {tuple(k.split(":")) for k in args.only.split(",")}
        jobs = [j for j in jobs if (j[0], str(j[1]), j[2]) in wanted]
    out = EXP / args.out
    out.parent.mkdir(exist_ok=True)
    print(json.dumps({"jobs": len(jobs), "arm_c_catalog": kept,
                      "removed_in_c": [n for n in full if n not in kept]}), flush=True)
    if args.dry_run:
        return 0

    def load():
        rows = [json.loads(x) for x in out.read_text().splitlines()] if out.exists() else []
        return rows

    lock = threading.Lock()

    def one(job, attempt):
        arm, rep, qid = job
        q = dict(qs[qid])
        q["category"] = q["kind"]
        _local.arm = arm
        t0 = time.monotonic()
        try:
            if arm == "b":
                row = generate.arm_b(ctx, q, BUDGET_B)
            else:
                row = mylo_turn.run_question(ctx, q, visitor=VISITOR)
        except Exception as exc:  # noqa: BLE001
            row = {"id": qid, "error": f"{type(exc).__name__}: {exc}"[:400]}
        finally:
            _local.arm = "a"
            connection.close()
        row.update({"arm": arm, "rep": rep, "id": qid, "kind": q["kind"], "attempt": attempt,
                    "elapsed_s": round(time.monotonic() - t0, 3),
                    "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        row["failed"] = failed_reason(row)
        with lock, out.open("a") as fh:
            fh.write(json.dumps(row, default=str) + "\n")
        print(arm, rep, qid, attempt, row.get("wall_s"), row["failed"], row.get("error", ""), flush=True)

    def pending(attempt):
        rows = load()
        by = {}
        for r in rows:
            by.setdefault((r["arm"], r["rep"], r["id"]), []).append(r)
        todo = []
        for j in jobs:
            got = by.get(j, [])
            if any(not r.get("failed") for r in got):
                continue
            if len(got) >= attempt:
                continue
            todo.append(j)
        return todo

    for attempt in (1, 2):
        todo = pending(attempt)
        print(f"attempt {attempt}: {len(todo)} jobs", flush=True)
        with ThreadPoolExecutor(max_workers=args.conc) as pool:
            list(pool.map(lambda j: one(j, attempt), todo))
    return 0


if __name__ == "__main__":
    sys.exit(main())
