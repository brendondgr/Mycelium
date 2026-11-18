"""The turn (GAIFA §3), with its guards (§8).

    resolve pending calls → step cap → compact → thrash guard → call the model
    → no calls: runaway retry, citation and grounding checks, done
    → calls: run them, repeat

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
#: Refuse a function after it failed in this many steps of one turn, whatever
#: the arguments (EXP-2026-11-013: one answer called an introduction-path
#: lookup eight times on people it cannot reach). Counted per step, not per
#: call: a model that sends twenty calls at once with the same slip made one
#: mistake, and its corrected batch must still run.
FAILURE_LIMIT = 2
#: A call rejected because its arguments were malformed (a name the function
#: does not take, a required one left out, a value in the wrong form) is the
#: model's slip, not the function failing: it does not count toward
#: FAILURE_LIMIT, so the corrected call still runs (Q-075: two malformed calls
#: used up the limit and the correct third was refused). Malformed calls have
#: this ceiling of their own, per function and turn, so a model cannot loop on
#: them for ever.
MALFORMED_LIMIT = 4
#: Told to the model when its answer got stuck repeating itself.
RUNAWAY_RETRY = (
    "Your last answer got stuck repeating the same words, so it was thrown "
    "away and nobody saw it. Answer again, briefly. If you need details about "
    "an item, read it first. Never repeat a line."
)
#: Posted instead of a fragment when the retry loops too.
RUNAWAY_GIVE_UP = (
    "I got stuck writing that answer, so I've left it out rather than post "
    "something broken. Ask me again, or ask about one item at a time."
)
#: Told to the model when its reply came back empty twice (the model call's
#: own retry included): one more chance, with no functions (Q-070, Q-088).
EMPTY_RETRY = (
    "Your last reply was empty, so the person saw nothing. Answer now in a "
    "few sentences with what you found. If you found nothing useful, say so "
    "plainly and say what they could ask instead."
)
#: Told to the model when its reply was empty although the server says it
#: stopped to call a function: the call was lost on the way (the server could
#: not read it), so nothing ran. It is asked for again with functions still
#: on — answering "with what you found" is no use to a model that was about to
#: look something up (EXP-2026-11-019 Amendment 7: every empty call of Gemma
#: 4 31B was of this kind, and the no-functions retry then lost its call too).
LOST_CALL_RETRY = (
    "Your last step was a function call that could not be read, so nothing "
    "ran. Send it again: one function at a time, its arguments as one JSON "
    "object."
)
#: Posted when that chance is empty too, so the person never sees a blank.
EMPTY_GIVE_UP = (
    "I couldn't put together an answer to that. Try asking again, or ask in a "
    "narrower way, for example about one project or one item."
)
#: Told to the model when its answer hit the output cap mid-sentence (Q-078).
LENGTH_RETRY = (
    "Your last answer ran past the length limit and was cut off, so it was "
    "thrown away and nobody saw it. Answer again, much shorter: the main "
    "points only."
)
#: Told to the model when its reply hit the output cap before it had called
#: any function in the turn. Functions stay on: "answer again, shorter" with
#: functions off left a model that had only been reasoning aloud with nothing
#: to answer from, and the turn ended on the give-up line (Q-096).
LENGTH_RETRY_UNREAD = (
    "Your last reply ran past the length limit before you had looked anything "
    "up, so it was thrown away and nobody saw it. Do not write your reasoning "
    "out. If you need to look something up, call the function now; if you do "
    "not, answer in a few sentences."
)
#: Told to the model when what one turn read no longer fits the window and
#: the oldest results were put away so the turn can still end with an answer.
FIT_FINAL = (
    "What you have read in this turn no longer fits in your memory, so the "
    "oldest results were put away. Stop calling functions and answer now from "
    "what you can still see. Say plainly that the answer covers only part of "
    "what was asked, and say what you could not check."
)
#: What a call past the step's limit is told.
TOO_MANY_CALLS_FIX = (
    "Send it in your next step if you still need it. To check every item of a "
    "list against one condition, pass the condition to the list function "
    "instead of reading the items one by one."
)
#: Shown to the person when unbacked details were taken out of an answer.
CLAIMS_REMOVED = (
    "Mylo removed details from this answer that it could not find in what it "
    "read."
)


def common_clip(text: str, n: int = 240) -> str:
    """One line of at most ``n`` characters, for an error a model reads."""
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _grounding_extra(caller, thread, events) -> list[str]:
    """Cards in view besides lookups: what was tagged, and the anchor."""
    from . import refs

    extra = [
        card
        for e in events
        if e.type == "user"
        for card in (e.payload.get("cards") or [])
    ]
    anchored = refs.resolve_anchor(caller, thread)
    if anchored is not None:
        extra.append(refs.card(*anchored))
    return extra


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
    failures: dict[str, list[str]] = {}
    malformed: dict[str, int] = {}
    failed_steps = 0
    overflowed = False
    repaired = False
    runaway_retried = False
    empty_retried = False
    lost_call_retried = False
    fitted = False
    force_final = ""
    step_calls = int(config.get("step_calls") or 0)
    while True:
        if stream.cancel_requested(thread.pk):
            _cancel_pending(thread)
            store.append(thread, "note", {"text": "Stopped."})
            return AgentThread.State.IDLE
        if not _resolve_pending(caller, thread):
            return AgentThread.State.WAITING
        # What the last step's calls wrote (functions loaded, references
        # numbered) is read from the row, not from this turn's first copy: a
        # function the model was told is "available from your next step" was
        # otherwise not offered until the turn after.
        thread.refresh_from_db(fields=["settings"])
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
        msgs = rebuild.messages(thread, events, caller=caller)
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
                msgs = rebuild.messages(thread, events, caller=caller)
                size = rebuild.estimate_tokens(system, msgs, tools)
        if size > window * compaction.SUMMARIZE_AT:
            if compaction.summarize(thread, events, port, rebuild.messages):
                events = store.events(thread)
                msgs = rebuild.messages(thread, events, caller=caller)
                system = prompt.build(
                    caller,
                    thread,
                    deferred=deferred,
                    skill_list=skills.available(),
                    unavailable=unavailable,
                    summary=compaction.latest_summary(events),
                )
                size = rebuild.estimate_tokens(system, msgs, tools)
        if size > window and not fitted:
            # One question read more than the window holds. Rather than end
            # with an error, put the oldest results away and answer from what
            # is left, saying so (Q-091).
            fitted = True
            over = size - int(window * compaction.CLEAR_AT)
            if compaction.clear_to_fit(thread, events, over):
                store.append(thread, "verdict", {"ok": False, "action": "fit_final"})
                force_final = FIT_FINAL
                continue
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
                    "key": key,
                    "call_id": c.id,
                    "name": c.name,
                    "args": c.args,
                    "arguments": c.arguments,
                    "error": c.error,
                    "repeat": seen[key],
                }
            )

        if not calls:
            gave_up = False
            # Cut off at the output cap: treated like a runaway (Q-078).
            cut_off = reply.finish == "length"
            # Nothing has been called yet in this turn: there is nothing to
            # answer from, so the retry keeps functions on (Q-096).
            unread = cut_off and not seen and not force_final
            if "runaway_cut" in (reply.repairs or []) or cut_off:
                if not runaway_retried:
                    # The looped text is never posted, and never replayed.
                    runaway_retried = True
                    store.append(
                        thread,
                        "verdict",
                        {
                            "ok": False,
                            "action": "length_retry" if cut_off else "runaway_retry",
                            "cut": (reply.text or "")[-300:],
                        },
                    )
                    store.append(
                        thread,
                        "note",
                        {
                            "text": LENGTH_RETRY_UNREAD
                            if unread
                            else LENGTH_RETRY
                            if cut_off
                            else RUNAWAY_RETRY,
                            "to_model": True,
                        },
                    )
                    if cut_off and not unread:
                        force_final = force_final or "Answer now."
                    continue
                gave_up = True
            empty = not gave_up and not (reply.text or "").strip()
            if (
                empty
                and reply.finish == "tool_calls"
                and not force_final
                and not lost_call_retried
            ):
                # A call was made and lost: ask for it again, functions on.
                lost_call_retried = True
                store.append(
                    thread, "verdict", {"ok": False, "action": "lost_call_retry"}
                )
                store.append(
                    thread, "note", {"text": LOST_CALL_RETRY, "to_model": True}
                )
                continue
            if empty and not empty_retried:
                # Never post a blank: one more try, without functions (Q-070).
                empty_retried = True
                store.append(
                    thread, "verdict", {"ok": False, "action": "empty_retry"}
                )
                store.append(thread, "note", {"text": EMPTY_RETRY, "to_model": True})
                force_final = force_final or "Answer now."
                continue
            text = (
                EMPTY_GIVE_UP if empty else RUNAWAY_GIVE_UP if gave_up else reply.text
            )
            gave_up = gave_up or empty
            missing, unread_refs, claims, numbered = [], [], [], []
            if not gave_up:
                results = rebuild.visible_results(thread, events, caller)
                extra = _grounding_extra(caller, thread, events)
                in_view = verify.seen_refs(results, extra)
                # A person or project named without its number gets it.
                text, numbered = verify.number_names(thread, text, in_view)
                missing = verify.unmatched(thread, text)
                unread_refs = [
                    n for n in verify.unread(thread, text, in_view) if n not in missing
                ]
                claims = verify.unsupported(text, verify.source_text(results, extra))
            if (missing or unread_refs or claims) and not repaired:
                ev = store.append(
                    thread,
                    "assistant",
                    {"text": text, "repairs": reply.repairs, **model},
                )
                store.append(
                    thread,
                    "verdict",
                    {
                        "seq": ev.seq,
                        "ok": False,
                        "unmatched": missing,
                        "unread": unread_refs,
                        "unsupported": claims,
                        "action": "repair",
                    },
                )
                parts = [verify.repair_message(missing)] if missing else []
                if unread_refs or claims:
                    parts.append(verify.grounding_message(unread_refs, claims))
                store.append(
                    thread, "note", {"text": "\n\n".join(parts), "to_model": True}
                )
                repaired = True
                if not (unread_refs or claims):
                    # Only a citation to fix: no reading needed.
                    force_final = force_final or "Answer now."
                continue
            if missing:
                text = verify.strip(text, missing)
            if claims:
                text = verify.strip_claims(text, claims)
            ev = store.append(
                thread,
                "assistant",
                {
                    "text": text,
                    "repairs": reply.repairs,
                    "final": True,
                    **({"removed": missing} if missing else {}),
                    **({"removed_claims": claims} if claims else {}),
                    **({"numbered": numbered} if numbered else {}),
                    **model,
                },
            )
            store.append(
                thread,
                "verdict",
                {
                    "seq": ev.seq,
                    "ok": not (missing or claims or gave_up),
                    "unmatched": missing,
                    "unread": unread_refs,
                    "unsupported": claims,
                    "action": (
                        "empty_gave_up"
                        if empty
                        else "runaway_gave_up"
                        if gave_up
                        else "stripped"
                        if (missing or claims)
                        else "none"
                    ),
                },
            )
            if claims:
                store.append(thread, "note", {"text": CLAIMS_REMOVED})
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
                failures, malformed = {}, {}
                lost_call_retried = fitted = False
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
            if len(failures.get(c["name"], [])) >= FAILURE_LIMIT:
                said = "; ".join(dict.fromkeys(failures[c["name"]]))
                results.append(
                    {
                        "call_id": c["call_id"],
                        "name": c["name"],
                        "status": "error",
                        "error": {
                            "code": "keeps_failing",
                            "detail": f"{c['name']} has failed {FAILURE_LIMIT} times "
                            f"this turn ({common_clip(said)}), so it is not run again.",
                            "fix": "It does not cover this. Use another function, "
                            "or answer with what you have and say what you could "
                            "not find.",
                        },
                    }
                )
            elif malformed.get(c["name"], 0) >= MALFORMED_LIMIT:
                results.append(
                    {
                        "call_id": c["call_id"],
                        "name": c["name"],
                        "status": "error",
                        "error": {
                            "code": "keeps_malformed",
                            "detail": f"{c['name']} was called {MALFORMED_LIMIT} "
                            "times this turn with arguments it does not take, so "
                            "it is not run again.",
                            "fix": (
                                f"{dispatch.accepts_by_name(c['name'])} Use another "
                                "function, or answer with what you have and say "
                                "what you could not find."
                            ).strip(),
                        },
                    }
                )
            elif c["repeat"] >= REPEAT_LIMIT:
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
            elif step_calls and len(runnable) >= step_calls:
                # Not run and not held against it: the same call may come
                # again in a later step.
                seen[c["key"]] -= 1
                results.append(
                    {
                        "call_id": c["call_id"],
                        "name": c["name"],
                        "status": "error",
                        "error": {
                            "code": "too_many_calls",
                            "detail": f"Only {step_calls} function calls run in "
                            f"one step and this step made {len(calls)}, so this "
                            "one was not run.",
                            "fix": TOO_MANY_CALLS_FIX,
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
        counted: set[tuple[str, str]] = set()
        for result in results:
            error = result.get("error") or {}
            refused_here = error.get("code") in (
                "repeated_call",
                "keeps_failing",
                "keeps_malformed",
                "too_many_calls",
            )
            if result.get("status") not in ("error", "denied") or refused_here:
                continue
            name = result.get("name") or ""
            kind = "malformed" if dispatch.malformed(result) else "failed"
            if (kind, name) in counted:
                continue  # the same slip, sent several times at once
            counted.add((kind, name))
            if kind == "malformed":
                malformed[name] = malformed.get(name, 0) + 1
            else:
                failures.setdefault(name, []).append(
                    str(error.get("detail") or error.get("code") or "error")
                )
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
