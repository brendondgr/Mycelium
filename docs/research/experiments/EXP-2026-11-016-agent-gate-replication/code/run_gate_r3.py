"""EXP-2026-11-016 Amendment 2 (round three, Phase 1): does Mylo answer the
gate probes that most often ended on nothing?

The two controls and the five access probes with the most turns that ended
with no reply in round two's gate arm (``data/regrade_a1.jsonl``, reply seen
empty): ``probe-viewer`` 6, ``scope-viewer-files`` 4, ``scope-directory-only`` 2,
``scope-invite-only`` 2, ``probe-outsider-project`` 1 (tied with
``probe-other-lab`` at 1; the tie goes to the earlier in ``probes.py``). Gate
arm, seeds 101, 202 and 303, three repetitions.

``run_gate.py`` unchanged otherwise (world, ``run_v2.run_plain``, ``grade_v2``),
except: a fresh database per (seed, model) named
``mycelium_agent_eval_r3_<seed>_gate_<model>`` so round two's kept databases
are never dropped; the answer is graded on the reply seen (Amendment 1); and
EXP-2026-11-019's ``r3turns.Recorder`` keeps what the model returned on every
call.

    docker compose run --rm --no-deps -T --user $(id -u):$(id -g) -e HOME=/tmp \
        -e AGENT_PARALLEL_CALLS=0 -e EVAL_MODEL_NAME=… \
        -v $PWD/docs/research:/app/docs/research backend \
        uv run --no-sync --project web/backend python \
        docs/research/experiments/EXP-2026-11-016-agent-gate-replication/code/run_gate_r3.py \
        --seed 101 [--model instance|second] [--reps 3] [--conc 4] [--tag r3]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CODE = Path(__file__).resolve().parent
HERE = CODE.parent
R1 = HERE.parent / "EXP-2026-11-011-mylo-agent-baseline" / "code"
C019 = HERE.parent / "EXP-2026-11-019-agent-collab-scenarios" / "code"
sys.path[:0] = [str(CODE), str(R1)]
import run_v2  # noqa: E402

sys.path.insert(0, str(CODE))
import probes as P  # noqa: E402
import run_gate  # noqa: E402
import world_seeded  # noqa: E402

TASKS = ("probe-viewer", "scope-viewer-files", "scope-directory-only", "scope-invite-only",
         "probe-outsider-project", "scope-head-oversight", "scope-member-control")
LOCK = threading.Lock()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--model", choices=["instance", "second"], default="instance")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--conc", type=int, default=4)
    ap.add_argument("--tag", default="r3")
    args = ap.parse_args()
    assert args.conc <= 4
    spec = world_seeded.spec(args.seed)
    tasks = [t for t in P.probes(spec) if t["id"] in TASKS]
    assert len(tasks) == len(TASKS)
    db = f"mycelium_agent_eval_r3_{args.seed}_gate_{args.model}"
    os.environ["DATABASE_URL"] = run_gate.recreate_db(db)
    import django
    from django.conf import settings

    django.setup()
    assert settings.DATABASES["default"]["NAME"] == db
    settings.CACHES["ambient"] = {"BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                                  "LOCATION": "eval-ambient"}
    from django.core.cache import caches

    try:
        del caches["ambient"]
    except Exception:  # noqa: BLE001
        pass
    settings.AGENT_LEARNING = True
    settings.AMBIENT_ENABLED = False
    from config.celery import app as celery_app

    celery_app.conf.task_always_eager = True
    from django.core.management import call_command

    call_command("migrate", verbosity=0)
    import tasks as _r1_tasks  # noqa: F401
    from django.db import connection

    sys.path.insert(0, str(C019))
    import r3turns

    from tools.agent import llmcall, refs, stream
    from tools.agent.models import AgentThread

    refs.common_ref = run_v2.refs_token
    stream.use_memory_bus()
    w = world_seeded.build(spec)
    if args.model == "second":
        name = os.environ["EVAL2_LLM_MODEL"]
        llmcall.model_name = lambda current=None: name
    model = llmcall.model_name()
    base = r3turns.Recorder(llmcall.default_port())
    log = HERE / "logs" / f"runs_{args.tag}_s{args.seed}_gate_{args.model}.jsonl"
    stated = os.environ.get("EVAL2_MODEL_NAME" if args.model == "second" else "EVAL_MODEL_NAME") \
        or "not stated by the operator"
    with LOCK, log.open("a") as fh:
        fh.write(json.dumps({"marker": "start", "db": db, "model": model, "stated": stated,
                             "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}) + "\n")

    def one(job, attempt=1):
        task, rep = job
        r3turns.begin()
        try:
            out = run_v2.run_plain(task, w, base)
            thread = AgentThread.objects.filter(pk=out.get("thread")).first() if out.get("thread") else None
            facts = r3turns.thread_facts(thread) if thread is not None else {"questions": []}
            final = out.get("text") or ""
            seen = "\n".join(x for x in [final, *facts["questions"]] if x.strip())
            passed, checks, points = run_v2.grade_v2(task, dict(out, text=seen), w)
            cls = r3turns.outcome(final, facts["questions"], out.get("errors") or ())
            if out.get("refused_at_open") or out.get("refused_at_send"):
                cls = "refused"
        except Exception as exc:  # noqa: BLE001
            out, facts, passed, checks, points, cls = (
                {"error": f"{type(exc).__name__}: {exc}"[:400]}, {}, False, {"error": True}, {}, "error")
        finally:
            connection.close()
        calls = r3turns.calls()
        row = {"task": task["id"], "category": task["category"], "probe": task["probe"],
               "seed": args.seed, "arm": "gate", "model": args.model, "model_name": model,
               "rep": rep, "attempt": attempt, "outcome": cls, "passed": passed,
               **{f"check_{k}": v for k, v in checks.items()}, "leaks": points,
               "tokens": out.get("tokens", 0), "seconds": out.get("seconds"),
               "steps": out.get("steps"), "denied": out.get("denied", 0),
               **{k: v for k, v in facts.items()}, **r3turns.summary(calls),
               "model_call_log": calls, "question": task["text"],
               "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        keep = {k: v for k, v in out.items() if not k.startswith("_")}
        with LOCK, log.open("a") as fh:
            fh.write(json.dumps({**row, "output": keep}, default=str) + "\n")
        print(task["id"], rep, attempt, cls, passed, {k: v for k, v in points.items() if v}, flush=True)
        return cls

    for rep in range(args.reps):
        jobs = [(t, rep) for t in tasks]
        with ThreadPoolExecutor(max_workers=args.conc) as pool:
            got = list(pool.map(one, jobs))
        retry = [j for j, c in zip(jobs, got) if c == "failed"]  # once, both rows kept
        with ThreadPoolExecutor(max_workers=args.conc) as pool:
            list(pool.map(lambda j: one(j, 2), retry))
    with LOCK, log.open("a") as fh:
        fh.write(json.dumps({"marker": "end", "db": db, "model": model,
                             "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
