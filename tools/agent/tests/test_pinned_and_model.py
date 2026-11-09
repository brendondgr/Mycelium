"""S3: pinned chats, and which model answers and where it runs."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from tools.agent import loop, service, store
from tools.agent.caller import for_thread

from .conftest import thread_for

pytestmark = pytest.mark.django_db
BASE = "/api/tools/agent"


def client_for(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


def test_pinned_threads_list_first(world):
    c = client_for(world.member)
    first = c.post(f"{BASE}/threads/", {}, format="json").json()["id"]
    second = c.post(f"{BASE}/threads/", {}, format="json").json()["id"]
    listed = [t["id"] for t in c.get(f"{BASE}/threads/").json()["threads"]]
    assert listed == [second, first]
    r = c.patch(f"{BASE}/threads/{first}/", {"pinned": True}, format="json")
    assert r.status_code == 200 and r.json()["pinned"] is True
    listed = c.get(f"{BASE}/threads/").json()["threads"]
    assert [t["id"] for t in listed] == [first, second]
    assert [t["pinned"] for t in listed] == [True, False]
    r = c.patch(f"{BASE}/threads/{first}/", {"pinned": "false"}, format="json")
    assert r.json()["pinned"] is False


def test_status_names_the_model_and_where_it_runs(world, settings):
    settings.LLM_MODEL = "qwen-test"
    settings.AGENT_MODEL = ""
    body = client_for(world.member).get(f"{BASE}/status/").json()
    assert body == {
        "model": {"name": "qwen-test", "label": "qwen-test", "location": "local"}
    }
    assert service.status() == body


def test_every_assistant_event_records_the_model(world, scripted):
    thread = thread_for(world.member)
    service.send(for_thread(thread), thread, "who am I?", start=lambda t: None)
    loop.run_turn(thread.pk, port=scripted([("me_profile", {})], "You are Member."))
    assistants = [e for e in store.events(thread) if e.type == "assistant"]
    assert len(assistants) == 2
    for e in assistants:
        assert e.payload["model"] == {
            "name": "test-model",
            "label": "test-model",
            "location": "local",
        }
