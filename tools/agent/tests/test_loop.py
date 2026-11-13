"""Phase 1: the store, rebuild and the turn loop with a scripted model."""

from __future__ import annotations

import pytest

from tools.agent import loop, rebuild, service, store, stream
from tools.agent.caller import for_thread
from tools.agent.models import AgentEvent, AgentThread

from .conftest import make_user, thread_for

pytestmark = pytest.mark.django_db


def _send(thread, text, **kw):
    caller = for_thread(thread)
    return service.send(caller, thread, text, start=lambda t: None, **kw)


def _types(thread):
    return [e.type for e in store.events(thread)]


def _final(thread):
    finals = [
        e
        for e in store.events(thread)
        if e.type == "assistant" and e.payload.get("final")
    ]
    return finals[-1].payload["text"] if finals else None


@pytest.fixture
def person():
    return make_user("ada")


def test_a_plain_answer_ends_the_turn_idle(person, scripted):
    thread = thread_for(person)
    _send(thread, "hello")
    model = scripted("Hi Ada.", '{"title": "Greeting", "purpose": "saying hello"}')
    assert loop.run_turn(thread.pk, port=model) == "idle"
    assert _final(thread) == "Hi Ada."
    thread.refresh_from_db()
    assert thread.title == "Greeting" and thread.purpose == "saying hello"
    # seq is dense and starts at 1
    seqs = [e.seq for e in store.events(thread)]
    assert seqs == list(range(1, len(seqs) + 1))


def test_a_call_runs_and_its_result_is_rebuilt(person, scripted):
    thread = thread_for(person)
    _send(thread, "who am I?")
    model = scripted([("me_profile", {})], "You are Ada.")
    loop.run_turn(thread.pk, port=model)
    result = next(e for e in store.events(thread) if e.type == "tool_result")
    assert result.payload["status"] == "ok"
    assert "@ada" in result.payload["content"]
    second = model.requests[1]["messages"]
    assert second[-1]["role"] == "tool" and "@ada" in second[-1]["content"]
    assert second[-2]["role"] == "assistant" and second[-2]["tool_calls"]


def test_rebuild_is_byte_identical(person, scripted):
    thread = thread_for(person)
    _send(thread, "who am I?")
    loop.run_turn(thread.pk, port=scripted([("me_profile", {})], "You are Ada."))
    events = store.events(thread)
    assert rebuild.messages(thread, events) == rebuild.messages(
        thread, store.events(thread)
    )


def test_step_cap_forces_a_final_answer(person, scripted, settings):
    settings.AGENT_MAX_STEPS = 2
    thread = thread_for(person)
    _send(thread, "loop")
    model = scripted([("me_profile", {})], [("me_interests", {})], "Done anyway.")
    loop.run_turn(thread.pk, port=model)
    assert model.requests[2]["tool_choice"] == "none"
    assert _final(thread) == "Done anyway."


def test_third_identical_call_is_refused(person, scripted):
    thread = thread_for(person)
    _send(thread, "again")
    model = scripted(
        [("me_profile", {})], [("me_profile", {})], [("me_profile", {})], "ok"
    )
    loop.run_turn(thread.pk, port=model)
    results = [e.payload for e in store.events(thread) if e.type == "tool_result"]
    assert [r["status"] for r in results] == ["ok", "ok", "error"]
    assert results[-1]["error"]["code"] == "repeated_call"


def test_a_function_that_keeps_failing_is_not_run_again(person, scripted):
    # EXP-2026-11-013: the same lookup failed eight times with new arguments.
    thread = thread_for(person)
    _send(thread, "who can introduce me?")
    model = scripted(
        [("no_such_fn", {"who": "a"})],
        [("no_such_fn", {"who": "b"})],
        [("no_such_fn", {"who": "c"})],
        "I could not find a path.",
    )
    loop.run_turn(thread.pk, port=model)
    results = [e.payload for e in store.events(thread) if e.type == "tool_result"]
    assert [r["error"]["code"] for r in results][-1] == "keeps_failing"
    assert "not run again" in results[-1]["error"]["detail"]


def test_thrashing_wraps_up(person, scripted):
    thread = thread_for(person)
    _send(thread, "break")
    bad = [("no_such_fn", {})]
    model = scripted(
        bad, [("no_such_fn", {"a": 1})], [("no_such_fn", {"a": 2})], "Sorry."
    )
    loop.run_turn(thread.pk, port=model)
    assert model.requests[3]["tool_choice"] == "none"
    assert _final(thread) == "Sorry."


def test_ask_user_pauses_and_the_answer_resumes(person, scripted):
    thread = thread_for(person)
    _send(thread, "help me pick")
    model = scripted([("ask_user", {"question": "Which one?", "options": ["A", "B"]})])
    assert loop.run_turn(thread.pk, port=model) == "waiting"
    question = AgentEvent.objects.get(thread=thread, type="question")
    assert question.payload["options"] == ["A", "B"]
    with pytest.raises(service.ServiceError):
        _send(thread, "something else")  # answer first
    service.answer(for_thread(thread), thread, "B", start=lambda t: None)
    model2 = scripted("You chose B.")
    assert loop.run_turn(thread.pk, port=model2) == "idle"
    msgs = model2.requests[0]["messages"]
    assert any(m["role"] == "tool" and "B" in m["content"] for m in msgs)


def test_resume_after_a_crash_runs_the_unfinished_call(person, scripted):
    thread = thread_for(person)
    _send(thread, "who am I")
    # a crash after the call was recorded but before it ran
    store.append(
        thread,
        "assistant",
        {
            "text": "",
            "tool_calls": [{"id": "c9", "name": "me_profile", "arguments": "{}"}],
        },
    )
    store.append(
        thread,
        "tool_call",
        {"call_id": "c9", "name": "me_profile", "args": {}, "arguments": "{}"},
    )
    AgentThread.objects.filter(pk=thread.pk).update(state="running")
    model = scripted("You are Ada.")
    loop.run_turn(thread.pk, port=model)
    result = AgentEvent.objects.get(thread=thread, type="tool_result")
    assert result.payload["call_id"] == "c9" and result.payload["status"] == "ok"
    assert _final(thread) == "You are Ada."


def test_cancel_stops_before_the_next_step(person, scripted):
    thread = thread_for(person)
    _send(thread, "go")

    class CancelAfterFirst:
        def __init__(self):
            self.inner = scripted([("me_profile", {})], "never")

        def __call__(self, **kw):
            out = self.inner(**kw)
            stream.request_cancel(thread.pk)
            return out

    model = CancelAfterFirst()
    assert loop.run_turn(thread.pk, port=model) == "idle"
    turn_calls = [r for r in model.inner.requests if r["tools"]]
    assert len(turn_calls) == 1
    assert any(
        e.type == "note" and e.payload.get("text") == "Stopped."
        for e in store.events(thread)
    )
    results = [e for e in store.events(thread) if e.type == "tool_result"]
    assert len(results) == 1  # the call already made ran; nothing after it


def test_unmatched_citations_get_one_repair_then_are_stripped(person, scripted):
    thread = thread_for(person)
    _send(thread, "cite")
    model = scripted("See #7.", "Still #7 and #8.")
    loop.run_turn(thread.pk, port=model)
    verdicts = [e.payload for e in store.events(thread) if e.type == "verdict"]
    assert [v["action"] for v in verdicts] == ["repair", "stripped"]
    assert "#7" not in _final(thread) and "#8" not in _final(thread)
    repair_note = model.requests[1]["messages"][-2]["content"]
    assert "#7" in repair_note


def test_messages_sent_during_a_turn_are_answered_after_it(person, scripted):
    thread = thread_for(person)
    _send(thread, "first")
    AgentThread.objects.filter(pk=thread.pk).update(state="running")
    thread.refresh_from_db()
    assert _send(thread, "second")["status"] == "queued"
    model = scripted("One.", "Two.")
    loop.run_turn(thread.pk, port=model)
    finals = [
        e.payload["text"]
        for e in store.events(thread)
        if e.type == "assistant" and e.payload.get("final")
    ]
    assert finals == ["One.", "Two."]
    users = [e.payload["text"] for e in store.events(thread) if e.type == "user"]
    assert users == ["first", "second"]


def test_steer_writes_into_the_running_turn(person):
    thread = thread_for(person)
    AgentThread.objects.filter(pk=thread.pk).update(state="running")
    thread.refresh_from_db()
    out = _send(thread, "also this", steer=True)
    assert out["status"] == "steered"
    assert _types(thread)[-1] == "user"


def test_no_model_is_reported_not_raised(person, settings):
    settings.LLM_MODEL = ""
    settings.AGENT_MODEL = ""
    thread = thread_for(person)
    _send(thread, "hi")
    assert loop.run_turn(thread.pk) == "idle"
    error = AgentEvent.objects.get(thread=thread, type="error")
    assert error.payload["code"] == "no_model" and error.payload["fix"]
    assert service.status()["code"] == "no_model"


def test_fork_drops_an_unresolved_trailing_step(person, scripted):
    thread = thread_for(person)
    _send(thread, "hi")
    loop.run_turn(thread.pk, port=scripted("Hello."))
    store.append(
        thread,
        "assistant",
        {
            "text": "",
            "tool_calls": [{"id": "x", "name": "me_profile", "arguments": "{}"}],
        },
    )
    store.append(
        thread, "tool_call", {"call_id": "x", "name": "me_profile", "args": {}}
    )
    child = service.fork_thread(person, thread.pk, store.last_seq(thread))
    child_types = [e.type for e in store.events(child)]
    assert "tool_call" not in child_types
    assert child.parent_id == thread.pk


def test_deltas_are_published_but_never_stored(person, scripted):
    thread = thread_for(person)
    sub = stream.bus().subscribe([stream.thread_channel(thread.pk)])
    _send(thread, "hi")
    loop.run_turn(thread.pk, port=scripted("Hello there."))
    seen = []
    while (msg := sub.get(0.01)) is not None:
        seen.append(msg)
    assert any(m["type"] == "delta" and m["text"] == "Hello there." for m in seen)
    assert not AgentEvent.objects.filter(thread=thread, type="delta").exists()


def test_learning_notice_is_given_once(person, scripted):
    thread = thread_for(person)
    _send(thread, "hi")
    loop.run_turn(thread.pk, port=scripted("Hello."))
    _send(thread, "again")
    loop.run_turn(thread.pk, port=scripted("Hello again."))
    notices = [
        e for e in store.events(thread) if e.payload.get("kind") == "learning_notice"
    ]
    assert len(notices) == 1
