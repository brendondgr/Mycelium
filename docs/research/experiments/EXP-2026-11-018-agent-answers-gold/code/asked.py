"""EXP-2026-11-018 Amendment 1: the clarifying questions turns ended on.

    docker compose run … python docs/research/experiments/EXP-2026-11-018-agent-answers-gold/code/asked.py

Read-only. For every row of ``data/runs.jsonl`` whose turn ended ``waiting``,
reads the thread's ``question`` events and writes ``data/asked.jsonl``. Run
before ``cleanup.py`` deletes the threads.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "EXP-2026-11-013-agent-answers-human-judged" / "code"))
import mylo_turn  # noqa: E402

mylo_turn.setup()
from tools.agent import store  # noqa: E402
from tools.agent.models import AgentThread  # noqa: E402

out = []
for line in (HERE.parent / "data" / "runs.jsonl").read_text().splitlines():
    r = json.loads(line)
    if r.get("state") != "waiting" or not r.get("thread"):
        continue
    t = AgentThread.objects.filter(pk=r["thread"]).first()
    qs = [e.payload for e in store.events(t) if e.type == "question"] if t else []
    out.append({"arm": r["arm"], "rep": r["rep"], "id": r["id"], "attempt": r.get("attempt"),
                "thread": r["thread"], "found": t is not None,
                "questions": [{"question": q.get("question"), "options": q.get("options")} for q in qs]})
(HERE.parent / "data" / "asked.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in out) + "\n")
print(len(out))
