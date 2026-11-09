"""Plan P, P4: Mylo's chat on any configured model server.

Each server is a loopback mock (``apps.core.llm_testservers``) speaking its
real wire format; the turn runs through ``default_port`` and the shared
client, exactly as in production. No key, no network.
"""

from __future__ import annotations

import json

import pytest
from apps.core import llm, llm_servers
from apps.core.llm import LLMContextLengthError, LLMResponse
from apps.core.llm_testservers import MockServer, reply

from tools.agent import compaction, loop, rebuild, service, store
from tools.agent.caller import for_thread

from .conftest import make_user, thread_for

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _fresh(monkeypatch, settings):
    monkeypatch.setenv("MOCK_LLM_KEY", "mock-key-value")
    settings.AGENT_MODEL = ""
    settings.LLM_ALLOW_CLOUD = True
    settings.LLM_FALLBACK = []
    llm_servers.reset()
    llm._breakers.clear()
    yield
    llm_servers.reset()


def _route(settings, *servers, agent=None):
    table = {"local": {"name": "local", "synthesized": True,
                       "location_stated": False}}
    for name, srv, extra in servers:
        table[name] = srv.server_entry(name, **extra)
    settings.LLM_SERVERS = table
    settings.LLM_ROUTES = {"agent": agent} if agent else {}


def _send(thread, text):
    service.send(for_thread(thread), thread, text, start=lambda t: None)


def _final(thread):
    finals = [e for e in store.events(thread)
              if e.type == "assistant" and e.payload.get("final")]
    return finals[-1].payload["text"] if finals else None


@pytest.mark.parametrize("kind", ["openai_compatible", "anthropic", "gemini",
                                  "ollama"])
def test_a_turn_with_two_function_calls_on_each_kind(kind, settings):
    person = make_user("ada")
    with MockServer(kind) as srv:
        _route(settings, ("chatbox", srv, {"label": "Chat box"}), agent="chatbox")
        srv.replies += [
            reply(thinking="I will look.", calls=[("me_profile", {}),
                                                  ("me_interests", {})]),
            reply("You are Ada."),
        ]
        thread = thread_for(person)
        _send(thread, "who am I?")
        assert loop.run_turn(thread.pk) == "idle"
        assert _final(thread) == "You are Ada."
        events = store.events(thread)
        results = [e for e in events if e.type == "tool_result"]
        assert [r.payload["status"] for r in results] == ["ok", "ok"]
        # The second request carried both results back to the server.
        sent = json.dumps(srv.requests[1])
        assert "@ada" in sent
    expected = "cloud" if kind in ("anthropic", "gemini") else "local"
    for e in events:
        if e.type == "assistant":
            assert e.payload["model"] == {"name": srv.model, "label": "Chat box",
                                          "location": expected}
    thinking = [e for e in events if e.type == "thinking"]
    assert thinking and thinking[0].payload["text"] == "I will look."
    if kind in ("anthropic", "gemini"):
        assert thinking[0].payload["opaque"]["kind"] == kind


def test_switching_servers_between_turns_drops_the_other_servers_state(settings):
    person = make_user("ada")
    with MockServer("anthropic") as claude, MockServer("gemini") as gem:
        _route(settings, ("claude", claude, {}), ("gem", gem, {}), agent="claude")
        claude.replies += [
            reply(thinking="Look first.", calls=[("me_profile", {})],
                  signature="claude-signature-1"),
            reply("You are Ada."),
        ]
        thread = thread_for(person)
        _send(thread, "who am I?")
        loop.run_turn(thread.pk)
        # The signed thinking block went back to Claude within the turn.
        assert "claude-signature-1" in json.dumps(claude.requests[1])

        _route(settings, ("claude", claude, {}), ("gem", gem, {}), agent="gem")
        gem.replies.append(reply("Still Ada."))
        _send(thread, "and again?")
        loop.run_turn(thread.pk)
        assert _final(thread) == "Still Ada."
        assert "claude-signature-1" not in json.dumps(gem.requests[0])
        events = store.events(thread)
        assert any("opaque" in m for m in rebuild.messages(thread, events,
                                                           kind="anthropic"))
        assert not any("opaque" in m for m in rebuild.messages(thread, events,
                                                               kind="gemini"))
        last = [e for e in events if e.type == "assistant"][-1]
        assert last.payload["model"]["location"] == "cloud"
        assert last.payload["model"]["name"] == gem.model


def test_a_context_overflow_compacts_and_retries(scripted, settings):
    person = make_user("ada")
    thread = thread_for(person)
    _send(thread, "first question")
    loop.run_turn(thread.pk, port=scripted("First answer.", '{"title": "t"}'))
    _send(thread, "second question")

    class Overflowing:
        def __init__(self):
            self.inner = scripted("A short summary.", "Second answer.")
            self.raised = False

        def __call__(self, **kw):
            if not self.raised:
                self.raised = True
                raise LLMContextLengthError("prompt is too long", server="x")
            return self.inner(**kw)

    assert loop.run_turn(thread.pk, port=Overflowing()) == "idle"
    types = [e.type for e in store.events(thread)]
    assert "compact" in types
    assert _final(thread) == "Second answer."


def test_a_second_overflow_fails_the_turn(scripted):
    person = make_user("ada")
    thread = thread_for(person)
    _send(thread, "q")

    def always(**kw):
        raise LLMContextLengthError("prompt is too long", server="x")

    assert loop.run_turn(thread.pk, port=always) == "error"


def test_status_says_where_chat_runs(settings):
    with MockServer("anthropic") as claude:
        _route(settings, ("claude", claude, {"label": "Claude"}), agent="claude")
        assert service.status() == {"model": {
            "name": claude.model, "label": "Claude", "location": "cloud"}}
        # Cloud off: the route is not honoured and chat stays local.
        settings.LLM_ALLOW_CLOUD = False
        settings.LLM_MODEL = "qwen"
        assert service.status() == {"model": {
            "name": "qwen", "label": "qwen", "location": "local"}}


def test_tools_agent_model_overrides_the_routed_servers_model(settings):
    with MockServer("ollama") as box:
        _route(settings, ("box", box, {}), agent="box")
        settings.AGENT_MODEL = "llama3:70b"
        assert service.status()["model"]["name"] == "llama3:70b"


def test_the_window_comes_from_the_server_unless_stated(settings):
    with MockServer("ollama", context=12288) as box:
        _route(settings, ("box", box, {}), agent="box")
        settings.AGENT_CONTEXT_WINDOW = 0
        assert compaction.window() == 12288
        settings.AGENT_CONTEXT_WINDOW = 4000
        assert compaction.window() == 4000


def test_the_activity_view_never_carries_opaque_state():
    from tools.agent import activity

    message = {"type": "thinking", "seq": 3, "payload": {
        "text": "secret reasoning",
        "opaque": {"kind": "anthropic", "blocks": [{"signature": "s"}]}}}
    shown = activity.project(message)
    assert "secret" not in json.dumps(shown) and "signature" not in json.dumps(shown)


def test_llmresponse_opaque_reaches_the_reply():
    from tools.agent.llmcall import parse

    response = LLMResponse(content="hi", opaque={"kind": "gemini", "blocks": [1]})
    assert parse(response, known=set()).opaque == {"kind": "gemini", "blocks": [1]}


def test_health_reports_server_location_and_whether_it_answers(settings):
    from apps.core.llm_testservers import dead_url

    from tools.agent import health

    with MockServer("ollama") as box:
        _route(settings, ("box", box, {}), agent="box")
        report = health.report(force=True)
    assert report["server"] == "box" and report["location"] == "local"
    assert report["answers"] is True and report["problem"] is None
    settings.LLM_ROUTES = {"agent": "ghost"}
    settings.LLM_BASE_URL = dead_url() + "/v1"
    report = health.report(force=True)
    assert report["server"] == "local" and report["answers"] is False
    assert "ghost" in report["problem"]
