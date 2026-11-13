"""EXP-2026-11-013: generate the answers raters will judge.

    docker compose run --rm --no-deps -T backend uv run --no-sync --project web/backend \
        python docs/research/experiments/EXP-2026-11-013-agent-answers-human-judged/code/generate.py \
        --arm a [--conc 4] [--tag main]
    ... generate.py --arm b --budget-from data/arm_a_main.jsonl [--tag main]

Arm a: Mylo as shipped (verifier and its one repair on), one fresh demo thread
per question, through ``mylo_turn.run_question`` (the Celery task's function,
called synchronously). Arm b: one ``corpus_search`` for the question, the
tagged items' cards plus as many search results' full records (the text
``corpus_item`` gives the agent) as fit in the mean total tokens of arm a, then
one model call through the same port with no tools.

Rows are appended to data/arm_<arm>_<tag>.jsonl as they finish.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mylo_turn  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
VISITOR = "EXP-2026-11-013"
CHARS_PER_TOKEN = 4
ANSWER_RESERVE = 1500  # tokens left for the answer and the instructions

SYSTEM_B = (
    "You are a research assistant for the principal investigator of {lab}. "
    "Answer the question using only the numbered evidence below. After each sentence "
    "that uses a piece of evidence, cite it as #n. Do not state any detail (author, "
    "venue, date, amount, number) that the evidence does not contain. If the evidence "
    "does not answer the question, say so plainly."
)


def arm_a(ctx, q):
    row = mylo_turn.run_question(ctx, q, visitor=VISITOR)
    return row


def evidence_for_b(ctx, q, budget_tokens):
    from tools.agent.caller import Audience, Caller, Scope
    from tools.agent.functions.corpus import corpus_item, corpus_search

    caller = Caller(user=ctx["pi"], surface="web", scope=Scope("lab", ctx["lab"]),
                    audience=Audience("person"))
    keys = [m.split(":", 1)[1] for m in q.get("mentions", [])]
    found = corpus_search(caller, q["text"], limit=20)
    keys += [str(info.key) for info in (found.refs or []) if str(info.key) not in keys]
    cap_chars = max(0, (budget_tokens - ANSWER_RESERVE)) * CHARS_PER_TOKEN
    blocks, used = [], 0
    for key in keys:
        try:
            content = corpus_item(caller, f"item:{key}").content
        except Exception:  # noqa: BLE001
            continue
        n = len(blocks) + 1
        text = content.split("\n", 1)
        head = text[0].split("}", 1)[-1].strip()
        block = f"#{n} {head}\n{text[1] if len(text) > 1 else ''}".strip()
        if used + len(block) > cap_chars and blocks:
            break
        blocks.append({"n": n, "key": key, "text": block})
        used += len(block)
    return blocks, found.content


def arm_b(ctx, q, budget_tokens):
    from tools.agent.llmcall import default_port

    blocks, search_listing = evidence_for_b(ctx, q, budget_tokens)
    evidence = "\n\n".join(b["text"] for b in blocks)
    messages = [
        {"role": "system", "content": SYSTEM_B.format(lab=ctx["lab"].name)},
        {"role": "user", "content": f"Evidence:\n\n{evidence}\n\nQuestion: {q['text']}"},
    ]
    port = default_port()
    t0 = time.monotonic()
    reply = port(messages=messages, tools=None, tool_choice=None, on_delta=None,
                 should_stop=None)
    usage = dict(reply.usage or {})
    import re

    text = reply.text or ""
    return {
        "id": q["id"], "category": q["category"], "wall_s": round(time.monotonic() - t0, 3),
        "final_text": text, "evidence": blocks, "budget_tokens": budget_tokens,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "cited": sorted({int(n) for n in re.findall(r"#(\d+)", text)}),
        "search_listing": search_listing,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--arm", choices=["a", "b"], required=True)
    p.add_argument("--conc", type=int, default=4)
    p.add_argument("--tag", default="main")
    p.add_argument("--only", default="")
    p.add_argument("--budget-from", default="")
    p.add_argument("--budget", type=int, default=0)
    args = p.parse_args()
    mylo_turn.setup()
    from django.db import connection

    ctx = mylo_turn.demo_context()
    qs = json.loads((HERE / "code" / "questions.json").read_text())["questions"]
    if args.only:
        qs = [q for q in qs if q["id"] in args.only.split(",")]
    out = HERE / "data" / f"arm_{args.arm}_{args.tag}.jsonl"
    out.parent.mkdir(exist_ok=True)
    budget = args.budget
    if args.arm == "b" and not budget:
        rows = [json.loads(x) for x in (HERE / args.budget_from).read_text().splitlines()]
        budget = round(statistics.mean(
            (r.get("prompt_tokens") or 0) + (r.get("completion_tokens") or 0)
            for r in rows if "error" not in r))
        print("budget tokens (mean arm a total):", budget, flush=True)
    lock = threading.Lock()

    def one(q):
        try:
            row = arm_a(ctx, q) if args.arm == "a" else arm_b(ctx, q, budget)
            row["category"] = q["category"]
        except Exception as exc:  # noqa: BLE001
            row = {"id": q["id"], "category": q["category"],
                   "error": f"{type(exc).__name__}: {exc}"[:400]}
        finally:
            connection.close()
        row["at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        with lock, out.open("a") as fh:
            fh.write(json.dumps(row, default=str) + "\n")
        print(q["id"], row.get("wall_s"), row.get("error", ""), flush=True)

    with ThreadPoolExecutor(max_workers=args.conc) as pool:
        list(pool.map(one, qs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
