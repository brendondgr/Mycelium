"""One real Mylo turn in the demo world, instrumented from the outside.

Shared by EXP-2026-11-010 (A2) and copied into the human-judged answers
experiment. Nothing here changes production behaviour: the agent runs through
``tools.agent.service.create_thread`` / ``send`` and ``tools.agent.loop.run_turn``
— the function the Celery task calls — with a port that wraps the instance's
own ``default_port`` to timestamp each model call and its first streamed delta.

Threads are created as demo threads (``demo_visitor`` set), so they are budgeted
like the public demo, never feed the learning pass, and are removed by the
demo's own 24-hour cleanup.
"""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
sys.path[:0] = [str(REPO / "web" / "backend"), str(REPO)]
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


def setup():
    import django

    django.setup()


class TimedPort:
    """Wraps a model port; records per-call timings and enforces a turn deadline."""

    def __init__(self, inner, deadline_s: float):
        self.inner = inner
        self.deadline_s = deadline_s
        self.t0 = None
        self.calls: list[dict] = []
        self.first_delta: float | None = None
        self.timed_out = False

    def start(self):
        self.t0 = time.monotonic()

    def __call__(self, *, messages, tools, tool_choice, on_delta, should_stop):
        started = time.monotonic()
        first = []

        def delta(kind, text):
            now = time.monotonic()
            if not first:
                first.append(now)
            if self.first_delta is None:
                self.first_delta = now
            if on_delta:
                on_delta(kind, text)

        def stop():
            if time.monotonic() - self.t0 > self.deadline_s:
                self.timed_out = True
                return True
            return bool(should_stop and should_stop())

        reply = self.inner(messages=messages, tools=tools, tool_choice=tool_choice,
                           on_delta=delta, should_stop=stop)
        ended = time.monotonic()
        usage = dict(reply.usage or {})
        self.calls.append({
            "start_s": round(started - self.t0, 3),
            "latency_s": round(ended - started, 3),
            "first_delta_s": round(first[0] - started, 3) if first else None,
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "function_calls": len(getattr(reply, "tool_calls", None) or getattr(reply, "calls", None) or []),
            "tool_choice": tool_choice,
            "n_tools": len(tools or []),
        })
        return reply


def demo_context():
    from django.contrib.auth import get_user_model

    from apps.accounts.models import Lab
    from apps.demo.models import DemoWorld
    from apps.research.models import Project

    world = DemoWorld.objects.select_related("viewer", "lab").get(key="default")
    pi = world.viewer
    lab = world.lab
    projects = {p.name: p for p in Project.objects.filter(scope_lab=lab)}
    return {"pi": pi, "lab": lab, "projects": projects,
            "User": get_user_model(), "Lab": Lab}


def run_question(ctx, q: dict, *, visitor: str, deadline_s: float = 900.0,
                 port=None) -> dict:
    """Ask one question as the demo PI; return timings, counts and content."""
    from tools.agent import loop, rebuild, refs, service, store, verify
    from tools.agent.caller import Audience, Caller, Scope
    from tools.agent.llmcall import default_port

    pi, lab = ctx["pi"], ctx["lab"]
    kind = q.get("scope", "lab")
    obj = lab if kind == "lab" else ctx["projects"].get(q.get("project", "")) if kind == "project" else None
    scope = Scope(kind, obj) if obj is not None else Scope("personal")
    thread = service.create_thread(pi, scope=scope, surface="web", demo_visitor=visitor)
    caller = Caller(user=pi, surface="web", scope=scope, audience=Audience("person"),
                    thread_id=thread.pk)
    timed = TimedPort(port or default_port(), deadline_s)
    service.send(caller, thread, q["text"], mentions=q.get("mentions", []),
                 start=lambda t: None)
    timed.start()
    wall0 = time.monotonic()
    loop.run_turn(thread.pk, port=timed, caller=caller)
    wall = time.monotonic() - wall0
    thread.refresh_from_db()
    events = store.events(thread)
    t_user = next((e.ts for e in events if e.type == "user"), None)
    first_call = next((e.ts for e in events if e.type == "tool_call"), None)
    finals = [e for e in events if e.type == "assistant" and e.payload.get("final")]
    drafts = [e for e in events if e.type == "assistant" and not e.payload.get("final")
              and not e.payload.get("partial")]
    verdicts = [e.payload for e in events if e.type == "verdict"]
    notes = [e.payload.get("text", "") for e in events if e.type == "note"]
    final = finals[-1].payload if finals else {}
    results = rebuild.visible_results(thread, events, caller)
    try:
        from tools.agent.loop import _grounding_extra

        extra = list(_grounding_extra(caller, thread, events))
    except Exception:  # noqa: BLE001
        extra = []
    first_activity = None
    candidates = []
    if timed.first_delta is not None:
        candidates.append(timed.first_delta - timed.t0)
    if first_call is not None and t_user is not None:
        # event timestamps are wall-clock; turn start ≈ the user event
        candidates.append((first_call - t_user).total_seconds())
    if candidates:
        first_activity = round(min(candidates), 3)
    text = final.get("text", "")
    stops = " ".join(n for n in notes)
    return {
        "id": q["id"],
        "group": q.get("group"),
        "thread": str(thread.pk),
        "wall_s": round(wall, 3),
        "first_activity_s": first_activity,
        "model_calls": len(timed.calls),
        "function_calls": sum(1 for e in events if e.type == "tool_call"),
        "functions": [e.payload.get("name") for e in events if e.type == "tool_call"],
        "denied": sum(1 for e in events if e.type == "tool_result"
                      and e.payload.get("status") == "denied"),
        "prompt_tokens": sum(c["prompt_tokens"] or 0 for c in timed.calls),
        "completion_tokens": sum(c["completion_tokens"] or 0 for c in timed.calls),
        "hit_max_steps": "used all" in stops,
        "thrash_stop": "last calls all failed" in stops,
        "timed_out": timed.timed_out,
        "repair": any(v.get("action") == "repair" for v in verdicts),
        "verdicts": verdicts,
        "final_text": text,
        "removed": final.get("removed", []),
        "removed_claims": final.get("removed_claims", []),
        "drafts": [d.payload.get("text", "") for d in drafts if d.payload.get("text")],
        "errors": [e.payload for e in events if e.type == "error"],
        "refs": refs.thread_refs(thread),
        "cited": sorted({int(n) for n in re.findall(r"#(\d+)", text)}),
        "results": [{"name": p.get("name"), "status": p.get("status"),
                     "refs": p.get("refs"), "content": p.get("content")} for p in results],
        "extra": extra,
        "source_seen": sorted(verify.seen_refs(results, extra)),
        "calls": timed.calls,
        "state": thread.state,
    }
