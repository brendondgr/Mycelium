"""Round three (Q-070, Q-088): what a Mylo turn ended on, and what the model
returned on every empty call. Shared by this folder's ``run019_r3.py`` and
EXP-2026-11-016's ``run_gate_r3.py``. Harness only; product code is unchanged.

``Recorder`` wraps the model port (outside round one's ``CapturePort``) and keeps,
per model call of the current worker thread: seconds, finish reason, content and
reasoning length, the function calls the server parsed, the usage block, and
whether the reasoning text carries function-call markup the server did not turn
into a call. A call is *empty* when it returned no text and no function call
(the condition ``llmcall.call`` retries on, and the loop's own empty retry).

``outcome`` puts the turn in exactly one class: ``answered`` (final text that is
not a give-up line), ``question`` (no final text; a clarifying question shown),
``fallback`` (the loop's give-up line), ``failed`` (no text; the turn stored a
``turn_failed`` error, so the person saw the error), ``blank`` (none of these).
"""

from __future__ import annotations

import json
import re
import threading
import time

TL = threading.local()
CALL_MARKUP = re.compile(r"<tool_call>|<function=|\"name\"\s*:\s*\"[a-z_]+\"\s*,\s*\"arguments\"|"
                         r"\b(?:knowledge|projects|feeds|org|me|corpus|files|load)_[a-z_]+\s*\(")


def begin():
    TL.calls = []


def calls():
    return list(getattr(TL, "calls", []))


class Recorder:
    def __init__(self, inner):
        self.inner = inner

    def __call__(self, *, messages, tools, tool_choice, on_delta, should_stop):
        t0 = time.monotonic()
        rec = {"tool_choice": tool_choice, "n_tools": len(tools or [])}
        try:
            reply = self.inner(messages=messages, tools=tools, tool_choice=tool_choice,
                               on_delta=on_delta, should_stop=should_stop)
        except Exception as exc:  # noqa: BLE001
            rec.update(seconds=round(time.monotonic() - t0, 2),
                       exception=f"{type(exc).__name__}: {exc}"[:300])
            getattr(TL, "calls", []).append(rec)
            raise
        content = reply.content or ""
        reasoning = reply.reasoning or ""
        usage = dict(reply.usage or {})
        details = usage.get("completion_tokens_details") or {}
        rec.update(
            seconds=round(time.monotonic() - t0, 2),
            finish_reason=reply.finish_reason,
            content_chars=len(content.strip()),
            reasoning_chars=len(reasoning.strip()),
            tool_calls=[tc.name for tc in reply.tool_calls],
            tool_args_json_ok=[_json_ok(tc.arguments) for tc in reply.tool_calls],
            completion_tokens=usage.get("completion_tokens"),
            reasoning_tokens=details.get("reasoning_tokens") if isinstance(details, dict) else None,
            prompt_tokens=usage.get("prompt_tokens"),
            empty=not content.strip() and not reply.tool_calls,
            markup_in_reasoning=bool(CALL_MARKUP.search(reasoning)),
            markup_in_content=bool(CALL_MARKUP.search(content)),
            reasoning_tail=reasoning[-400:] if not content.strip() and not reply.tool_calls else "",
        )
        getattr(TL, "calls", []).append(rec)
        return reply


def _json_ok(text):
    try:
        json.loads(text or "{}")
        return True
    except ValueError:
        return False


def thread_facts(thread) -> dict:
    from tools.agent import store

    events = store.events(thread)
    questions = [str(e.payload.get("question") or "") for e in events if e.type == "question"]
    recall = [str(e.payload.get("text") or "") for e in events if e.type == "recall"]
    verdicts = [e.payload.get("action") for e in events if e.type == "verdict"]
    return {"questions": questions,
            "recall_nonempty": any(r.strip() for r in recall),
            "recall_facts": sum(int(e.payload.get("facts") or 0) for e in events if e.type == "recall"),
            "loop_empty_retry": verdicts.count("empty_retry"),
            "length_retry": verdicts.count("length_retry"),
            "runaway_retry": verdicts.count("runaway_retry"),
            "failed_inside": [e.payload.get("name") for e in events if e.type == "tool_result"
                              and (e.payload.get("error") or {}).get("code") == "failed"]}


def outcome(final_text: str, questions: list[str], errors=()) -> str:
    from tools.agent.loop import EMPTY_GIVE_UP, RUNAWAY_GIVE_UP

    t = (final_text or "").strip()
    if t in (EMPTY_GIVE_UP.strip(), RUNAWAY_GIVE_UP.strip()):
        return "fallback"
    if t:
        return "answered"
    if any(q.strip() for q in questions):
        return "question"
    if any((e.get("code") if isinstance(e, dict) else e) == "turn_failed" for e in errors or ()):
        return "failed"
    return "blank"


def summary(call_rows: list[dict]) -> dict:
    empties = [c for c in call_rows if c.get("empty")]
    return {"model_calls": len(call_rows), "empty_calls": len(empties),
            "empty_call_detail": empties,
            "call_exceptions": [c["exception"] for c in call_rows if c.get("exception")],
            "model_seconds": round(sum(c.get("seconds") or 0 for c in call_rows), 2)}
