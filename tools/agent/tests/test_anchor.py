"""S2: a conversation about one thing (the anchor)."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from tools.agent import loop, service
from tools.agent.caller import Scope, for_thread

pytestmark = pytest.mark.django_db
BASE = "/api/tools/agent"


def client_for(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


def _system(request) -> str:
    return request["messages"][0]["content"]


def _turn(thread, text, model):
    service.send(for_thread(thread), thread, text, start=lambda t: None)
    loop.run_turn(thread.pk, port=model)


def test_an_anchored_thread_shows_one_on_every_turn(world, scripted):
    thread = service.create_thread(
        world.member, scope=Scope(), anchor={"kind": "lab", "key": "imaging"}
    )
    assert thread.settings["anchor"] == {"kind": "lab", "key": "imaging"}
    assert thread.settings["refs"][0]["n"] == 1
    model = scripted("First.", "{}", "Second.", "{}")
    _turn(thread, "what is this lab doing?", model)
    _turn(thread, "and now?", model)
    answers = [r for r in model.requests if r["tools"]]
    assert len(answers) == 2
    for request in answers:
        system = _system(request)
        assert "This conversation is about #1." in system
        assert "#1 lab: Imaging Lab" in system


def test_the_anchor_is_dropped_for_a_caller_who_cannot_see_it(world, scripted):
    from apps.accounts.models import LabMembership

    thread = service.create_thread(world.member, scope=Scope(), anchor="lab:imaging")
    LabMembership.objects.filter(user=world.member, lab=world.lab).delete()
    model = scripted("Hello.", "{}")
    _turn(thread, "hi", model)
    system = _system(model.requests[0])
    assert "This conversation is about" not in system
    assert "Imaging Lab" not in system


def test_creating_about_something_invisible_or_unknown_is_refused(world):
    with pytest.raises(service.ServiceError) as hidden:
        service.create_thread(world.outsider, scope=Scope(), anchor="lab:imaging")
    assert hidden.value.code == "anchor_not_visible" and hidden.value.status == 404
    with pytest.raises(service.ServiceError) as bad:
        service.create_thread(world.member, scope=Scope(), anchor="nonsense:1")
    assert bad.value.code == "bad_anchor"


def test_api_creates_and_filters_by_anchor(world):
    c = client_for(world.member)
    item = f"project:{world.lab_project.pk}"
    made = c.post(f"{BASE}/threads/", {"anchor": item}, format="json")
    assert made.status_code == 201
    assert made.json()["anchor"] == {
        "kind": "project",
        "key": str(world.lab_project.pk),
    }
    c.post(f"{BASE}/threads/", {}, format="json")
    c.post(
        f"{BASE}/threads/",
        {"anchor": {"kind": "lab", "key": "imaging"}},
        format="json",
    )
    found = c.get(f"{BASE}/threads/", {"anchor": item}).json()["threads"]
    assert [t["id"] for t in found] == [made.json()["id"]]
    assert len(c.get(f"{BASE}/threads/").json()["threads"]) == 3
    assert c.get(f"{BASE}/threads/", {"anchor": "x"}).status_code == 400
    refused = c.post(
        f"{BASE}/threads/",
        {"anchor": f"project:{world.other_project.pk}"},
        format="json",
    )
    assert refused.status_code == 404
