"""The turn (GAIFA §3), with its guards (§8).

    resolve pending calls → step cap → compact → thrash guard → call the model
    → no calls: citation check, done → calls: run them, repeat

Everything needed to resume lives in the log: a pause (``ask_user``) ends the
turn ``waiting``; the answer is appended and a new turn picks up from there. A
turn left ``running`` by a crash is restarted by the resume sweep, which runs
the calls that have no result yet and carries on.
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor

from apps.core.llm import is_context_length_error
from django.db import close_old_connections

from . import (
    compaction,
    config,
    dispatch,
    permissions,
    prompt,
    rebuild,
    skills,
    store,
    stream,
    verify,
)
from .caller import Caller
from .llmcall import NoModel, call, default_port, model_info
from .models import AgentQueuedMessage, AgentThread

logger = logging.getLogger(__name__)

#: Functions the loop handles itself rather than through a handler.
ASK_USER = "ask_user"
#: Refuse the Nth identical call in one turn.
REPEAT_LIMIT = 3
#: Wrap up after this many steps in a row whose calls all failed.
THRASH_STEPS = 3


def _visible_functions(caller: Caller, thread: AgentThread):
    """(loaded, deferred, unavailable): what the model may call now, what it
    could load, and plain reasons for what this person cannot use here."""
    loaded_names = set((thread.settings or {}).get("loaded", []))
    loaded, deferred, unavailable = [], [], []
    for fn, decision in permissions.catalog(caller, mode=thread.mode):
        if not decision.allowed:
            if decision.layer in (2, 3, 4, 7) and decision.detail not in unavailable:
                unavailable.append(decision.detail.rstrip("."))
            continue
        core = fn.core or (fn.group == "projects" and caller.scope.kind == "project")
        if core or fn.name in loaded_names:
            loaded.append(fn)
        else:
            deferred.append(fn)
    return loaded, deferred, unavailable[:6]


def _cancel_pending(thread: AgentThread) -> None:
    for event in store.pending_calls(thread):
        if event.payload.get("name") == ASK_USER:
            continue
        store.append(
            thread,
            "tool_result",
            {
                "call_id": event.payload["call_id"],
                "name": event.payload.get("name"),
                "status": "cancelled",
                "error": {
                    "code": "cancelled",
                    "detail": "The person stopped this turn.",
                },
            },
        )


def _run_calls(caller, thread, calls: list[dict]) -> list[dict]:
    def one(c):
        try:
            return dispatch.run(
                caller,
                thread,
                name=c["name"],
                args=c.get("args"),
                call_id=c["call_id"],
                arg_error=c.get("error", ""),
                mode=thread.mode,
            )
        finally:
            if parallel:
                close_old_connections()

    parallel = bool(config.get("parallel_calls")) and len(calls) > 1
    if parallel:
        with ThreadPoolExecutor(max_workers=min(4, len(calls))) as pool:
            return list(pool.map(one, calls))
    return [one(c) for c in calls]


def _resolve_pending(caller, thread) -> bool:
    """Run calls that have no result (after a crash). False when the thread
    is waiting on ask_user."""
    pending = store.pending_calls(thread)
    if any(e.payload.get("name") == ASK_USER for e in pending):
        return False
    todo = [dict(e.payload) for e in pending]
    for result in _run_calls(caller, thread, todo):
        store.append(thread, "tool_result", result)
    return True


def _drain_queue(thread: AgentThread) -> bool:
    """A person's own thread: everything sent during the turn is answered
    together, in the same turn."""
    rows = list(
        AgentQueuedMessage.objects.filter(thread=thread).order_by("created_at", "id")
    )
    if not rows:
        return False
    from . import service

    for row in rows:
        service.record_user_message(
            thread, row.text, mentions=row.mentions or [], caller=None
        )
        row.delete()
    return True


def next_shared_message(thread: AgentThread) -> bool:
    """A shared thread: the oldest queued question becomes the next turn, under
    its own asker. Never merged with the others (plan D)."""
    from . import service

    row = (
        AgentQueuedMessage.objects.filter(thread=thread)
        .order_by("created_at", "id")
        .first()
    )
    if row is None:
        return False
    service.record_user_message(
        thread,
        row.text,
        mentions=row.mentions or [],
        cards=[],
        speaker=row.speaker or None,
        turn=row.turn or None,
        queued_id=row.pk,
    )
    row.delete()
    return True


def run_turn(thread_id, *, port=None, caller: Caller | None = None) -> str:
    """Run turns until the thread is settled. A shared thread answers its
    queued questions one turn each, each under its own asker."""
    while True:
        state = _run_one(thread_id, port=port, caller=caller)
        caller = None  # the next turn's caller comes from its own question
        thread = AgentThread.objects.get(pk=thread_id)
        if (
            state != AgentThread.State.IDLE
            or not thread.shared
            or not next_shared_message(thread)
        ):
            return state


def _run_one(thread_id, *, port=None, caller: Caller | None = None) -> str:
    """Run one turn to its end. Returns the thread's final state."""
    thread = AgentThread.objects.select_related(
        "user", "scope_lab", "scope_department", "scope_project"
    ).get(pk=thread_id)
    if caller is None:
        from .caller import for_turn

        caller = for_turn(thread)
    gate = permissions.may_chat(caller)
    if not gate.allowed:
        store.append(
            thread, "error", {"code": gate.code, "detail": gate.detail, "fix": gate.fix}
        )
        store.set_state(thread, AgentThread.State.IDLE)
        return thread.state
    try:
        port = port or default_port()
    except NoModel:
        store.append(
            thread,
            "error",
            {
                "code": "no_model",
                "detail": "No language model is configured on this instance.",
                "fix": (
                    "The operator sets LLM_MODEL (or tools.agent.model) and restarts."
                ),
            },
        )
        store.set_state(thread, AgentThread.State.IDLE)
        return thread.state
    store.set_state(thread, AgentThread.State.RUNNING)
    try:
        state = _turn(caller, thread, port)
    except Exception as exc:
        logger.exception("agent turn failed for thread %s", thread.pk)
        store.append(
            thread,
            "error",
            {
                "code": "turn_failed",
                "detail": str(exc)[:300],
                "fix": "Send the message again.",
            },
        )
        state = AgentThread.State.ERROR
    stream.clear_cancel(thread.pk)
    thread.refresh_from_db(fields=["state"])
    store.set_state(thread, state)
    if state == AgentThread.State.IDLE:
        _after_turn(caller, thread, port)
    return state


def _after_turn(caller, thread, port) -> None:
    from . import memory_after

    try:
        memory_after.after_turn(caller, thread, port)
    except Exception:  # titles and notices are never worth failing a turn
        logger.exception("agent after-turn work failed for %s", thread.pk)


def _turn(caller: Caller, thread: AgentThread, port) -> str:
    from . import recall

    #: Which model answered, on every assistant event (S3).
    info = model_info()
    model = {"model": info} if info else {}
    max_steps = int(config.get("max_steps"))
    window = compaction.window()
    steps = 0
    seen: dict[str, int] = {}
    failed_steps = 0
    overflowed = False
    repaired = False
    force_final = ""
    while True:
        if stream.cancel_requested(thread.pk):
            _cancel_pending(thread)
            store.append(thread, "note", {"text": "Stopped."})
            return AgentThread.State.IDLE
        if not _resolve_pending(caller, thread):
            return AgentThread.State.WAITING
        recall.ensure(caller, thread)
        if steps >= max_steps and not force_final:
            force_final = (
                f"You have used all {max_steps} steps for this turn. Answer now with "
                "what you have, and say what you could not finish."
            )
        if failed_steps >= THRASH_STEPS and not force_final:
            force_final = (
                "Your last calls all failed or were refused. Stop calling functions "
                "and answer with what you know, saying what did not work."
            )
        if force_final:
            store.append(thread, "note", {"text": force_final, "to_model": True})

        loaded, deferred, unavailable = _visible_functions(caller, thread)
        events = store.events(thread)
        msgs = rebuild.messages(thread, events)
        system = prompt.build(
            caller,
            thread,
            deferred=deferred,
            skill_list=skills.available(),
            unavailable=unavailable,
            summary=compaction.latest_summary(events),
        )
        tools = [fn.schema() for fn in loaded]
        size = rebuild.estimate_tokens(system, msgs, tools)
        if size > window * compaction.CLEAR_AT:
            if compaction.clear_old_results(thread, events):
                msgs = rebuild.messages(thread, events)
                size = rebuild.estimate_tokens(system, msgs, tools)
        if size > window * compaction.SUMMARIZE_AT:
            if compaction.summarize(thread, events, port, rebuild.messages):
                events = store.events(thread)
                msgs = rebuild.messages(thread, events)
                system = prompt.build(
                    caller,
                    thread,
                    deferred=deferred,
                    skill_list=skills.available(),
                    unavailable=unavailable,
                    summary=compaction.latest_summary(events),
                )
                size = rebuild.estimate_tokens(system, msgs, tools)
        if size > window:
            store.append(
                thread,
                "error",
                {
                    "code": "context_full",
                    "detail": "This conversation no longer fits in Mylo's memory.",
                    "fix": (
                        "Start a new thread, or fork this one from an earlier message."
                    ),
                },
            )
            return AgentThread.State.IDLE
        stream.publish_transient(thread, "meter", used=size, window=window)

        try:
            reply = call(
                port,
                messages=[{"role": "system", "content": system}, *msgs],
                tools=tools,
                tool_choice="none" if force_final else ("auto" if tools else None),
                known={fn.name for fn in loaded},
                on_delta=lambda kind, text: stream.publish_transient(
                    thread, "delta", kind=kind, text=text
                ),
                should_stop=lambda: stream.cancel_requested(thread.pk),
            )
        except Exception as exc:
            # The server says the prompt overflowed although the estimate
            # fit: compact once and try again (P4).
            if overflowed or not is_context_length_error(exc):
                raise
            overflowed = True
            if compaction.clear_old_results(thread, events) or compaction.summarize(
                thread, events, port, rebuild.messages
            ):
                continue
            raise
        steps += 1
        if reply.usage:
            store.append(
                thread,
                "usage",
                {"usage": reply.usage, "step": steps},
                tokens=int(reply.usage.get("total_tokens") or 0),
            )
        if reply.thinking or reply.opaque:
            store.append(
                thread,
                "thinking",
                {"text": reply.thinking,
                 **({"opaque": reply.opaque} if reply.opaque else {})},
            )
        if reply.finish == "cancelled":
            if reply.text:
                store.append(
                    thread, "assistant", {"text": reply.text, "partial": True, **model}
                )
            store.append(thread, "note", {"text": "Stopped."})
            return AgentThread.State.IDLE

        calls = []
        for c in reply.calls:
            shape = (
                json.dumps(c.args, sort_keys=True)
                if c.args is not None
                else c.arguments
            )
            key = f"{c.name}:{shape}"
            seen[key] = seen.get(key, 0) + 1
            calls.append(
                {
                    "call_id": c.id,
                    "name": c.name,
                    "args": c.args,
                    "arguments": c.arguments,
                    "error": c.error,
                    "repeat": seen[key],
                }
            )

        if not calls:
            missing = verify.unmatched(thread, reply.text)
            if missing and not repaired:
                ev = store.append(
                    thread,
                    "assistant",
                    {"text": reply.text, "repairs": reply.repairs, **model},
                )
                store.append(
                    thread,
                    "verdict",
                    {
                        "seq": ev.seq,
                        "ok": False,
                        "unmatched": missing,
                        "action": "repair",
                    },
                )
                store.append(
                    thread,
                    "note",
                    {"text": verify.repair_message(missing), "to_model": True},
                )
                repaired = True
                force_final = force_final or "Answer now."
                continue
            text = verify.strip(reply.text, missing) if missing else reply.text
            ev = store.append(
                thread,
                "assistant",
                {
                    "text": text,
                    "repairs": reply.repairs,
                    "final": True,
                    **({"removed": missing} if missing else {}),
                    **model,
                },
            )
            store.append(
                thread,
                "verdict",
                {
                    "seq": ev.seq,
                    "ok": not missing,
                    "unmatched": missing,
                    "action": "stripped" if missing else "none",
                },
            )
            if missing:
                store.append(
                    thread,
                    "note",
                    {
                        "text": "Some citations could not be matched to anything "
                        "Mylo read "
                        "and were removed: " + ", ".join(f"#{n}" for n in missing)
                    },
                )
            if not thread.shared and _drain_queue(thread):
                steps, failed_steps, repaired, force_final, seen = 0, 0, False, "", {}
                continue
            return AgentThread.State.IDLE

        store.append(
            thread,
            "assistant",
            {
                "text": reply.text,
                "repairs": reply.repairs,
                "tool_calls": [
                    {"id": c["call_id"], "name": c["name"], "arguments": c["arguments"]}
                    for c in calls
                ],
                **model,
            },
        )
        for c in calls:
            store.append(
                thread,
                "tool_call",
                {k: c[k] for k in ("call_id", "name", "args", "arguments")},
            )
        asked = [c for c in calls if c["name"] == ASK_USER]
        runnable = []
        results = []
        for c in calls:
            if c["name"] == ASK_USER:
                continue
            if c["repeat"] >= REPEAT_LIMIT:
                results.append(
                    {
                        "call_id": c["call_id"],
                        "name": c["name"],
                        "status": "error",
                        "error": {
                            "code": "repeated_call",
                            "detail": "You already made this exact call twice "
                            "this turn.",
                            "fix": "Use the result you have, or change the call.",
                        },
                    }
                )
            else:
                runnable.append(c)
        results += _run_calls(caller, thread, runnable)
        for result in results:
            stream.publish_transient(
                thread, "progress", name=result.get("name"), status=result.get("status")
            )
            store.append(thread, "tool_result", result)
        if results and all(r.get("status") != "ok" for r in results):
            failed_steps += 1
        else:
            failed_steps = 0
        if asked:
            c = asked[0]
            args = c.get("args") or {}
            store.append(
                thread,
                "question",
                {
                    "call_id": c["call_id"],
                    "question": args.get("question", ""),
                    "options": args.get("options", []),
                },
            )
            for extra in asked[1:]:
                store.append(
                    thread,
                    "tool_result",
                    {
                        "call_id": extra["call_id"],
                        "name": ASK_USER,
                        "status": "error",
                        "error": {
                            "code": "one_question",
                            "detail": "Ask one question at a time.",
                        },
                    },
                )
            return AgentThread.State.WAITING
