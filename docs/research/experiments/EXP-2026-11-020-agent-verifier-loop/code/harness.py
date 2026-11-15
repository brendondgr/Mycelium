"""EXP-2026-11-020: shared harness — scripted model replies and replayed
function results inside a real Mylo turn.

Nothing in product code changes. Two hooks live only in this process:

- ``ScriptedPort`` answers the loop's first model calls from a script (a list
  of replies, or a function of the thread) and forwards every later call to
  the instance model through a timing wrapper.
- ``install_replay`` wraps ``tools.agent.dispatch.run`` so that a call whose id
  starts with ``replay-`` returns a stored function result (content and
  reference numbers) instead of running; every other call runs normally.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
R1 = HERE.parents[1] / "EXP-2026-11-013-agent-answers-human-judged" / "code"
sys.path.insert(0, str(R1))
import mylo_turn  # noqa: E402

VISITOR = "EXP-2026-11-020"
_replay: dict[str, list[dict]] = {}
_lock = threading.Lock()


def setup():
    mylo_turn.setup()
    install_replay()


def response(text="", calls=()):
    from apps.core.llm import LLMResponse, ToolCall

    return LLMResponse(
        content=text,
        finish_reason="tool_calls" if calls else "stop",
        usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        tool_calls=tuple(ToolCall(id=c["id"], name=c["name"], arguments=json.dumps(c.get("args") or {}))
                         for c in calls),
    )


class ScriptedPort:
    """``script`` items are LLMResponse objects or callables returning one
    (called with no arguments, so they can read the thread at that moment).
    After the script, calls go to ``inner`` (the instance model), timed."""

    def __init__(self, script, inner=None):
        self.script = list(script)
        self.inner = inner
        self.scripted = 0
        self.real: list[dict] = []

    def __call__(self, *, messages, tools, tool_choice, on_delta, should_stop):
        if self.script:
            item = self.script.pop(0)
            self.scripted += 1
            return item() if callable(item) else item
        if self.inner is None:
            raise RuntimeError("script exhausted and no model allowed")
        t0 = time.monotonic()
        reply = self.inner(messages=messages, tools=tools, tool_choice=tool_choice,
                           on_delta=on_delta, should_stop=should_stop)
        usage = dict(reply.usage or {})
        self.real.append({"latency_s": round(time.monotonic() - t0, 3),
                          "prompt_tokens": usage.get("prompt_tokens"),
                          "completion_tokens": usage.get("completion_tokens"),
                          "tool_calls": len(reply.tool_calls or ()), "tool_choice": tool_choice})
        return reply


def install_replay():
    from tools.agent import dispatch

    if getattr(dispatch.run, "_exp020", False):
        return
    real = dispatch.run

    def run(caller, thread, *, name, args, call_id, arg_error="", mode="read"):
        if str(call_id).startswith("replay-"):
            with _lock:
                stored = _replay[str(thread.pk)][int(str(call_id).split("-", 1)[1])]
            numbers = list(stored.get("refs") or [])
            return {"call_id": call_id, "name": name, "status": "ok",
                    "content": stored.get("content") or "", "refs": numbers,
                    "untrusted": True, "source": ",".join(f"#{n}" for n in numbers[:5]) or name,
                    "chars": len(stored.get("content") or "")}
        return real(caller, thread, name=name, args=args, call_id=call_id,
                    arg_error=arg_error, mode=mode)

    run._exp020 = True
    dispatch.run = run


def set_replay(thread_pk, results: list[dict]):
    with _lock:
        _replay[str(thread_pk)] = results


def new_thread(ctx, q: dict):
    """A demo thread as the demo PI, in the question's scope."""
    from tools.agent import service
    from tools.agent.caller import Audience, Caller, Scope

    pi, lab = ctx["pi"], ctx["lab"]
    kind = q.get("scope", "lab")
    obj = lab if kind == "lab" else ctx["projects"].get(q.get("project", "")) if kind == "project" else None
    scope = Scope(kind, obj) if obj is not None else Scope("personal")
    thread = service.create_thread(pi, scope=scope, surface="web", demo_visitor=VISITOR)
    caller = Caller(user=pi, surface="web", scope=scope, audience=Audience("person"), thread_id=thread.pk)
    return thread, caller


def ask(caller, thread, text, mentions=()):
    from tools.agent import service

    service.send(caller, thread, text, mentions=list(mentions), start=lambda t: None)


def outcome(thread, since_seq: int = 0) -> dict:
    from tools.agent import refs, store

    thread.refresh_from_db()
    events = [e for e in store.events(thread) if e.seq > since_seq]
    finals = [e.payload for e in events if e.type == "assistant" and e.payload.get("final")]
    final = finals[-1] if finals else {}
    return {
        "verdicts": [e.payload for e in events if e.type == "verdict"],
        "final_text": final.get("text", ""),
        "removed": final.get("removed", []),
        "removed_claims": final.get("removed_claims", []),
        "notes": [e.payload.get("text", "") for e in events if e.type == "note" and not e.payload.get("to_model")],
        "functions": [e.payload.get("name") for e in events if e.type == "tool_call"
                      and not str(e.payload.get("call_id", "")).startswith("replay-")],
        "errors": [e.payload for e in events if e.type == "error"],
        "refs": refs.thread_refs(thread),
        "last_seq": max((e.seq for e in store.events(thread)), default=0),
        "state": thread.state,
    }
