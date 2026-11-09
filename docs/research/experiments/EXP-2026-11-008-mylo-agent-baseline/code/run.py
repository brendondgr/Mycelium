"""EXP-2026-11-008: the Mylo agent baseline.

Seeds a deterministic world into its own database (``mycelium_agent_eval``),
runs every task three times with the instance's model, grades outcomes, and
writes data/metrics.json, data/metrics.csv and logs/runs.jsonl.

    UV_PROJECT_ENVIRONMENT=~/.cache/mycelium-backend-venv \\
      uv run --no-sync --project web/backend python \\
      docs/research/experiments/EXP-2026-11-008-mylo-agent-baseline/code/run.py [--dry-run]

``--dry-run`` replaces the model with a scripted one that answers every task
with "I can't tell." — it checks the harness (seeding, threads, graders,
writing), produces no metrics, and writes logs/dry_run.json only.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
REPO = Path(__file__).resolve().parents[5]
sys.path[:0] = [str(Path(__file__).resolve().parent), str(REPO / "web" / "backend"),
                str(REPO)]
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
EVAL_DB = "mycelium_agent_eval"


def _eval_url() -> str:
    url = os.environ.get("DATABASE_URL", "postgres://mycelium:mycelium@localhost:11450/mycelium")
    return re.sub(r"/[^/]+$", f"/{EVAL_DB}", url)


def _ensure_db(url: str) -> None:
    import psycopg

    admin = re.sub(r"/[^/]+$", "/postgres", url)
    with psycopg.connect(admin, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname=%s",
                              (EVAL_DB,)).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{EVAL_DB}"')


class Dry:
    def __call__(self, *, messages, tools, tool_choice, on_delta, should_stop):
        from apps.core.llm import LLMResponse

        return LLMResponse(content="I can't tell.", usage={"total_tokens": 1})


def run_task(task, w, port, rep):
    from tools.agent import loop, refs, service, store
    from tools.agent.caller import Audience, Caller, Scope

    user = w[task["persona"]]
    if task["before"]:
        speaker = w[task["before_persona"] or task["persona"]]
        prior = service.create_thread(speaker, scope=Scope("personal"))
        for text in task["before"]:
            service.send(Caller(user=speaker, surface="web", thread_id=prior.pk), prior, text,
                         start=lambda t: None)
            loop.run_turn(prior.pk, port=port)
    kind = task["scope"]
    obj = {"lab": w["lab"], "project": w["seg"], "other_project": w["secret"]}.get(kind)
    kind = "project" if kind == "other_project" else kind
    try:
        thread = service.create_thread(user, scope=Scope(kind, obj), surface=task["surface"])
    except service.ServiceError as exc:
        return {"refused_at_open": exc.code, "text": "", "events": 0, "tokens": 0, "cites": []}
    caller = Caller(user=user, surface=task["surface"], scope=Scope(kind, obj),
                    audience=Audience(task["audience"]), thread_id=thread.pk)
    mentions = [refs.common_ref(w[m]) for m in task["mentions"]]
    try:
        service.send(caller, thread, task["text"], mentions=mentions, start=lambda t: None)
    except service.ServiceError as exc:
        return {"refused_at_send": exc.code, "text": "", "events": 0, "tokens": 0, "cites": []}
    started = time.monotonic()
    loop.run_turn(thread.pk, port=port, caller=caller)
    events = store.events(thread)
    final = [e.payload.get("text", "") for e in events
             if e.type == "assistant" and e.payload.get("final")]
    cited = sorted({int(n) for n in re.findall(r"#(\d+)", final[-1] if final else "")})
    by_n = {e["n"]: e["ref"] for e in refs.thread_refs(thread)}
    return {
        "text": final[-1] if final else "",
        "seconds": round(time.monotonic() - started, 2),
        "events": len(events),
        "steps": sum(1 for e in events if e.type == "assistant"),
        "calls": [e.payload.get("name") for e in events if e.type == "tool_call"],
        "denied": sum(1 for e in events if e.type == "tool_result"
                      and e.payload.get("status") == "denied"),
        "tokens": sum(e.tokens for e in events if e.type == "usage"),
        "cites": [by_n.get(n) for n in cited],
    }


def grade(task, out, w):
    from tools.agent import refs
    from tools.recommendation.read import RelevanceScore, order_by_slate

    text = (out.get("text") or "").lower()
    checks = {}
    if task["contains_any"]:
        checks["contains"] = any(s.lower() in text for s in task["contains_any"])
    checks["no_leak"] = not any(s.lower() in text for s in task["not_contains"])
    if task["cites"]:
        want = {refs.common_ref(w[k]) for k in task["cites"]}
        checks["cites"] = want <= set(out.get("cites") or [])
    if task["overlap_top"]:
        slate = order_by_slate(RelevanceScore.objects.filter(
            target_project=w["seg"], content__type="paper"))[:3]
        top = {f"item:{s.content_id}" for s in slate}
        checks["overlap"] = len(top & set(out.get("cites") or [])) >= task["overlap_top"]
    return all(checks.values()), checks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reps", type=int, default=3)
    parser.add_argument("--only", default="")
    args = parser.parse_args()
    url = _eval_url()
    _ensure_db(url)
    os.environ["DATABASE_URL"] = url
    os.environ.setdefault("AGENT_PARALLEL_CALLS", "0")
    import django

    django.setup()
    from django.conf import settings
    from django.core.management import call_command

    assert settings.DATABASES["default"]["NAME"] == EVAL_DB
    call_command("migrate", verbosity=0)
    import world
    from tasks import TASKS

    from tools.agent import llmcall, refs, stream

    def common_ref(obj):
        from apps.research.models import Project

        if isinstance(obj, Project):
            return f"project:{obj.pk}"
        return f"item:{obj.pk}"

    refs.common_ref = common_ref
    stream.use_memory_bus()
    w = world.seed()
    world.store_file(w)
    port = Dry() if args.dry_run else llmcall.default_port()
    if not args.dry_run:
        # A dead endpoint must abort the run, not grade thirty failed turns.
        port(messages=[{"role": "user", "content": "Reply with: ok"}], tools=None,
             tool_choice=None, on_delta=None, should_stop=None)
    model = "dry-run" if args.dry_run else llmcall.model_name()
    rows = []
    log = (HERE / "logs" / ("dry_run.jsonl" if args.dry_run else "runs.jsonl")).open("w")
    for task in TASKS:
        if args.only and task["category"] != args.only:
            continue
        for rep in range(args.reps):
            out = run_task(task, w, port, rep)
            passed, checks = grade(task, out, w)
            row = {"task": task["id"], "category": task["category"], "rep": rep,
                   "passed": passed, **{f"check_{k}": v for k, v in checks.items()},
                   "tokens": out.get("tokens", 0), "seconds": out.get("seconds"),
                   "steps": out.get("steps"), "denied": out.get("denied", 0)}
            rows.append(row)
            log.write(json.dumps({**row, "output": out}, default=str) + "\n")
    log.close()
    by_cat = {}
    for row in rows:
        by_cat.setdefault(row["category"], []).append(row)
    summary = {"model": model, "tasks": len({r["task"] for r in rows}), "reps": args.reps}
    for cat, rs in sorted(by_cat.items()):
        tasks = {}
        for r in rs:
            tasks.setdefault(r["task"], []).append(r["passed"])
        summary[f"pass_rate@{cat}"] = round(sum(r["passed"] for r in rs) / len(rs), 3)
        summary[f"pass_all_reps@{cat}"] = sum(all(v) for v in tasks.values())
        summary[f"tokens_mean@{cat}"] = round(sum(r["tokens"] for r in rs) / len(rs))
    summary["leaks"] = sum(1 for r in rows if not r.get("check_no_leak", True))
    if args.dry_run:
        (HERE / "logs" / "dry_run.json").write_text(json.dumps(summary, indent=1))
        print(json.dumps(summary, indent=1))
        return 0
    (HERE / "data" / "metrics.json").write_text(json.dumps(
        {"summary": summary, "rows": rows}, indent=1))
    with (HERE / "data" / "metrics.csv").open("w", newline="") as fh:
        keys = sorted({k for r in rows for k in r})
        writer = csv.DictWriter(fh, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        (HERE / "logs").mkdir(exist_ok=True)
        (HERE / "logs" / "attempt.json").write_text(json.dumps({
            "when": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "error": f"{type(exc).__name__}: {exc}"[:500]}, indent=1))
        print(f"run failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
