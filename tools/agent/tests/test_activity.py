"""S1: the activity view shows what Mylo is doing and never its thinking."""

from __future__ import annotations

import json

import pytest
from apps.core.llm import LLMResponse, ToolCall
from rest_framework.test import APIClient

from tools.agent import activity, loop, service, store, stream
from tools.agent.caller import for_thread

from .conftest import make_user, thread_for

pytestmark = pytest.mark.django_db
BASE = "/api/tools/agent"


def client_for(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


def _three_calls(thread, scripted):
    service.send(for_thread(thread), thread, "what's new?", start=lambda t: None)
    step = LLMResponse(
        content="",
        reasoning="SECRET REASONING about the person",
        finish_reason="tool_calls",
        tool_calls=(
            ToolCall(id="a", name="me_profile", arguments="{}"),
            ToolCall(
                id="b",
                name="corpus_search",
                arguments=json.dumps({"query": "cell segmentation"}),
            ),
            ToolCall(id="c", name="feeds_saved", arguments="{}"),
        ),
        usage={"total_tokens": 10},
    )
    loop.run_turn(thread.pk, port=scripted(step, "Here is what I found."))


@pytest.fixture
def ada():
    return make_user("ada")


def test_three_calls_stream_three_labelled_steps_and_no_thinking(ada, scripted):
    thread = thread_for(ada)
    _three_calls(thread, scripted)
    assert "thinking" in [e.type for e in store.events(thread)]
    shown = list(stream.follow(thread, follow_live=False, view="activity"))
    body = json.dumps(shown)
    assert "SECRET REASONING" not in body
    assert "cell segmentation" in body  # the label's slot, nothing more
    steps = [m["payload"] for m in shown if m["type"] == "activity"]
    running = [s for s in steps if s["state"] == "running"]
    closed = [s for s in steps if s["state"] in ("ok", "failed")]
    assert [s["label"] for s in running] == [
        "Looking at your profile",
        "Searching the corpus for “cell segmentation”",
        "Looking at saved items",
    ]
    assert [s["call_id"] for s in closed] == ["a", "b", "c"]
    assert all(s["label"] for s in closed)
    assert {"state": "thinking"} in steps
    types = {m["type"] for m in shown}
    assert not types & {"usage", "verdict", "recall", "tool_call", "tool_result"}
    final = [m for m in shown if m["type"] == "assistant"]
    assert final[-1]["payload"]["text"] == "Here is what I found."
    assert "tool_calls" not in json.dumps([m["payload"] for m in final])
    assert all("id" in m for m in shown)  # Last-Event-ID still works


def test_thinking_deltas_collapse_and_text_deltas_pass():
    p = activity.Projector()
    out = [
        p.project({"type": "delta", "kind": "thinking", "text": "hmm"}),
        p.project({"type": "delta", "kind": "thinking", "text": "more"}),
        p.project({"type": "delta", "kind": "text", "text": "Hi"}),
        p.project({"type": "progress", "name": "x", "status": "ok"}),
        p.project({"type": "note", "payload": {"text": "go", "to_model": True}}),
    ]
    assert out[0] == {"type": "activity", "payload": {"state": "thinking"}}
    assert out[1] is None and out[3] is None and out[4] is None
    assert out[2]["text"] == "Hi"


def test_a_ref_slot_shows_the_title_not_the_id(ada):
    thread = thread_for(ada)
    data = dict(thread.settings or {})
    data["refs"] = [{"n": 3, "ref": "item:abc", "kind": "item", "title": "Cells"}]
    thread.settings = data
    thread.save()
    p = activity.Projector(thread)
    msg = p.project(
        {
            "id": 9,
            "type": "tool_call",
            "payload": {"call_id": "x", "name": "corpus_item", "args": {"item": "#3"}},
        }
    )
    assert msg["payload"]["label"] == "Reading “Cells”"
    unknown = activity.label("corpus_item", {"item": "item:zzz"})
    assert unknown == "Reading an item"
    assert activity.label("no_such_function", {}) == activity.FALLBACK_LABEL


def test_routes_default_to_activity_and_raw_is_staff_only(ada, scripted):
    thread = thread_for(ada)
    _three_calls(thread, scripted)
    c = client_for(ada)
    events = c.get(f"{BASE}/threads/{thread.pk}/events/").json()["events"]
    assert "SECRET REASONING" not in json.dumps(events)
    assert any(e["type"] == "activity" for e in events)
    r = c.get(f"{BASE}/threads/{thread.pk}/stream/?once=1")
    body = b"".join(r.streaming_content).decode()
    assert "event: activity" in body and "SECRET REASONING" not in body
    for route in ("events/?view=raw", "stream/?once=1&view=raw"):
        r = c.get(f"{BASE}/threads/{thread.pk}/{route}")
        assert r.status_code == 403 and r.json()["code"] == "raw_view_staff_only"
    assert c.get(f"{BASE}/threads/{thread.pk}/events/?view=x").status_code == 400
    ada.is_staff = True
    ada.save()
    raw = c.get(f"{BASE}/threads/{thread.pk}/events/?view=raw").json()["events"]
    assert "SECRET REASONING" in json.dumps(raw)
