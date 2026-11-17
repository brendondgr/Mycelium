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


def _results(thread):
    return [e.payload for e in store.events(thread) if e.type == "tool_result"]


def _paper(title="A paper to read"):
    from tools.retrieval.read import ContentItem

    return ContentItem.objects.create(
        type="paper",
        source="test",
        external_id=title[:20],
        metadata={"title": title, "abstract": "An abstract."},
    )


def test_two_malformed_calls_do_not_block_the_correct_one(person, scripted):
    # Q-075: a wrong argument name, then none, used up the failure limit and
    # the corrected call was refused.
    paper = _paper()
    thread = thread_for(person)
    _send(thread, "what is this paper?")
    model = scripted(
        [("corpus_item", {"paper": f"item:{paper.pk}"})],
        [("corpus_item", {})],
        [("corpus_item", {"item": f"item:{paper.pk}"})],
        "It is a paper.",
    )
    loop.run_turn(thread.pk, port=model)
    results = _results(thread)
    assert [r["status"] for r in results] == ["error", "error", "ok"]
    assert [r["error"]["code"] for r in results[:2]] == ["bad_arguments"] * 2
    # The error names what the function does and does not take.
    assert "does not take: paper" in results[0]["error"]["detail"]
    assert "needs: item" in results[1]["error"]["detail"]
    assert results[0]["error"]["fix"] == "corpus_item accepts: item (required)."
    assert "A paper to read" in results[2]["content"]


def test_a_real_failure_still_counts_toward_the_limit(person, scripted):
    thread = thread_for(person)
    _send(thread, "read these")
    gone = "item:00000000-0000-0000-0000-00000000000"
    model = scripted(
        [("corpus_item", {"item": gone + "1"})],
        [("corpus_item", {"item": gone + "2"})],
        [("corpus_item", {"item": gone + "3"})],
        "I could not read them.",
    )
    loop.run_turn(thread.pk, port=model)
    results = _results(thread)
    assert [r["status"] for r in results[:2]] == ["denied", "denied"]
    assert results[2]["error"]["code"] == "keeps_failing"


def test_one_slip_sent_many_times_at_once_counts_once(person, scripted):
    # Go-live check, 2026-11-17: 24 calls in one step with the same wrong
    # reference used up the limit twelve times over, and the corrected batch
    # was refused.
    papers = [_paper(f"Paper number {n}") for n in range(3)]
    thread = thread_for(person)
    _send(thread, "read these three")
    gone = "item:00000000-0000-0000-0000-00000000000"
    model = scripted(
        [("corpus_item", {"item": gone + str(n)}) for n in range(3)],
        [("corpus_item", {"item": f"item:{p.pk}"}) for p in papers],
        "They are papers.",
    )
    loop.run_turn(thread.pk, port=model)
    results = _results(thread)
    assert [r["status"] for r in results] == ["denied"] * 3 + ["ok"] * 3


def test_a_reference_with_its_title_after_it_is_that_reference(person):
    from tools.agent import dispatch, refs
    from tools.agent.caller import for_thread

    one, two = _paper("First paper"), _paper("Second paper")
    thread = thread_for(person)
    caller = for_thread(thread)
    for paper in (one, two):
        dispatch.run(
            caller, thread, name="corpus_item", args={"item": f"item:{paper.pk}"},
            call_id="c",
        )
    def key(token):
        return refs.resolve(caller, token, expect_kind="item").key

    assert key("#1 First paper") == str(one.pk)
    assert key("#2: Second paper") == str(two.pk)
    assert key("[#2]") == str(two.pk)
    # Two numbers name nothing: a title never picks between objects.
    assert refs.resolve(caller, "#1 and #2", expect_kind="item") is None
    assert refs.resolve(caller, "#9 No such reference", expect_kind="item") is None
    out = dispatch.run(
        caller, thread, name="corpus_item", args={"item": "#1 First paper"}, call_id="d"
    )
    assert out["status"] == "ok" and "First paper" in out["content"]


def test_malformed_calls_have_a_ceiling_of_their_own(person, scripted):
    thread = thread_for(person)
    _send(thread, "keep trying")
    good = [("me_profile", {}), ("me_interests", {}), ("me_understanding", {})]
    steps = [
        [("corpus_item", {"guess": n}), good[n % 3]]
        for n in range(loop.MALFORMED_LIMIT)
    ]
    model = scripted(*steps, [("corpus_item", {"guess": 99})], "I give up.")
    loop.run_turn(thread.pk, port=model)
    mine = [r for r in _results(thread) if r["name"] == "corpus_item"]
    assert [r["error"]["code"] for r in mine] == [
        *["bad_arguments"] * loop.MALFORMED_LIMIT,
        "keeps_malformed",
    ]
    assert "not run again" in mine[-1]["error"]["detail"]
    assert "corpus_item accepts: item (required)." in mine[-1]["error"]["fix"]


def test_a_handler_asking_for_a_missing_argument_is_malformed_too(person):
    from tools.agent import dispatch
    from tools.agent.caller import for_thread

    thread = thread_for(person)
    thread.settings = {**(thread.settings or {}), "loaded": ["projects_get"]}
    thread.save(update_fields=["settings"])
    out = dispatch.run(
        for_thread(thread), thread, name="projects_get", args={}, call_id="c1"
    )
    assert out["error"]["code"] == "need_project" and dispatch.malformed(out)
    assert out["error"]["fix"].endswith("projects_get accepts: project.")
    denied = dispatch.run(
        for_thread(thread), thread, name="no_such_fn", args={}, call_id="c2"
    )
    assert not dispatch.malformed(denied)


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


def _statuses(thread):
    return [
        (e.payload["status"], (e.payload.get("error") or {}).get("code"))
        for e in store.events(thread)
        if e.type == "tool_result"
    ]


def test_a_step_runs_only_so_many_calls_and_the_rest_may_come_again(
    person, scripted, settings
):
    # Q-091: a model sent 24 calls in one step, and nothing limited them.
    settings.AGENT_STEP_CALLS = 2
    thread = thread_for(person)
    _send(thread, "what can you do?")
    asks = [("find_functions", {"query": q}) for q in ("feed", "lab", "paper", "grant")]
    model = scripted(asks, asks[2:], asks[2:], "That is what I can do.")
    loop.run_turn(thread.pk, port=model)
    late = ("error", "too_many_calls")
    assert _statuses(thread)[:4] == [late, late, ("ok", None), ("ok", None)]
    # A call that was not run is not held against the model: sent again it
    # runs, and it does not count as a repeat or as the function failing.
    assert _statuses(thread)[4:] == [("ok", None)] * 4
    refused = next(
        e.payload["error"]
        for e in store.events(thread)
        if e.type == "tool_result" and e.payload["status"] == "error"
    )
    assert "Only 2 function calls run in one step" in refused["detail"]
    assert _final(thread) == "That is what I can do."


def test_a_turn_that_read_more_than_fits_answers_from_what_is_left(
    person, scripted, settings
):
    # Q-091: results that overflowed the window ended the turn with an error
    # ("context_full") and no answer.
    settings.AGENT_CONTEXT_WINDOW = 6000
    thread = thread_for(person)
    _send(thread, "read everything in the feed")
    for i in range(3):
        store.append(
            thread,
            "assistant",
            {
                "text": "",
                "tool_calls": [{"id": f"r{i}", "name": "me_profile", "arguments": "{}"}],
            },
        )
        store.append(
            thread,
            "tool_result",
            {
                "call_id": f"r{i}",
                "name": "me_profile",
                "status": "ok",
                "content": "data " * 2400,
            },
        )
    model = scripted("Here is the part I could read.")
    assert loop.run_turn(thread.pk, port=model) == "idle"
    assert _final(thread) == "Here is the part I could read."
    assert "error" not in _types(thread)
    verdicts = [e.payload["action"] for e in store.events(thread) if e.type == "verdict"]
    assert verdicts[0] == "fit_final"
    asked = model.requests[0]
    assert asked["tool_choice"] == "none"
    assert any(loop.FIT_FINAL in str(m.get("content")) for m in asked["messages"])
    thread.refresh_from_db()
    assert "r0" in thread.settings["cleared"]
