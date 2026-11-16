"""EXP-2026-11-019 Amendment 4 (round three, Phase 1): does Mylo answer?

Scenarios S1, S2 and S10, gate arm only, the ten seekers each, three
repetitions, in two modes, each on its own copy of the sandbox:

* ``repeated`` (``mycelium_sandbox_exp019r3rep``): the same seeker re-asks every
  repetition, as in round two, so recall brings back their earlier asks;
* ``fresh`` (``mycelium_sandbox_exp019r3fresh``): before every turn the seeker's
  earlier Mylo threads (and with them their digests, recall's only source with
  learning and ambient off) are deleted, so no repetition sees an earlier one.

Everything else is ``run019.py`` unchanged (world, plan, ``run_one``, ``grade``),
imported; the answer is graded as round two's grading v2 (final text + every
clarifying question). ``r3turns.Recorder`` keeps what the model returned on
every call. ``--model second`` routes the agent to ``EVAL2_LLM_MODEL``.

    docker compose exec -T postgres psql -U mycelium -d postgres \
      -c 'CREATE DATABASE "mycelium_sandbox_exp019r3<mode>" TEMPLATE "mycelium_sandbox"'
    R="docker compose run --rm --no-deps -T --user $(id -u):$(id -g) -e HOME=/tmp \
       -e SANDBOX_DB=mycelium_sandbox_exp019r3<mode> -e AGENT_PARALLEL_CALLS=0 \
       -e EVAL_MODEL_NAME=… -v $PWD/docs/research:/app/docs/research backend \
       uv run --no-sync --project web/backend python \
       docs/research/experiments/EXP-2026-11-019-agent-collab-scenarios/code"
    $R/run019_r3.py --mode <mode> --setup                # migrate, overlay, preflight (once per copy)
    $R/run019_r3.py --mode <repeated|fresh> --rep R --conc 4 --tag r3
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
sys.path.insert(0, str(CODE))
DBS = {"repeated": "mycelium_sandbox_exp019r3rep", "fresh": "mycelium_sandbox_exp019r3fresh"}

import run019  # noqa: E402
import r3turns  # noqa: E402

LOCK = threading.Lock()
SCENARIOS = ("S1", "S2", "S10")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=list(DBS), required=True)
    ap.add_argument("--rep", type=int, default=0)
    ap.add_argument("--setup", action="store_true", help="migrate, overlay, preflight; no model")
    ap.add_argument("--conc", type=int, default=4)
    ap.add_argument("--tag", default="r3")
    ap.add_argument("--model", choices=["instance", "second"], default="instance")
    args = ap.parse_args()
    assert args.conc <= 8  # Amendment 5 (019) / Amendment 3 (016): at most 8 in flight
    assert os.environ.get("SANDBOX_DB") == DBS[args.mode], "SANDBOX_DB must name this mode's copy"
    run019.EXP_DB = DBS[args.mode]
    env = run019.setup_django()
    import world019
    from django.db import connection

    from tools.agent import llmcall
    from tools.agent.models import AgentThread
    from tools.retrieval.models import ContentItem

    world = world019.base_world()
    plan = world019.plan(world)
    if args.setup:
        # run019.py --setup, writing to its own file (round two's data/world.json is kept).
        from django.core.management import call_command

        call_command("migrate", verbosity=0)
        out = {"env": env, "plan": plan.as_dict(), "apply": world019.apply(world, plan),
               "uniqueness": world019.uniqueness(world), "preflight": world019.preflight(world, plan)}
        (run019.HERE / "data" / f"world_r3_{args.mode}.json").write_text(
            json.dumps(out, indent=1, default=str))
        print(json.dumps({"env": env, "uniqueness": out["uniqueness"],
                          "preflight_failures": out["preflight"]["failures"]}, indent=1, default=str))
        return 1 if out["preflight"]["failures"] else 0
    items = {i.external_id: i for i in ContentItem.objects.filter(source=world019.SOURCE)}
    assert set(items) == set(plan.calls), "run run019.py --setup on this copy first"
    if args.model == "second":
        name = os.environ["EVAL2_LLM_MODEL"]
        llmcall.model_name = lambda current=None: name
    inner = llmcall.default_port()
    base = r3turns.Recorder(inner)
    model = llmcall.model_name()
    names = run019.Names(world)
    runs = [r for r in plan.runs if r.scenario in SCENARIOS]
    log = run019.HERE / "logs" / f"runs_r3_{args.mode}_{args.model}_{args.tag}.jsonl"
    log.parent.mkdir(exist_ok=True)
    with LOCK, log.open("a") as fh:
        fh.write(json.dumps({"marker": "start", "rep": args.rep, "env": env, "model": model,
                             "stated": os.environ.get("EVAL2_MODEL_NAME" if args.model == "second"
                                                      else "EVAL_MODEL_NAME") or "not stated by the operator",
                             "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}) + "\n")

    def one(run, attempt=1):
        r3turns.begin()
        prior = 0
        try:
            if args.mode == "fresh":
                with LOCK:
                    prior, _ = AgentThread.objects.filter(user__username=run.seeker).delete()
            out = run019.run_one(run, plan, items, base)
            thread = AgentThread.objects.filter(pk=out.get("thread")).first() if out.get("thread") else None
            facts = r3turns.thread_facts(thread) if thread is not None else {"questions": []}
            final = out.get("text") or ""
            seen = "\n".join([final, *facts["questions"]]).strip()
            graded_out = dict(out, text=seen)
            g = run019.grade(run, graded_out, names, world, plan, "gate")
            cls = r3turns.outcome(final, facts["questions"], out.get("errors") or ())
            if out.get("refused_at_open") or out.get("refused_at_send"):
                cls = "refused"
            failed = bool(out.get("errors"))
        except Exception as exc:  # noqa: BLE001
            out, g, facts, cls, failed = ({"exception": f"{type(exc).__name__}: {exc}"[:500]}, {},
                                          {}, "error", True)
        finally:
            connection.close()
        calls = r3turns.calls()
        row = {"scenario": run.scenario, "variant": run.variant, "seeker": run.seeker,
               "arm": "gate", "mode": args.mode, "model_arm": args.model, "rep": args.rep,
               "model": model, "attempt": attempt, "outcome": cls, "failed": failed,
               "prior_threads_deleted": prior, **g,
               "seconds": out.get("seconds"), "tokens": out.get("tokens", 0),
               "calls": out.get("calls"), **{k: v for k, v in facts.items()},
               **r3turns.summary(calls), "model_call_log": calls,
               "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        keep = {k: v for k, v in out.items() if not k.startswith("_")}
        keep["results_head"] = (out.get("_results") or "")[:3000]
        with LOCK, log.open("a") as fh:
            fh.write(json.dumps({**row, "output": keep}, default=str) + "\n")
        print(run.scenario, run.seeker, args.mode, args.rep, attempt, cls, g.get("must_named"),
              out.get("seconds"), flush=True)
        return cls

    with ThreadPoolExecutor(max_workers=args.conc) as pool:
        got = list(pool.map(one, runs))
    retry = [r for r, c in zip(runs, got) if c == "failed"]  # once, both rows kept
    with ThreadPoolExecutor(max_workers=args.conc) as pool:
        list(pool.map(lambda r: one(r, 2), retry))
    with LOCK, log.open("a") as fh:
        fh.write(json.dumps({"marker": "end", "rep": args.rep, "model": model,
                             "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
