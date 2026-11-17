"""How a turn ends when the model gives nothing or too much (Q-070, Q-078).

* An empty reply, after the model call's own retry, gets one more chance with
  functions off; if that is empty too the person reads an honest line, never
  a blank.
* A reply cut off at the output cap is thrown away and asked for again,
  shorter; a second cut-off posts an honest line.
"""

from __future__ import annotations

import pytest
from apps.core.llm import LLMResponse

from tools.agent import loop, service, store
from tools.agent.caller import for_thread

from .conftest import make_user, thread_for


def _send(thread, text):
    return service.send(for_thread(thread), thread, text, start=lambda t: None)


def _events(thread, kind):
    return [e.payload for e in store.events(thread) if e.type == kind]


def _final(thread):
    finals = [p for p in _events(thread, "assistant") if p.get("final")]
    return finals[-1]["text"] if finals else None


def _cut(text):
    return LLMResponse(content=text, finish_reason="length", usage={"total_tokens": 9})


def test_an_empty_reply_gets_one_more_chance_without_functions(scripted, db):
    thread = thread_for(make_user("ada"))
    _send(thread, "what is new?")
    model = scripted("", "", "Nothing new in your feeds this week.")
    loop.run_turn(thread.pk, port=model)
    assert _final(thread) == "Nothing new in your feeds this week."
    assert _events(thread, "verdict")[0]["action"] == "empty_retry"
    # The third request carried the nudge; it ends the turn without functions.
    asked_again = model.requests[2]
    assert asked_again["tool_choice"] in ("none", None)
    sent = [str(m.get("content")) for m in asked_again["messages"]]
    assert any(loop.EMPTY_RETRY in text for text in sent)


def _lost_call():
    """What the server returns when it could not read the model's call."""
    usage = {"total_tokens": 9}
    return LLMResponse(content="", finish_reason="tool_calls", usage=usage)


def test_a_lost_function_call_is_asked_for_again_with_functions_on(scripted, db):
    # EXP-2026-11-019 Amendment 7: the server said the model stopped to call a
    # function and returned no call; the no-functions retry could not help.
    thread = thread_for(make_user("ada"))
    _send(thread, "who am I?")
    model = scripted(_lost_call(), _lost_call(), [("me_profile", {})], "You are Ada.")
    loop.run_turn(thread.pk, port=model)
    assert _final(thread) == "You are Ada."
    assert _events(thread, "verdict")[0]["action"] == "lost_call_retry"
    again = model.requests[2]
    assert again["tool_choice"] == "auto" and again["tools"]
    sent = [str(m.get("content")) for m in again["messages"]]
    assert any(loop.LOST_CALL_RETRY in text for text in sent)
    results = _events(thread, "tool_result")
    assert [r["status"] for r in results] == ["ok"]


def test_a_call_lost_twice_falls_back_to_the_empty_reply_path(scripted, db):
    thread = thread_for(make_user("ada"))
    _send(thread, "who am I?")
    model = scripted(
        _lost_call(), _lost_call(), _lost_call(), _lost_call(), "I could not look."
    )
    loop.run_turn(thread.pk, port=model)
    actions = [v["action"] for v in _events(thread, "verdict")]
    assert actions[:2] == ["lost_call_retry", "empty_retry"]
    assert _final(thread) == "I could not look."
    assert model.requests[-1]["tool_choice"] in ("none", None)


def test_a_second_empty_reply_posts_an_honest_line(scripted, db):
    thread = thread_for(make_user("ada"))
    _send(thread, "what is new?")
    loop.run_turn(thread.pk, port=scripted("", "", "", ""))
    assert _final(thread) == loop.EMPTY_GIVE_UP
    verdict = _events(thread, "verdict")[-1]
    assert verdict["action"] == "empty_gave_up" and verdict["ok"] is False


def test_a_cut_off_answer_is_asked_again_shorter(scripted, db):
    thread = thread_for(make_user("ada"))
    _send(thread, "tell me everything")
    model = scripted(_cut("A very long answer that never"), "The short version.")
    loop.run_turn(thread.pk, port=model)
    assert _final(thread) == "The short version."
    assert all("never" not in p.get("text", "") for p in _events(thread, "assistant"))
    assert _events(thread, "verdict")[0]["action"] == "length_retry"
    assert any(n.get("text") == loop.LENGTH_RETRY for n in _events(thread, "note"))


def test_a_second_cut_off_posts_an_honest_line(scripted, db):
    thread = thread_for(make_user("ada"))
    _send(thread, "tell me everything")
    loop.run_turn(thread.pk, port=scripted(_cut("Long"), _cut("Still long")))
    assert _final(thread) == loop.RUNAWAY_GIVE_UP


def test_a_turn_the_queue_refuses_does_not_leave_the_thread_running(
    db, monkeypatch
) -> None:
    """The broker being unreachable used to strand the thread as ``running``, so
    every later message sat "waiting for my turn" behind a turn nobody ran."""
    from tools.agent import tasks
    from tools.agent.models import AgentQueuedMessage, AgentThread

    def refuse(*args, **kwargs):
        raise RuntimeError("broker unreachable")

    monkeypatch.setattr(tasks.run_turn, "delay", refuse)
    thread = thread_for(make_user("ada"))

    with pytest.raises(RuntimeError):
        service.start_turn(thread)

    thread.refresh_from_db()
    assert thread.state == AgentThread.State.ERROR
    # So the next message starts a turn of its own instead of queueing.
    monkeypatch.setattr(tasks.run_turn, "delay", lambda *a, **k: None)
    out = service.send(for_thread(thread), thread, "are you there?")
    assert out["status"] != "queued"
    assert not AgentQueuedMessage.objects.filter(thread=thread).exists()
