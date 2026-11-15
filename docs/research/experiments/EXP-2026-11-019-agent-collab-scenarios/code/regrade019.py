"""EXP-2026-11-019 Amendment 2: the answer point is what the reader sees.

When Mylo ends a turn with ``ask_user``, the person is shown the question (an
event of type ``question``, payload key ``question``) and the final assistant
text is empty. ``run019.turn_outcome`` (grading v1) read only the final text,
so such a turn looked vacuous and a name inside the question was never graded.
This re-reads every logged run's thread (threads are kept in
``mycelium_sandbox_exp019``) and grades the answer point again on the final
text **plus** every question of the turn (grading v2). The catalog and
function-results points are unchanged.

    (one-off backend container, as run019.py)
    python docs/research/experiments/EXP-2026-11-019-agent-collab-scenarios/code/regrade019.py --tag main

Writes ``logs/grades_v2_<arm>_<tag>.jsonl``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CODE = Path(__file__).resolve().parent
sys.path.insert(0, str(CODE))

import run019  # noqa: E402  (sets sys.path and SANDBOX_DB)


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
        if not src.exists():
            continue
        out = []
        for line in src.open():
            row = json.loads(line)
            run = runs[(row["scenario"], row["seeker"])]
            o = row.get("output") or {}
            final = o.get("text") or ""
            questions = []
            thread = AgentThread.objects.filter(pk=o.get("thread")).first() if o.get("thread") else None
            if thread is not None:
                questions = [
                    str(e.payload.get("question") or "")
                    for e in store.events(thread)
                    if e.type == "question"
                ]
            seen = "\n".join([final, *questions]).strip()
            fake = {
                "text": seen,
                "_catalog": "",
                "_results": "",
                "calls": row.get("calls") or [],
                "refused_at_open": o.get("refused_at_open"),
                "refused_at_send": o.get("refused_at_send"),
            }
            g = run019.grade(run, fake, names, world, plan, arm)
            v1 = row.get("violations") or {}
            viol = {"catalog": v1.get("catalog", []), "results": v1.get("results", []),
                    "answer": g["violations"]["answer"]}
            keep = {k: g[k] for k in g if k not in ("violations", "forbidden", "beyond_offered",
                                                     "for_call_offered", "outside_first",
                                                     "outside_used")}
            keep.update(
                violations=viol,
                violation_any=any(viol.values()),
                ended_on_question=bool(questions) and not final.strip(),
                questions=questions,
                thread_found=thread is not None,
            )
            out.append({"arm": arm, "rep": row["rep"], "scenario": row["scenario"],
                        "seeker": row["seeker"], **keep})
        dst = run019.HERE / "logs" / f"grades_v2_{arm}_{args.tag}.jsonl"
        dst.write_text("".join(json.dumps(r) + "\n" for r in out))
        print(arm, len(out), "rows;", sum(r["ended_on_question"] for r in out), "ended on a question;",
              sum(not r["thread_found"] for r in out), "threads missing")
    return 0


if __name__ == "__main__":
    sys.exit(main())
