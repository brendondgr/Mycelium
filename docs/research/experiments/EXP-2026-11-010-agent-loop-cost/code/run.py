"""EXP-2026-11-010: latency and tokens per step of a scripted tool loop.

The model calls are real; the function results are scripted (a fixed ~1 500
character result per call), so the only thing measured is what the model and
the growing context cost. For N in (1, 5, 15) the loop asks the model to keep
calling ``corpus_search`` until N calls have been made, then to answer.

Run from the repository root:

    UV_PROJECT_ENVIRONMENT=~/.cache/mycelium-backend-venv \\
      uv run --no-sync --project web/backend python \\
      docs/research/experiments/EXP-2026-11-010-agent-loop-cost/code/run.py

Writes data/metrics.json and data/metrics.csv, and logs/run.log. Exits non-zero
(and writes logs/attempt.json) when the endpoint cannot be reached.
"""

from __future__ import annotations

import csv
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
REPO = Path(__file__).resolve().parents[5]
sys.path[:0] = [str(REPO / "web" / "backend"), str(REPO)]
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

STEPS = (1, 5, 15)
REPS = 3
RESULT = ("Matches for the query (scripted result):\n" + "\n".join(
    f"- #{i} [paper] A plausible paper title about segmentation and uncertainty, "
    f"number {i}, with authors and a venue" for i in range(1, 15)))


def main() -> int:
    import django

    django.setup()
    from django.conf import settings

    from apps.core.llm import build_llm_client
    from tools.agent import prompt
    from tools.agent.registry import registry

    model = settings.LLM_MODEL
    client = build_llm_client(component="agent.experiment")
    tools = [fn.schema() for fn in registry().functions.values() if fn.core]
    system = prompt.BASE_RULES
    rows, log = [], []
    for steps in STEPS:
        for rep in range(REPS):
            messages = [{"role": "system", "content": system}, {"role": "user", "content": (
                f"Call corpus_search exactly {steps} times, each with a different query "
                "about cell segmentation, one call per step, then answer in one sentence.")}]
            for step in range(1, steps + 2):
                first = []
                started = time.monotonic()
                response = client.complete_stream(
                    messages, model=model, tools=tools,
                    tool_choice="auto" if step <= steps else "none",
                    on_delta=lambda k, t: first.append(time.monotonic()) if not first else None,
                )
                total = time.monotonic() - started
                usage = dict(response.usage or {})
                rows.append({
                    "steps": steps, "rep": rep, "step": step,
                    "latency_s": round(total, 3),
                    "first_delta_s": round(first[0] - started, 3) if first else None,
                    "prompt_tokens": usage.get("prompt_tokens"),
                    "completion_tokens": usage.get("completion_tokens"),
                    "called": len(response.tool_calls),
                })
                log.append(rows[-1])
                if not response.tool_calls:
                    break
                call = response.tool_calls[0]
                messages.append({"role": "assistant", "content": response.content or None,
                                 "tool_calls": [call.as_dict()]})
                messages.append({"role": "tool", "tool_call_id": call.id, "content": RESULT})
    summary = {}
    for steps in STEPS:
        turn = [r for r in rows if r["steps"] == steps]
        per_rep = {}
        for r in turn:
            per_rep.setdefault(r["rep"], []).append(r)
        turn_latency = [sum(x["latency_s"] for x in rs) for rs in per_rep.values()]
        turn_tokens = [sum((x["prompt_tokens"] or 0) + (x["completion_tokens"] or 0)
                           for x in rs) for rs in per_rep.values()]
        summary[f"turn_latency_s_mean@{steps}"] = round(sum(turn_latency) / len(turn_latency), 2)
        summary[f"turn_tokens_mean@{steps}"] = round(sum(turn_tokens) / len(turn_tokens))
        summary[f"step_latency_s_mean@{steps}"] = round(
            sum(r["latency_s"] for r in turn) / len(turn), 2)
    (HERE / "data").mkdir(exist_ok=True)
    (HERE / "data" / "metrics.json").write_text(json.dumps(
        {"model": model, "summary": summary, "rows": rows}, indent=1))
    with (HERE / "data" / "metrics.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (HERE / "logs").mkdir(exist_ok=True)
    (HERE / "logs" / "run.log").write_text("\n".join(json.dumps(r) for r in log))
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # record the failed attempt, as the rules require
        (HERE / "logs").mkdir(exist_ok=True)
        (HERE / "logs" / "attempt.json").write_text(json.dumps({
            "when": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "error": f"{type(exc).__name__}: {exc}"[:500]}, indent=1))
        print(f"run failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
