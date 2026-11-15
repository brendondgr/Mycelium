"""EXP-2026-11-019 Amendment 3 (post hoc, written after the runs): what Mylo's
recall put in front of the model.

Every repetition asks the same seeker the same question, and Mylo recalls a
person's own earlier conversations (``recall`` events: "Earlier conversation
(…): …"). So a later run could see the seeker's earlier runs — of either arm,
and of the dry runs. ``run019.turn_outcome`` read recall events' ``content``
key, but their text is under ``text``, so recall was never graded. This reads
every logged run's recall text from the kept threads and reports, per run:
how many earlier threads the seeker had, whether recall was present, and any
person named in it outside the run's allowed set.

    (one-off backend container, as run019.py)
    python docs/research/experiments/EXP-2026-11-019-agent-collab-scenarios/code/recall019.py --tag main

Writes ``logs/recall_<arm>_<tag>.jsonl``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CODE = Path(__file__).resolve().parent
sys.path.insert(0, str(CODE))

import run019  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="main")
    args = ap.parse_args()
    run019.setup_django()
    import world019

    from tools.agent import store
    from tools.agent.models import AgentThread

    world = world019.base_world()
    plan = world019.plan(world)
    names = run019.Names(world)
    runs = {(r.scenario, r.seeker): r for r in plan.runs}
    for arm in ("gate", "baseline"):
        src = run019.HERE / "logs" / f"runs_{arm}_{args.tag}.jsonl"
        out = []
        for line in src.open():
            row = json.loads(line)
            run = runs[(row["scenario"], row["seeker"])]
            allowed, _ = run019.allowed_for(run, world, plan)
            thread = AgentThread.objects.filter(pk=(row.get("output") or {}).get("thread")).first()
            recall, earlier = "", None
            if thread is not None:
                recall = "\n".join(
                    str(e.payload.get("text") or e.payload.get("content") or "")
                    for e in store.events(thread)
                    if e.type == "recall"
                )
                earlier = AgentThread.objects.filter(
                    user=thread.user, created_at__lt=thread.created_at
                ).count()
            found = names.find(recall)
            out.append(
                {
                    "arm": arm,
                    "rep": row["rep"],
                    "scenario": row["scenario"],
                    "seeker": row["seeker"],
                    "earlier_threads": earlier,
                    "recall_present": bool(recall.strip()),
                    "recall_names": found,
                    "recall_outside": sorted(set(found) - allowed),
                    "recall_forbidden": sorted(set(found) & set(run.never_name)),
                }
            )
        dst = run019.HERE / "logs" / f"recall_{arm}_{args.tag}.jsonl"
        dst.write_text("".join(json.dumps(r) + "\n" for r in out))
        print(arm, len(out), "rows;", sum(r["recall_present"] for r in out), "with recall;",
              sum(bool(r["recall_outside"]) for r in out), "recall naming someone outside consent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
