"""Plan D, phase D1: shared conversations, per-turn callers, guests.

Everything here runs with the scripted model and no Discord: a shared thread is
an agent thread with no owner, each question is a turn under its own asker, and
a guest stands where a member of the place's lab stands, narrowed by a level.
"""

from __future__ import annotations

import pytest

from tools.agent import loop, permissions, service, store
from tools.agent.caller import Audience, Caller, Guest, Scope, for_thread, for_turn
from tools.agent.models import AgentOrgPolicy, AgentQueuedMessage, AgentThread

pytestmark = pytest.mark.django_db

ROOM = {"channel_id": "10", "thread_id": "11"}


def member(user, lab, *, width="lab", obj=None, via=None):
    return Caller(
        user=user,
        surface="discord",
        scope=Scope("lab", lab),
        audience=Audience(width, obj or lab),
        via={**ROOM, "discord_user_id": f"d{user.pk}", **(via or {})},
    )


def guest(lab, *, name="Visitor", discord_id="4242"):
    return Caller(
        user=None,
        guest=Guest(discord_id, name),
        surface="discord",
        scope=Scope("lab", lab),
        audience=Audience("lab", lab),
        via=dict(ROOM),
    )


def shared_thread(caller, title="Grant thread"):
    return service.create_thread(
        None,
        scope=caller.scope,
        surface="discord",
        title=title,
        caller=caller,
        shared=True,
    )


def ask(caller, thread, text):
    return service.send(
        _with_thread(caller, thread), thread, text, start=lambda t: None
    )


def _with_thread(caller, thread):
    from dataclasses import replace

    return replace(caller, thread_id=thread.pk)


def run(thread, model):
    return loop.run_turn(thread.pk, port=model)


def tool_names(request) -> set[str]:
    return {t["function"]["name"] for t in request["tools"] or []}


def expected_tools(caller, thread) -> set[str]:
    thread.refresh_from_db()
    loaded = set((thread.settings or {}).get("loaded", []))
    return {
        fn.name
        for fn in permissions.allowed_functions(_with_thread(caller, thread))
        if fn.core or fn.name in loaded
    }


@pytest.fixture
def place(world):
    """The lab's server: a shared project, a declared member profile."""
    world.lab_project.share_in_lab_reports = True
    world.lab_project.save(update_fields=["share_in_lab_reports"])
    profile = world.member.profile
    profile.interests = {"clusters": [{"label": "cell imaging", "areas": ["CNN"]}]}
    profile.save(update_fields=["interests"])
    return world


def results(thread, after=0):
    return [
        e.payload for e in store.events(thread, after=after) if e.type == "tool_result"
    ]


# --------------------------------------------------------------------------- #
# Turns and askers
# --------------------------------------------------------------------------- #


def test_two_members_and_a_guest_take_turns_each_with_their_own_functions(
    place, scripted
):
    a, b, g = (
        member(place.member, place.lab),
        member(place.admin, place.lab),
        guest(place.lab),
    )
    thread = shared_thread(a)
    assert thread.shared and thread.user_id is None

    ask(a, thread, "load the people and full text tools")
    model = scripted(
        [("load_functions", {"names": ["org_lab_members", "fulltext_availability"]})],
        "Loaded.",
    )
    run(thread, model)
    assert tool_names(model.requests[0]) == expected_tools(a, thread) - {
        "org_lab_members",
        "fulltext_availability",
    }

    ask(b, thread, "and for me?")
    model = scripted("Here.")
    run(thread, model)
    assert tool_names(model.requests[0]) == expected_tools(b, thread)
    assert "org_lab_members" in tool_names(model.requests[0])

    ask(g, thread, "and for a guest?")
    model = scripted("Here too.")
    run(thread, model)
    names = tool_names(model.requests[0])
    assert names == expected_tools(g, thread)
    assert "org_lab_members" in names  # guest level full: people included
    assert "fulltext_availability" in names  # a guest reads papers too

    speakers = [
        e.payload["speaker"]["kind"] for e in store.events(thread) if e.type == "user"
    ]
    assert speakers == ["member", "member", "guest"]


def test_a_guest_reads_the_place_and_is_refused_elsewhere(place, scripted):
    a, g = member(place.member, place.lab), guest(place.lab)
    thread = shared_thread(a)
    ask(a, thread, "what is our lab about?")
    run(thread, scripted([("org_lab", {})], "It images cells."))
    before = store.last_seq(thread)

    ask(g, thread, "tell me everything")
    model = scripted(
        [
            (
                "load_functions",
                {
                    "names": [
                        "org_lab",
                        "feeds_slate",
                        "projects_list",
                        "org_lab_members",
                        "org_person",
                    ]
                },
            ),
        ],
        [
            ("org_lab", {}),
            ("feeds_slate", {}),
            ("projects_list", {}),
            ("org_lab_members", {}),
            ("org_person", {"person": "person:member"}),
            ("org_lab", {"lab": "lab:other"}),
            ("org_person", {"person": "person:outsider"}),
        ],
        "Done.",
    )
    run(thread, model)
    got = {r["call_id"]: r for r in results(thread, after=before)}
    by_name = [(r["name"], r["status"]) for r in got.values()]
    assert ("org_lab", "ok") in by_name
    assert ("feeds_slate", "ok") in by_name
    assert ("projects_list", "ok") in by_name
    assert ("org_lab_members", "ok") in by_name
    assert by_name.count(("org_person", "ok")) == 1
    assert ("org_lab", "denied") in by_name  # another lab
    assert ("org_person", "denied") in by_name  # someone outside the lab
    contents = "\n".join(r.get("content", "") for r in got.values())
    assert "Segmentation" in contents  # the shared project
    assert "cell imaging" in contents  # a member's declared interests

    # The guest's context holds no function result from the member's turn.
    first = model.requests[0]["messages"]
    assert not [m for m in first if m["role"] == "tool"]
    assert any(
        m["role"] == "assistant" and m["content"] == "It images cells." for m in first
    )
    assert "[Visitor, guest]" in first[-1]["content"]


def test_guest_levels_narrow_the_catalog_and_off_refuses(place):
    g = guest(place.lab)
    full = {fn.name for fn in permissions.allowed_functions(g)}
    assert {"org_lab_members", "org_person", "knowledge_people_for_call"} <= full

    AgentOrgPolicy.objects.create(lab=place.lab, discord_guests="no_people")
    no_people = {fn.name for fn in permissions.allowed_functions(g)}
    assert full - no_people == {
        "org_lab_members",
        "org_person",
        "knowledge_people_for_call",
    }

    AgentOrgPolicy.objects.filter(lab=place.lab).update(discord_guests="public")
    public = {fn.name for fn in permissions.allowed_functions(g)}
    assert public == {
        "corpus_item",
        "corpus_search",
        "find_functions",
        "fulltext_availability",
        "fulltext_read_paper",
        "fulltext_search_paper",
        "load_functions",
        "read_skill",
    }

    AgentOrgPolicy.objects.filter(lab=place.lab).update(discord_guests="off")
    with pytest.raises(service.ServiceError) as err:
        shared_thread(g)
    assert err.value.code == "guests_off"


def test_the_host_ceiling_wins_over_a_wider_lab(place, settings):
    settings.AGENT_DISCORD_GUEST_LEVEL = "no_people"
    AgentOrgPolicy.objects.create(lab=place.lab, discord_guests="full")
    g = guest(place.lab)
    assert permissions.guest_level(g) == "no_people"
    assert "org_person" not in {fn.name for fn in permissions.allowed_functions(g)}
    assert service.guest_level_in_force("lab", place.lab) == "no_people"


def test_discord_access_linked_or_entitled_refuses_guests(place, settings):
    settings.AGENT_DISCORD_ACCESS = "linked"
    d = permissions.may_chat(guest(place.lab))
    assert (d.verdict, d.code) == ("deny", "guests_off")


def test_entitled_access_asks_for_the_plan_in_discord_only(place, settings):
    free = member(place.free, place.lab)
    assert permissions.may_chat(free).allowed  # public: no plan check here
    settings.AGENT_DISCORD_ACCESS = "entitled"
    assert permissions.may_chat(free).code == "not_entitled"


def test_a_guest_never_sees_more_about_a_person_than_a_member(place, scripted):
    from tools.agent import dispatch

    m = member(place.admin, place.lab)
    g = guest(place.lab)
    thread = shared_thread(m)
    as_member = dispatch.run(
        _with_thread(m, thread),
        thread,
        name="org_person",
        args={"person": "person:member"},
        call_id="x1",
    )
    as_guest = dispatch.run(
        _with_thread(g, thread),
        thread,
        name="org_person",
        args={"person": "person:member"},
        call_id="x2",
    )
    assert as_member["status"] == as_guest["status"] == "ok"
    assert set(as_guest["content"].splitlines()) <= set(
        as_member["content"].splitlines()
    )


def test_a_lab_only_result_is_absent_where_the_department_reads(place):
    from tools.agent import dispatch

    c = Caller(
        user=place.owner,
        surface="discord",
        scope=Scope("department", place.dept),
        audience=Audience("department", place.dept),
        via={"channel_id": "20"},
    )
    thread = shared_thread(c, title="Dept room")
    c = _with_thread(c, thread)
    lab_overview = dispatch.run(
        c, thread, name="org_lab", args={"lab": "lab:imaging"}, call_id="y1"
    )
    assert lab_overview["status"] == "denied"
    project = dispatch.run(
        c,
        thread,
        name="projects_get",
        args={"project": f"project:{place.lab_project.pk}"},
        call_id="y2",
    )
    assert project["status"] == "denied"


# --------------------------------------------------------------------------- #
# The queue
# --------------------------------------------------------------------------- #


def test_queued_questions_get_one_turn_each_under_their_own_asker(place, scripted):
    a, b, c, g = (
        member(place.member, place.lab),
        member(place.admin, place.lab),
        member(place.owner, place.lab),
        guest(place.lab),
    )
    thread = shared_thread(a)
    ask(a, thread, "first")
    store.set_state(thread, AgentThread.State.RUNNING)
    for who, text in ((b, "second"), (c, "third"), (g, "fourth")):
        assert ask(who, thread, text)["status"] == "queued"
    store.set_state(thread, AgentThread.State.IDLE)
    model = scripted("one", "two", "three", "four")
    assert run(thread, model) == "idle"

    users = [e.payload for e in store.events(thread) if e.type == "user"]
    assert [u["text"] for u in users] == ["first", "second", "third", "fourth"]
    assert [u["speaker"]["name"] for u in users] == [
        "Member",
        "Admin",
        "Owner",
        "Visitor",
    ]
    finals = [
        e.payload["text"]
        for e in store.events(thread)
        if e.type == "assistant" and e.payload.get("final")
    ]
    assert finals == ["one", "two", "three", "four"]
    # each request answered exactly its own question
    asked = [r["messages"][-1]["content"] for r in model.requests]
    assert [q.rsplit("\n", 1)[-1] for q in asked] == [
        "first",
        "second",
        "third",
        "fourth",
    ]
    assert "guest" in model.requests[3]["messages"][0]["content"]
    assert not AgentQueuedMessage.objects.filter(thread=thread).exists()


def test_a_sixth_waiting_question_is_turned_away(place):
    a = member(place.member, place.lab)
    thread = shared_thread(a)
    ask(a, thread, "first")
    store.set_state(thread, AgentThread.State.RUNNING)
    for i in range(service.SHARED_QUEUE_MAX):
        ask(guest(place.lab, discord_id=str(i)), thread, f"q{i}")
    with pytest.raises(service.ServiceError) as err:
        ask(a, thread, "one more")
    assert err.value.detail == "One at a time, please."


def test_speaker_names_are_cleaned_and_capped(place):
    g = guest(place.lab, name="<@123> @everyone `drop`|table\n" + "x" * 100)
    speaker = g.speaker()
    assert "@" not in speaker["name"] and "<" not in speaker["name"]
    assert "`" not in speaker["name"] and "|" not in speaker["name"]
    assert len(speaker["name"]) <= 64


# --------------------------------------------------------------------------- #
# Web threads are untouched; shared threads never reach the web
# --------------------------------------------------------------------------- #


def test_a_turn_without_a_turn_payload_is_the_owner_as_before(place):
    from .conftest import thread_for

    thread = thread_for(place.member)
    service.send(for_thread(thread), thread, "hi", start=lambda t: None)
    rebuilt = for_turn(thread)
    assert rebuilt == for_thread(thread)
    event = store.events(thread)[-1]
    assert "speaker" not in event.payload and "turn" not in event.payload


def test_no_web_route_returns_a_shared_thread(place, client):
    a = member(place.member, place.lab)
    thread = shared_thread(a)
    assert thread not in service.list_threads(place.member)
    with pytest.raises(service.ServiceError):
        service.get_thread(place.member, thread.pk)
    web = for_thread(service.create_thread(place.member, scope=Scope()))
    with pytest.raises(service.ServiceError):
        service.thread_events(web, thread)
    client.force_login(place.member)
    base = "/api/tools/agent/threads/"
    listed = client.get(base).json()["threads"]
    assert str(thread.pk) not in {t["id"] for t in listed}
    assert client.get(f"{base}{thread.pk}/").status_code == 404
    assert client.get(f"{base}{thread.pk}/events/").status_code == 404
