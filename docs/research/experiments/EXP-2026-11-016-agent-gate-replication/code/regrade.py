"""EXP-2026-11-016 Amendment 1: grade what the reader sees — the final text
**and** any clarifying question (``ask_user``, stored as a ``question`` event).

    docker compose run ... backend uv run --no-sync --project web/backend \
        python docs/research/experiments/EXP-2026-11-016-agent-gate-replication/code/regrade.py

For every counted run with a thread id, opens that configuration's database
(``mycelium_agent_eval_r2_<seed>_<arm>_<model>``, kept after the run), reads the
thread's ``question`` events, and writes ``data/regrade_a1.jsonl``:
``{key, question_text, reply_seen, answer_leak_a1}``. ``scope-narrowed`` keeps
no thread id in its log and is graded as before (its two turns are reported as
logged).
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
REPO = Path(__file__).resolve().parents[5]
sys.path[:0] = [str(REPO / "web" / "backend"), str(REPO)]
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


def main() -> int:
    import psycopg

    base = os.environ["DATABASE_URL"]
    out_path = HERE / "data" / "regrade_a1.jsonl"
    out = out_path.open("w")
    n = 0
    for path in sorted((HERE / "logs").glob("runs_main_s*.jsonl")):
        m = re.match(r"runs_main_s(\d+)_(gate|prompt_only)_(instance|second)\.jsonl", path.name)
        if not m:
            continue
        db = f"mycelium_agent_eval_r2_{m.group(1)}_{m.group(2)}_{m.group(3)}"
        url = re.sub(r"/[^/]+$", f"/{db}", base)
        rows = [json.loads(line) for line in path.open()]
        with psycopg.connect(url) as conn:
            for r in rows:
                thread = (r.get("output") or {}).get("thread")
                questions = []
                if thread:
                    cur = conn.execute(
                        "SELECT payload FROM agent_agentevent WHERE thread_id=%s AND type='question'"
                        " ORDER BY seq", (thread,))
                    questions = [str((p or {}).get("question") or "") for (p,) in cur.fetchall()]
                qtext = "\n".join(q for q in questions if q)
                seen = "\n".join(x for x in [(r["output"].get("text") or ""), qtext] if x.strip())
                strings = r.get("not_contains_strings")
                key = f"{r['seed']}|{r['arm']}|{r['model']}|{r['task']}|{r['rep']}"
                out.write(json.dumps({"key": key, "file": path.name, "task": r["task"],
                                      "rep": r["rep"], "thread": thread,
                                      "question_text": qtext, "reply_seen": seen}) + "\n")
                n += 1
    out.close()
    print(f"{n} runs re-read")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
