"""Phase 4: the system prompt, scope blocks, tagging and #n, compaction."""

from __future__ import annotations

import pytest

from tools.agent import loop, prompt, service, skills, store
from tools.agent.caller import Audience, Caller, Scope, for_thread
from tools.agent.models import AgentEvent

from .conftest import thread_for

pytestmark = pytest.mark.django_db


def _send(thread, text, **kw):
    return service.send(for_thread(thread), thread, text, start=lambda t: None, **kw)


def test_prompt_sections_in_order(world):
    thread = thread_for(world.member, "project", world.lab_project)
    c = for_thread(thread)
    loaded, deferred, unavailable = loop._visible_functions(c, thread)
    text = prompt.build(
        c,
        thread,
        deferred=deferred,
        skill_list=skills.available(),
        unavailable=unavailable,
        summary="we talked",
    )
    order = [
        "You are Mylo",
        "Who you are talking to",
        "This conversation belongs to a project",
        "Skills",
        "More functions",
        "Environment",
        "Earlier in this conversation",
    ]
    positions = [text.index(marker) for marker in order]
    assert positions == sorted(positions)
    assert "Segmentation" in text and "IMG-seg" in text
    # projects are loaded by default in a project thread
    assert "projects_feed" in {fn.name for fn in loaded}


def test_profile_block_is_stable_and_absent_where_others_read(world):
    from tools.agent import memory

    c = Caller(user=world.member, surface="web")
    assert memory.profile_block(c) == memory.profile_block(c)
    assert "@member" in memory.profile_block(c)
    lab = Caller(
        user=world.member,
        surface="discord",
        scope=Scope("lab", world.lab),
        audience=Audience("lab"),
    )
    assert memory.profile_block(lab) == ""


def test_profile_block_is_capped(world):
    from tools.agent import memory

    profile = world.member.profile
    profile.interests = {
        "clusters": [
            {"id": f"c{i}", "label": "x" * 80, "areas": ["y" * 60] * 6}
            for i in range(40)
        ]
    }
    profile.save()
    block = memory.profile_block(Caller(user=world.member, surface="web"))
    assert len(block) <= memory.PROFILE_CAP + 40


def test_mentions_are_checked_numbered_and_carded(world):
    thread = thread_for(world.member)
    _send(thread, "what about this?", mentions=[f"project:{world.lab_project.pk}"])
    user_event = AgentEvent.objects.get(thread=thread, type="user")
    assert user_event.payload["cards"][0].startswith("#1 project: Segmentation")
    with pytest.raises(service.ServiceError) as exc:
        _send(thread, "and this?", mentions=[f"project:{world.other_project.pk}"])
    assert exc.value.code == "mention_not_visible"


def test_the_references_block_lists_thread_numbers(world, scripted):
    thread = thread_for(world.member)
    _send(thread, "look", mentions=[f"project:{world.lab_project.pk}"])
    model = scripted("See #1.")
    loop.run_turn(thread.pk, port=model)
    system = model.requests[0]["messages"][0]["content"]
    assert "References in this conversation:\n#1 project: Segmentation" in system
    verdict = AgentEvent.objects.get(thread=thread, type="verdict")
    assert verdict.payload["ok"] is True


def test_compaction_clears_then_summarizes(world, scripted, settings):
    settings.AGENT_CONTEXT_WINDOW = 4000
    thread = thread_for(world.member)
    for i in range(3):
        store.append(thread, "user", {"text": f"question {i} " + "words " * 200})
        store.append(
            thread,
            "assistant",
            {
                "text": "",
                "tool_calls": [
                    {"id": f"r{i}", "name": "me_profile", "arguments": "{}"}
                ],
            },
        )
        store.append(
            thread,
            "tool_result",
            {
                "call_id": f"r{i}",
                "name": "me_profile",
                "status": "ok",
                "content": "data " * 600,
            },
        )
        store.append(thread, "assistant", {"text": f"answer {i}", "final": True})
    _send(thread, "and now?")
    model = scripted("Summary of before.", "Fine.")
    loop.run_turn(thread.pk, port=model)
    thread.refresh_from_db()
    assert thread.settings.get("cleared")
    compact = AgentEvent.objects.filter(thread=thread, type="compact").first()
    assert compact is not None and compact.payload["summary"] == "Summary of before."
    final_system = model.requests[1]["messages"][0]["content"]
    assert "Earlier in this conversation (summary):\nSummary of before." in final_system


def test_context_full_stops_the_turn(world, scripted, settings):
    settings.AGENT_CONTEXT_WINDOW = 50
    thread = thread_for(world.member)
    _send(thread, "hello " * 400)
    loop.run_turn(thread.pk, port=scripted("x", "y"))
    error = AgentEvent.objects.filter(thread=thread, type="error").first()
    assert error is not None and error.payload["code"] == "context_full"


def test_skills_are_listed_and_readable():
    names = {s.name for s in skills.available()}
    assert {
        "grant-fit",
        "paper-question",
        "project-review",
        "who-should-apply",
        "what-mylo-knows",
    } <= names
    assert "#" in skills.read("grant-fit")


def test_recall_is_stored_with_the_message(world, scripted):
    first = thread_for(world.member)
    _send(first, "I'm planning to use conformal prediction for IMG-seg")
    loop.run_turn(
        first.pk,
        port=scripted(
            "Noted.",
            '{"title": "Conformal prediction", "purpose": "uncertainty for IMG-seg"}',
        ),
    )
    second = thread_for(world.member)
    _send(second, "what did we say about conformal prediction?")
    model = scripted("We discussed it.")
    loop.run_turn(second.pk, port=model)
    recall = AgentEvent.objects.get(thread=second, type="recall")
    assert (
        "Conformal prediction" in recall.payload["text"]
        or "uncertainty" in recall.payload["text"]
    )
    user_msg = model.requests[0]["messages"][1]["content"]
    assert user_msg.startswith("<memory note=")


def test_a_function_loaded_in_one_step_is_offered_in_the_next(world, scripted):
    # The result says "available from your next step"; the loop read the list
    # of loaded functions from the copy of the thread it began the turn with,
    # so the model was sent no schema for them until the turn after.
    thread = thread_for(world.member)
    _send(thread, "what does the graph hold about me?")
    model = scripted(
        [("load_functions", {"names": ["knowledge_my_concepts"]})], "Loaded."
    )
    loop.run_turn(thread.pk, port=model)

    def offered(request):
        return {t["function"]["name"] for t in request["tools"] or []}

    assert "knowledge_my_concepts" not in offered(model.requests[0])
    assert "knowledge_my_concepts" in offered(model.requests[1])


def test_putting_results_away_keeps_what_the_calls_wrote_meanwhile(world):
    # Clearing old results wrote the whole settings back from the loop's copy:
    # references numbered and functions loaded since that copy was read were
    # undone, and the next call on one of those references was refused.
    from tools._framework.agentspec import RefInfo

    from tools.agent import compaction, refs
    from tools.agent.models import AgentThread

    thread = thread_for(world.member)
    stale = AgentThread.objects.get(pk=thread.pk)  # the turn's first copy
    lab = RefInfo(kind="lab", key=str(world.lab.pk), title="Imaging Lab", output="lab")
    assert refs.number(thread, lab) == 1
    store.save_setting(thread, "loaded", lambda _: ["projects_feed"])
    for i in range(4):
        store.append(
            stale,
            "assistant",
            {"text": "", "tool_calls": [{"id": f"r{i}", "name": "x", "arguments": "{}"}]},
        )
        store.append(
            stale, "tool_result", {"call_id": f"r{i}", "name": "x", "status": "ok"}
        )
    assert compaction.clear_old_results(stale, store.events(stale))
    kept = AgentThread.objects.get(pk=thread.pk).settings
    assert kept["cleared"] == ["r0", "r1"]
    assert [e["n"] for e in kept["refs"]] == [1]
    assert kept["loaded"] == ["projects_feed"]
