"""EXP-2026-11-016: the permission gate, replicated over seeded worlds and a
second model.

    docker compose run --rm --no-deps -T --user $(id -u):$(id -g) -e HOME=/tmp \
        -v $PWD/docs/research:/app/docs/research \
        [-e EVAL2_LLM_MODEL=default-model-2] backend \
        uv run --no-sync --project web/backend python \
        docs/research/experiments/EXP-2026-11-016-agent-gate-replication/code/run_gate.py \
        --seed 101 --arm gate|prompt_only --model instance|second [--reps 3] [--conc 3] \
        [--tag main] [--dry-run]

One fresh database per (seed, arm, model): ``mycelium_agent_eval_r2_<seed>_<arm>_<model>``
(dropped and recreated at start), so no configuration sees another's threads.
Everything else is round one's harness, imported unchanged from
EXP-2026-11-011 (``run_v2.py``: capture port, three-point grader, the
prompt-only bypass and policy, ``run_plain``). ``--model second`` routes the
agent to ``EVAL2_LLM_MODEL`` on the same relay by replacing
``tools.agent.llmcall.model_name`` in this process only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CODE = Path(__file__).resolve().parent
HERE = CODE.parent
R1 = HERE.parent / "EXP-2026-11-011-mylo-agent-baseline" / "code"
sys.path[:0] = [str(CODE), str(R1)]
import run_v2  # noqa: E402  (inserts R1 and web/backend on sys.path)

sys.path.insert(0, str(CODE))  # keep this folder first for world_seeded / probes
import probes as P  # noqa: E402
import world_seeded  # noqa: E402

v1 = run_v2.v1
LOCK = threading.Lock()


def flow_narrow(task, w, base):
    """Round one's ``flow_narrow`` with the seed's project name."""
    from apps.research.models import Project
    from tools.agent import loop, service, store
    from tools.agent.caller import Caller, Scope

    world_seeded.reset_drift(w)
    user = w[task["persona"]]
    scope = Scope("lab", w["lab"])
    port = run_v2.CapturePort(base)
    thread = service.create_thread(user, scope=scope, surface="web")
    caller = Caller(user=user, surface="web", scope=scope, thread_id=thread.pk)
    service.send(caller, thread, P.NARROW_Q1, start=lambda t: None)
    loop.run_turn(thread.pk, port=port, caller=caller)
    first = run_v2.turn_outcome(thread, port)
    last_seq = max(e.seq for e in store.events(thread))
    n_calls = len(port.calls)
    Project.objects.filter(pk=w["drift"].pk).update(visibility="invite_only")
    try:
        service.send(caller, thread, P.NARROW_Q2, start=lambda t: None)
        t0 = time.monotonic()
        loop.run_turn(thread.pk, port=port, caller=caller)
        out = run_v2.turn_outcome(thread, port, since_seq=last_seq, call_from=n_calls)
        out["seconds"] = round(time.monotonic() - t0, 2)
    finally:
        world_seeded.reset_drift(w)
    drift = w["spec"]["drift"]
    out["precondition"] = {"surfaced_before": drift.lower() in first["text"].lower(),
                           "first_text": first["text"][:1500]}
    return out


def recreate_db(name):
    import psycopg

    url = re.sub(r"/[^/]+$", f"/{name}", os.environ["DATABASE_URL"])
    admin = re.sub(r"/[^/]+$", "/postgres", url)
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{name}"')
    return url


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--arm", choices=["gate", "prompt_only"], required=True)
    ap.add_argument("--model", choices=["instance", "second"], required=True)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--conc", type=int, default=3)
    ap.add_argument("--tag", default="main")
    ap.add_argument("--only", default="")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    spec = world_seeded.spec(args.seed)
    tasks = P.probes(spec)  # asserts no secret in any question
    if args.only:
        tasks = [t for t in tasks if t["id"] in args.only.split(",")]
    db = f"mycelium_agent_eval_r2_{args.seed}_{args.arm}_{args.model}"
    assert db.startswith("mycelium_agent_eval")
    url = recreate_db(db)
    os.environ["DATABASE_URL"] = url
    os.environ.setdefault("AGENT_PARALLEL_CALLS", "0")
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
    import tasks as _r1_tasks  # noqa: F401  (loads the files tool, as round one did)
    from tools.agent import llmcall, refs, stream

    refs.common_ref = run_v2.refs_token
    stream.use_memory_bus()
    w = world_seeded.build(spec)
    model = "default"
    if args.model == "second":
        model = os.environ["EVAL2_LLM_MODEL"]
        llmcall.model_name = lambda current=None: model
    else:
        model = llmcall.model_name()
    if args.arm == "prompt_only":
        run_v2.bypass_gate()
    base = v1.Dry() if args.dry_run else llmcall.default_port()
    if not args.dry_run:
        base(messages=[{"role": "user", "content": "Reply with: ok"}], tools=None,
             tool_choice=None, on_delta=None, should_stop=None)

    name = f"runs_{args.tag}_s{args.seed}_{args.arm}_{args.model}{'_dry' if args.dry_run else ''}.jsonl"
    log_path = HERE / "logs" / name
    log_path.parent.mkdir(exist_ok=True)
    from django.db import connection

    def one(job):
        task, rep = job
        try:
            out = flow_narrow(task, w, base) if task.get("flow") == "narrow" else \
                run_v2.run_plain(task, w, base)
            passed, checks, points = run_v2.grade_v2(task, out, w)
        except Exception as exc:  # noqa: BLE001
            out, passed, checks, points = ({"error": f"{type(exc).__name__}: {exc}"[:400]},
                                           False, {"error": True}, {})
        finally:
            connection.close()
        row = {"task": task["id"], "category": task["category"], "probe": task["probe"],
               "seed": args.seed, "arm": args.arm, "model": args.model, "model_name": model,
               "rep": rep, "passed": passed, **{f"check_{k}": v for k, v in checks.items()},
               "leaks": points, "tokens": out.get("tokens", 0), "seconds": out.get("seconds"),
               "steps": out.get("steps"), "denied": out.get("denied", 0),
               "question": task["text"], "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        keep = {k: v for k, v in out.items() if not k.startswith("_")}
        with LOCK, log_path.open("a") as fh:
            fh.write(json.dumps({**row, "output": keep}, default=str) + "\n")
        print(task["id"], rep, passed, {k: v for k, v in points.items() if v}, flush=True)

    plain = [t for t in tasks if not t.get("flow")]
    flows = [t for t in tasks if t.get("flow")]
    for rep in range(args.reps):
        with ThreadPoolExecutor(max_workers=args.conc) as pool:
            list(pool.map(one, [(t, rep) for t in plain]))
        for t in flows:  # changes a shared row: one at a time
            one((t, rep))
    (HERE / "data").mkdir(exist_ok=True)
    with (HERE / "data" / "worlds.jsonl").open("a") as fh:
        fh.write(json.dumps({"seed": args.seed, "arm": args.arm, "model": args.model,
                             "model_name": model, "db": db, "tag": args.tag,
                             "dry_run": args.dry_run, "spec": spec}) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
