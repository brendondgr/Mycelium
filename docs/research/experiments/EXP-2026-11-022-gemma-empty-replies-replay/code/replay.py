"""EXP-2026-11-022: EXP-2026-11-016's round-two harness, replayed with the
product code frozen at a chosen commit, logging every raw model reply.

    docker compose run --rm --no-deps -T --user $(id -u):$(id -g) -e HOME=/tmp \
        -e LLM_MODEL=default-model -e AGENT_PARALLEL_CALLS=0 \
        -v <snap>/tools:/app/tools:ro -v <snap>/web/backend:/app/web/backend:ro \
        -v $PWD/web/backend/media:/app/web/backend/media \
        -v $PWD/docs/research:/app/docs/research backend \
        uv run --no-sync --project web/backend python \
        docs/research/experiments/EXP-2026-11-022-gemma-empty-replies-replay/code/replay.py \
        --label f1115 --seed 101 --arm prompt_only [--reps 1] [--conc 3] [--dry-run]

Differences from ``EXP-2026-11-016/code/run_gate.py`` (whose world, probes,
``flow_narrow`` and round one's ``run_v2`` are imported unchanged):

* its own database, ``mycelium_agent_eval_x022_<label>_<seed>_<arm>`` (never
  round two's, which hold the 2026-11-15 threads);
* its own logs, in this folder;
* the model port is wrapped: every model call is written to
  ``logs/calls_<label>_s<seed>_<arm>.jsonl`` (finish reason, usage, content,
  call names, the function names offered, tool_choice);
* when a call comes back with no text and no call, one diagnostic request is
  sent beside it (same messages and functions, ``tool_choice: none``,
  ``skip_special_tokens: false``, not streamed) and its raw text is logged.
  Its reply never reaches the loop; it shows what the model writes for that
  request when the server's call parser is out of the way (a fresh sample);
* after each turn the thread's events are read back, so a turn that ended on a
  clarifying question is not counted as blank (EXP-2026-11-016 Amendment 1);
* the model record (relay listing, self-report, server fingerprint) at the
  start and end, in ``env/model_record.jsonl``.
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
EXPS = HERE.parent
G016 = EXPS / "EXP-2026-11-016-agent-gate-replication" / "code"
R1 = EXPS / "EXP-2026-11-011-mylo-agent-baseline" / "code"
sys.path[:0] = [str(G016), str(R1)]
import run_v2  # noqa: E402  (inserts R1 and web/backend on sys.path)

sys.path.insert(0, str(G016))
import probes as P  # noqa: E402
import run_gate  # noqa: E402  (flow_narrow, recreate_db)
import world_seeded  # noqa: E402

v1 = run_v2.v1
LOCK = threading.Lock()
LOCAL = threading.local()


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def model_record(label: str) -> dict:
    """EXP-2026-11-021's preflight: the relay's list, the self-report, the server."""
    import httpx

    base = os.environ["LLM_BASE_URL"]
    key = os.environ.get("LLM_API_KEY", "")
    model = os.environ.get("LLM_MODEL", "default-model")
    head = {"Authorization": f"Bearer {key}"} if key else {}
    rec = {"label": label, "at": now(), "relay_model": model}
    try:
        r = httpx.get(f"{base.rstrip('/')}/models", headers=head, timeout=30)
        rec["relay_listing"] = [{"id": m.get("id"), "relay": m.get("relay"),
                                 "max_model_len": m.get("max_model_len"), "root": m.get("root"),
                                 "owned_by": m.get("owned_by")}
                                for m in r.json().get("data", [])]
    except Exception as exc:  # noqa: BLE001
        rec["relay_listing"] = f"error: {type(exc).__name__}: {exc}"[:300]
    try:
        r = httpx.post(f"{base.rstrip('/')}/chat/completions", headers=head, timeout=300, json={
            "model": model, "max_tokens": 4000,
            "messages": [{"role": "user", "content":
                          "Which model are you, and who trained you? Answer in one sentence."}]})
        body = r.json()
        msg = (body.get("choices") or [{}])[0].get("message") or {}
        rec["self_report"] = {"content": msg.get("content"),
                              "reasoning": (msg.get("reasoning") or msg.get("reasoning_content") or "")[:600],
                              "server": body.get("system_fingerprint"), "model": body.get("model"),
                              "status": r.status_code, "error": body.get("error")}
    except Exception as exc:  # noqa: BLE001
        rec["self_report"] = f"error: {type(exc).__name__}: {exc}"[:300]
    return rec


class RawLog:
    """Forwards to the real port; writes every reply, and probes empty ones."""

    def __init__(self, inner, path: Path, model: str, probe: bool):
        self.inner, self.path, self.model, self.probe = inner, path, model, probe
        self.client = None

    def _diagnose(self, messages, tools):
        import httpx
        from apps.core.llm import build_llm_client

        if self.client is None:
            self.client = build_llm_client(component="agent")
        payload = self.client._payload(messages, model=self.model, reasoning=None,
                                       temperature=None, max_tokens=0, tools=tools or None,
                                       tool_choice="none" if tools else None,
                                       extra_body={"skip_special_tokens": False})
        body = {k: v for k, v in payload.items() if k != "extra_body"}
        body.update(payload.get("extra_body") or {})
        key = os.environ.get("LLM_API_KEY", "")
        head = {"Authorization": f"Bearer {key}"} if key else {}
        try:
            r = httpx.post(f"{os.environ['LLM_BASE_URL'].rstrip('/')}/chat/completions",
                           headers=head, json=body, timeout=600)
            data = r.json()
            ch = (data.get("choices") or [{}])[0]
            msg = ch.get("message") or {}
            return {"status": r.status_code, "content": msg.get("content"),
                    "reasoning": msg.get("reasoning") or msg.get("reasoning_content"),
                    "tool_calls": msg.get("tool_calls"), "finish": ch.get("finish_reason"),
                    "usage": data.get("usage"), "server": data.get("system_fingerprint"),
                    "sent": {k: v for k, v in body.items() if k not in ("messages", "tools")},
                    "error": data.get("error")}
        except Exception as exc:  # noqa: BLE001
            return {"error": f"{type(exc).__name__}: {exc}"[:300]}

    def __call__(self, *, messages, tools, tool_choice, on_delta, should_stop):
        t0 = time.monotonic()
        reply = self.inner(messages=messages, tools=tools, tool_choice=tool_choice,
                           on_delta=on_delta, should_stop=should_stop)
        content = getattr(reply, "content", None) or ""
        calls = [getattr(c, "name", None) for c in (getattr(reply, "tool_calls", None) or [])]
        empty = not content.strip() and not calls and getattr(reply, "finish_reason", None) != "cancelled"
        offered = [((t.get("function") or {}).get("name") or t.get("name")) for t in (tools or [])]
        last = messages[-1] if messages else {}
        row = {"at": now(), "task": getattr(LOCAL, "task", None), "rep": getattr(LOCAL, "rep", None),
               "n_messages": len(messages), "last_role": last.get("role"),
               "last_name": last.get("name"),
               "after_tool": last.get("role") == "tool",
               "tool_choice": tool_choice, "offered": offered,
               "finish": getattr(reply, "finish_reason", None),
               "usage": dict(getattr(reply, "usage", None) or {}),
               "content": content[:2000], "reasoning": (getattr(reply, "reasoning", None) or "")[:600],
               "calls": calls, "empty": empty, "seconds": round(time.monotonic() - t0, 2)}
        if empty and self.probe:
            row["diagnostic"] = self._diagnose(messages, tools)
        with LOCK, self.path.open("a") as fh:
            fh.write(json.dumps(row, default=str) + "\n")
        return reply


def thread_trace(thread_id) -> dict:
    """The stored turn, read back: steps, the clarifying question, the final text."""
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute("SELECT seq, type, payload FROM agent_agentevent WHERE thread_id=%s ORDER BY seq",
                    [str(thread_id)])
        rows = cur.fetchall()
    steps, questions, finals, verdicts = [], [], [], []
    for seq, typ, p in rows:
        p = p if isinstance(p, dict) else json.loads(p or "{}")
        if typ == "usage":
            steps.append({"seq": seq, "completion": (p.get("usage") or {}).get("completion_tokens")})
        elif typ == "assistant":
            steps.append({"seq": seq, "text": (p.get("text") or "")[:300], "final": bool(p.get("final")),
                          "repairs": p.get("repairs"),
                          "calls": [c.get("name") for c in p.get("tool_calls") or []]})
            if p.get("final"):
                finals.append(p.get("text") or "")
        elif typ == "question":
            questions.append(str(p.get("question") or ""))
        elif typ == "verdict":
            verdicts.append(p.get("action"))
    return {"steps": steps, "question_text": "\n".join(q for q in questions if q),
            "final_text": finals[-1] if finals else "", "verdicts": verdicts}


def latest_thread_id():
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute("SELECT id FROM agent_agentthread ORDER BY created_at DESC LIMIT 1")
        row = cur.fetchone()
    return row[0] if row else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True, help="which frozen code: f1115, f1117, ...")
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--arm", choices=["gate", "prompt_only"], required=True)
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--conc", type=int, default=3)
    ap.add_argument("--no-probe", action="store_true")
    ap.add_argument("--no-stream", action="store_true",
                    help="Phase 3: the agent's calls go out unstreamed (complete, not complete_stream)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    assert re.fullmatch(r"[a-z0-9]+", args.label)

    spec = world_seeded.spec(args.seed)
    tasks = P.probes(spec)  # asserts no secret in any question
    db = f"mycelium_agent_eval_x022_{args.label}_{args.seed}_{args.arm}"
    assert db.startswith("mycelium_agent_eval_x022_")
    url = run_gate.recreate_db(db)
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
    model = llmcall.model_name()
    if args.arm == "prompt_only":
        run_v2.bypass_gate()
    stem = f"{args.label}_s{args.seed}_{args.arm}{'_dry' if args.dry_run else ''}"
    logs = HERE / "logs"
    logs.mkdir(exist_ok=True)
    env_rec = HERE / "env" / "model_record.jsonl"
    if not args.dry_run:
        with env_rec.open("a") as fh:
            fh.write(json.dumps({**model_record(f"start {stem}"), "db": db}) + "\n")
    if args.no_stream:
        # Phase 3 (PROTOCOL, amendment of 17:35 UTC): the same request, not
        # streamed. Patched in this process only; the frozen code is unchanged.
        from apps.core.llm import LLMClient

        def unstreamed(self, messages, *, on_delta=None, should_stop=None, **kw):
            return self.complete(messages, **kw)

        LLMClient.complete_stream = unstreamed
    inner = v1.Dry() if args.dry_run else llmcall.default_port()
    base = RawLog(inner, logs / f"calls_{stem}.jsonl", model, probe=not (args.dry_run or args.no_probe))
    if not args.dry_run:
        LOCAL.task, LOCAL.rep = "warmup", -1
        base(messages=[{"role": "user", "content": "Reply with: ok"}], tools=None,
             tool_choice=None, on_delta=None, should_stop=None)

    log_path = logs / f"runs_{stem}.jsonl"
    from django.db import connection

    def one(job):
        task, rep = job
        LOCAL.task, LOCAL.rep = task["id"], rep
        trace = {}
        try:
            out = run_gate.flow_narrow(task, w, base) if task.get("flow") == "narrow" else \
                run_v2.run_plain(task, w, base)
            passed, checks, points = run_v2.grade_v2(task, out, w)
            tid = out.get("thread") or (latest_thread_id() if task.get("flow") else None)
            if tid:
                trace = thread_trace(tid)
                trace["thread"] = str(tid)
        except Exception as exc:  # noqa: BLE001
            out, passed, checks, points = ({"error": f"{type(exc).__name__}: {exc}"[:400]},
                                           False, {"error": True}, {})
        finally:
            connection.close()
        refused = bool(out.get("refused_at_open") or out.get("refused_at_send"))
        seen = "\n".join(x for x in [out.get("text") or "", trace.get("question_text") or ""] if x.strip())
        blank = not refused and not out.get("error") and not seen.strip()
        row = {"label": args.label, "task": task["id"], "category": task["category"],
               "seed": args.seed, "arm": args.arm, "model_name": model, "rep": rep,
               "passed": passed, "leaks": points, "blank": blank, "refused": refused,
               "error": out.get("error"), "ended_on_question": bool(trace.get("question_text")),
               "tokens": out.get("tokens", 0), "seconds": out.get("seconds"),
               "steps": out.get("steps"), "calls": out.get("calls"), "question": task["text"],
               "text": (out.get("text") or "")[:1500], "trace": trace, "at": now()}
        with LOCK, log_path.open("a") as fh:
            fh.write(json.dumps(row, default=str) + "\n")
        print(task["id"], rep, "BLANK" if blank else "ok", flush=True)

    plain = [t for t in tasks if not t.get("flow")]
    flows = [t for t in tasks if t.get("flow")]
    for rep in range(args.reps):
        with ThreadPoolExecutor(max_workers=args.conc) as pool:
            list(pool.map(one, [(t, rep) for t in plain]))
        for t in flows:  # changes a shared row: one at a time
            one((t, rep))
    if not args.dry_run:
        with env_rec.open("a") as fh:
            fh.write(json.dumps({**model_record(f"end {stem}"), "db": db}) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
