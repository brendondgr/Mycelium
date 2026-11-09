"""Phase 5: the conversation log, streaming, the API and the CLI."""

from __future__ import annotations

from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from tools.agent import loop, service, store, stream, tasks
from tools.agent.models import AgentEvent, AgentThread

from .conftest import ScriptedModel, make_user, thread_for

pytestmark = pytest.mark.django_db
BASE = "/api/tools/agent"


@pytest.fixture
def turns(monkeypatch):
    """Run the turn inline with a scripted model instead of the worker."""
    script: list = []

    def delay(thread_id):
        loop.run_turn(thread_id, port=ScriptedModel(*script))
        return type("R", (), {"id": "inline"})()

    monkeypatch.setattr(tasks.run_turn, "delay", delay)
    return script


def client_for(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


def test_status_reports_no_model(world, settings):
    settings.LLM_MODEL = ""
    settings.AGENT_MODEL = ""
    body = client_for(world.member).get(f"{BASE}/status/").json()
    assert body["code"] == "no_model" and body["fix"]


def test_thread_lifecycle(world, turns):
    c = client_for(world.member)
    made = c.post(
        f"{BASE}/threads/",
        {"scope": "project", "ref": str(world.lab_project.pk)},
        format="json",
    )
    assert made.status_code == 201 and made.json()["scope"] == "project"
    tid = made.json()["id"]
    turns[:] = [
        "The project is on track.",
        '{"title": "Project check", "purpose": "status of segmentation"}',
    ]
    sent = c.post(
        f"{BASE}/threads/{tid}/messages/", {"text": "how is it going?"}, format="json"
    )
    assert sent.status_code == 202 and sent.json()["status"] == "started"
    events = c.get(f"{BASE}/threads/{tid}/events/").json()["events"]
    assert any(e["type"] == "assistant" and e["payload"].get("final") for e in events)
    later = c.get(f"{BASE}/threads/{tid}/events/?after=3").json()["events"]
    assert all(e["seq"] > 3 for e in later)
    listed = c.get(f"{BASE}/threads/?q=segmentation").json()["threads"]
    assert [t["id"] for t in listed] == [tid]
    renamed = c.patch(
        f"{BASE}/threads/{tid}/", {"title": "Renamed", "archived": True}, format="json"
    ).json()
    assert renamed["title"] == "Renamed" and renamed["archived"] is True
    assert c.get(f"{BASE}/threads/").json()["threads"] == []
    assert c.delete(f"{BASE}/threads/{tid}/").status_code == 204
    assert not AgentEvent.objects.filter(thread_id=tid).exists()


def test_post_routes_accept_no_trailing_slash(world, turns):
    c = client_for(world.member)
    assert c.post(f"{BASE}/threads", {}, format="json").status_code == 201


def test_someone_elses_thread_is_not_found_even_for_an_org_admin(world):
    thread = thread_for(world.member, "lab", world.lab)
    store.append(thread, "user", {"text": "private"})
    for user in (world.owner, world.admin, world.outsider):
        c = client_for(user)
        assert c.get(f"{BASE}/threads/{thread.pk}/").status_code == 404
        assert c.get(f"{BASE}/threads/{thread.pk}/events/").status_code == 404
        assert c.get(f"{BASE}/threads/{thread.pk}/stream/?once=1").status_code == 404
        assert c.get(f"{BASE}/threads/{thread.pk}/export/").status_code == 404


def test_a_scope_you_cannot_see_is_refused(world):
    c = client_for(world.outsider)
    r = c.post(f"{BASE}/threads/", {"scope": "lab", "ref": "imaging"}, format="json")
    assert r.status_code == 404


def test_unverified_people_are_refused(world, db):
    user = make_user("unverified", verified=False)
    r = client_for(user).post(f"{BASE}/threads/", {}, format="json")
    assert r.status_code == 403


def test_stream_replays_with_ids_and_last_event_id(world):
    thread = thread_for(world.member)
    for i in range(5):
        store.append(thread, "note", {"text": f"n{i}"})
    c = client_for(world.member)
    r = c.get(f"{BASE}/threads/{thread.pk}/stream/?once=1", HTTP_LAST_EVENT_ID="3")
    assert r["Content-Type"] == "text/event-stream"
    assert r["Cache-Control"] == "no-cache" and r["X-Accel-Buffering"] == "no"
    body = b"".join(r.streaming_content).decode()
    assert "id: 4" in body and "id: 5" in body and "id: 3\n" not in body


def test_reconnect_loses_nothing_and_duplicates_nothing(world):
    thread = thread_for(world.member)
    for i in range(3):
        store.append(thread, "note", {"text": f"n{i}"})
    follow = stream.follow(thread, after=1, poll=0.01, max_seconds=2)
    got = [next(follow)["id"], next(follow)["id"]]  # replay: 2, 3 (now subscribed)
    store.append(thread, "note", {"text": "n3"})
    store.append(thread, "note", {"text": "n4"})
    bus = stream.bus()
    bus.publish(
        stream.thread_channel(thread.pk), {"id": 3, "type": "note"}
    )  # duplicate
    bus.publish(stream.thread_channel(thread.pk), {"type": "delta", "text": "x"})
    bus.publish(stream.thread_channel(thread.pk), {"id": 5, "type": "note"})  # gap: 4
    for msg in follow:
        if msg.get("id"):
            got.append(msg["id"])
        if msg.get("id") == 5:
            break
    assert got == [2, 3, 4, 5]


def test_answer_and_cancel_routes(world, turns):
    c = client_for(world.member)
    tid = c.post(f"{BASE}/threads/", {}, format="json").json()["id"]
    turns[:] = [[("ask_user", {"question": "Which project?"})]]
    c.post(f"{BASE}/threads/{tid}/messages/", {"text": "help"}, format="json")
    assert AgentThread.objects.get(pk=tid).state == "waiting"
    turns[:] = ["Thanks."]
    r = c.post(f"{BASE}/threads/{tid}/answer/", {"text": "the thesis"}, format="json")
    assert r.status_code == 202
    assert AgentThread.objects.get(pk=tid).state == "idle"
    r = c.post(f"{BASE}/threads/{tid}/answer/", {"text": "again"}, format="json")
    assert r.status_code == 409
    assert c.post(f"{BASE}/threads/{tid}/cancel/", {}, format="json").status_code == 202
    assert stream.cancel_requested(tid)


def test_fork_and_export(world, turns):
    c = client_for(world.member)
    tid = c.post(f"{BASE}/threads/", {}, format="json").json()["id"]
    turns[:] = ["About #1: it is your lab's project."]
    c.post(
        f"{BASE}/threads/{tid}/messages/",
        {"text": "tell me about it", "mentions": [f"project:{world.lab_project.pk}"]},
        format="json",
    )
    fork = c.post(f"{BASE}/threads/{tid}/fork/", {"seq": 2}, format="json")
    assert fork.status_code == 201 and fork.json()["parent"] == tid
    data = c.get(f"{BASE}/threads/{tid}/export/").json()
    assert data["references"][0]["title"] == "Segmentation"
    md = c.get(f"{BASE}/threads/{tid}/export/?as=md").content.decode()
    assert "#1 (Segmentation)" in md
    # once the person can no longer see it, the export no longer shows it
    from apps.research.models import ProjectMember

    ProjectMember.objects.filter(user=world.member, project=world.lab_project).delete()
    data = c.get(f"{BASE}/threads/{tid}/export/").json()
    assert data["references"][0]["title"] == "(no longer available)"
    assert "Segmentation" not in str(data["events"])


def test_ref_search_returns_only_visible_objects(world):
    c = client_for(world.member)
    found = c.get(f"{BASE}/refs/search/?q=Se&kinds=project").json()["results"]
    titles = {r["title"] for r in found}
    assert "Segmentation" in titles and "Secret" not in titles


def test_preferences_and_policy(world):
    c = client_for(world.member)
    assert c.get(f"{BASE}/preferences/").json()["learning"] is True
    assert (
        c.patch(f"{BASE}/preferences/", {"learning": False}, format="json").json()[
            "learning"
        ]
        is False
    )
    assert c.get(f"{BASE}/policy/lab/imaging/").json()["set"] is False
    assert (
        c.patch(
            f"{BASE}/policy/lab/imaging/", {"groups_off": ["corpus"]}, format="json"
        ).status_code
        == 403
    )
    admin = client_for(world.admin)
    r = admin.patch(
        f"{BASE}/policy/lab/imaging/", {"groups_off": ["corpus"]}, format="json"
    )
    assert r.status_code == 200 and r.json()["groups_off"] == ["corpus"]
    assert (
        client_for(world.outsider).get(f"{BASE}/policy/lab/imaging/").status_code == 404
    )
    assert c.get(f"{BASE}/policy/nonsense/x/").status_code == 404


def test_catalog_endpoint_uses_the_gate(world):
    rows = (
        client_for(world.member)
        .get(f"{BASE}/catalog/?scope=lab&ref=imaging")
        .json()["functions"]
    )
    by_name = {r["name"]: r for r in rows}
    assert by_name["me_profile"]["allowed"] is True
    free = client_for(world.free).get(f"{BASE}/catalog/").json()["functions"]
    assert free[0]["code"] == "not_entitled"


def test_daily_turn_limit(world, settings, turns):
    settings.AGENT_DAILY_TURNS = 1
    c = client_for(world.member)
    tid = c.post(f"{BASE}/threads/", {}, format="json").json()["id"]
    turns[:] = ["One."]
    assert (
        c.post(
            f"{BASE}/threads/{tid}/messages/", {"text": "a"}, format="json"
        ).status_code
        == 202
    )
    r = c.post(f"{BASE}/threads/{tid}/messages/", {"text": "b"}, format="json")
    assert r.status_code == 429 and r.json()["code"] == "daily_limit"


def test_retention_sweep(world, settings):
    old = thread_for(world.member)
    fresh = thread_for(world.member)
    AgentThread.objects.filter(pk=old.pk).update(
        last_activity_at=timezone.now() - timedelta(days=40)
    )
    assert tasks.retention_sweep() == 0  # keep by default
    settings.AGENT_RETENTION_DAYS = 30
    tasks.retention_sweep()
    assert not AgentThread.objects.filter(pk=old.pk).exists()
    assert AgentThread.objects.filter(pk=fresh.pk).exists()


def test_resume_sweep_restarts_stuck_turns(world, monkeypatch):
    stuck = thread_for(world.member)
    AgentThread.objects.filter(pk=stuck.pk).update(
        state="running", last_activity_at=timezone.now() - timedelta(minutes=30)
    )
    started = []
    monkeypatch.setattr(tasks.run_turn, "delay", lambda pk: started.append(pk))
    assert tasks.resume_stuck_turns() == 1 and started == [str(stuck.pk)]


def test_cli_chat_one_message(world, monkeypatch):
    from tools.agent import llmcall

    monkeypatch.setattr(
        llmcall,
        "default_port",
        lambda: ScriptedModel(
            "Hello from the terminal.", '{"title": "t", "purpose": "p"}'
        ),
    )
    monkeypatch.setattr(loop, "default_port", llmcall.default_port)
    out = StringIO()
    call_command("agent", "chat", "--user", "member", "--message", "hi", stdout=out)
    assert "Hello from the terminal." in out.getvalue()
    from apps.accounts.models import AuditEvent

    assert AuditEvent.objects.filter(action="agent.cli").exists()


def test_service_lookup_reaches_the_agent():
    from tools._framework import services

    agent = services.get("agent")
    assert agent is service or agent.__name__ == "tools.agent.service"
