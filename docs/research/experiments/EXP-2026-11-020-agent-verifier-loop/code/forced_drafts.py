"""EXP-2026-11-020 5a: hand each sampled corrupted copy to the real loop as the
model's draft, and let the real repair run.

    docker compose run … python docs/research/experiments/EXP-2026-11-020-agent-verifier-loop/code/forced_drafts.py [--conc 3] [--only cite-01]

Per draft: a fresh demo thread as the demo PI asks round one's question (same
tags); the thread's reference table is set to the one the original answer was
written with; the loop's first model call is answered by a script that calls
one replayed function per stored function result (same content, same
reference numbers), and its second by the corrupted copy as the final draft.
From then on the instance model answers: the checker's verdict, the repair
note, the repair call and the final pass are the product's own code. Rows are
appended to ``data/forced_runs.jsonl``.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
sys.path.insert(0, str(HERE))
import harness as H  # noqa: E402

R1 = EXP.parent / "EXP-2026-11-013-agent-answers-human-judged"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--conc", type=int, default=3)
    ap.add_argument("--only", default="")
    ap.add_argument("--out", default="data/forced_runs.jsonl")
    args = ap.parse_args()
    H.setup()
    from django.db import connection

    from apps.accounts.models import Lab  # noqa: F401  (django ready)
    from tools.agent import loop
    from tools.agent.llmcall import default_port
    from tools.agent.models import AgentThread

    ctx = H.mylo_turn.demo_context()
    qs = {q["id"]: q for q in json.loads((R1 / "code" / "questions.json").read_text())["questions"]}
    originals = {}
    for tag in ("rep2", "rep3"):
        originals[tag] = {r["id"]: r for r in map(json.loads, (R1 / "data" / f"arm_a_{tag}.jsonl").read_text().splitlines())}
    sample = [json.loads(x) for x in (EXP / "data" / "forced_sample.jsonl").read_text().splitlines()]
    out = EXP / args.out
    done = set()
    if out.exists():
        done = {json.loads(x)["draft_id"] for x in out.read_text().splitlines() if x.strip()}
    todo = [s for s in sample if s["draft_id"] not in done
            and (not args.only or s["draft_id"] in args.only.split(","))]
    print("drafts to run:", len(todo), flush=True)
    lock = threading.Lock()

    def one(s):
        t0 = time.monotonic()
        row = {"draft_id": s["draft_id"], "cls": s["cls"], "token": s["token"], "answer": s["answer"], "tag": s["tag"]}
        try:
            orig = originals[s["tag"]][s["answer"]]
            q = qs[s["answer"]]
            thread, caller = H.new_thread(ctx, q)
            H.ask(caller, thread, q["text"], q.get("mentions", []))
            thread.refresh_from_db()
            settings = dict(thread.settings or {})
            row["refs_at_send"] = settings.get("refs", [])
            settings["refs"] = orig["refs"]
            AgentThread.objects.filter(pk=thread.pk).update(settings=settings)
            results = [r for r in orig.get("results") or [] if (r.get("status") or "ok") == "ok"]
            H.set_replay(thread.pk, results)
            script = []
            if results:
                script.append(H.response(calls=[{"id": f"replay-{i}", "name": r["name"], "args": {"replay": i}}
                                                for i, r in enumerate(results)]))
            script.append(H.response(text=s["draft"]))
            port = H.ScriptedPort(script, inner=default_port())
            loop.run_turn(thread.pk, port=port, caller=caller)
            row.update(H.outcome(thread))
            row.update({"thread": str(thread.pk), "scripted_calls": port.scripted, "real_calls": port.real,
                        "repair_s": round(sum(c["latency_s"] for c in port.real), 3),
                        "repair_tokens": sum((c["prompt_tokens"] or 0) + (c["completion_tokens"] or 0) for c in port.real),
                        "orig_refs": [e["n"] for e in orig["refs"]]})
        except Exception as exc:  # noqa: BLE001
            row["error"] = f"{type(exc).__name__}: {exc}"[:400]
        finally:
            connection.close()
        row["elapsed_s"] = round(time.monotonic() - t0, 3)
        row["at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with lock, out.open("a") as fh:
            fh.write(json.dumps(row, default=str, ensure_ascii=False) + "\n")
        print(s["draft_id"], row.get("elapsed_s"), row.get("error", ""), flush=True)

    with ThreadPoolExecutor(max_workers=args.conc) as pool:
        list(pool.map(one, todo))
    return 0


if __name__ == "__main__":
    sys.exit(main())
