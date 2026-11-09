"""Routing, the llmkit bridge, fallback and the per-server ledger.

Every server is a loopback mock (``apps.core.llm_testservers``) speaking the
real wire format, driven through the official SDKs. No key, no network.
"""

import json
from datetime import date

import pytest
from django.test import override_settings

from apps.core import llm, llm_servers
from apps.core.llm import (
    FallbackClient,
    LLMClient,
    LLMContextLengthError,
    build_llm_client,
    is_context_length_error,
)
from apps.core.llm_bridge import KitClient, opaque_state, to_kit_messages
from apps.core.llm_testservers import MockServer, dead_url, reply
from apps.core.models import LLMUsageDaily

TOOLS = [{"type": "function", "function": {
    "name": "search", "description": "Search the corpus.",
    "parameters": {"type": "object", "properties": {"q": {"type": "string"}},
                   "required": ["q"]}}}]


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setenv("MOCK_LLM_KEY", "mock-key-value")
    llm_servers.reset()
    llm._breakers.clear()
    yield
    llm_servers.reset()
    llm._breakers.clear()


def _servers(*entries):
    table = {"local": {"name": "local", "synthesized": True,
                       "location_stated": False}}
    for entry in entries:
        table[entry["name"]] = entry
    return table


def routed(srv, name="remote", **settings):
    return override_settings(
        LLM_SERVERS=_servers(srv.server_entry(name)), LLM_ALLOW_CLOUD=True,
        LLM_ROUTES={"chat": name}, LLM_REASONING="medium", **settings)


# --------------------------------------------------------------------------- #
# The default configuration is today's client
# --------------------------------------------------------------------------- #


def test_default_config_builds_todays_client():
    with override_settings(LLM_SERVERS={}, LLM_ROUTES={}, LLM_FALLBACK=[],
                           LLM_BASE_URL="http://h:1/v1", LLM_MODEL="qwen"):
        client = build_llm_client(component="papers")
    assert type(client) is LLMClient
    assert client.config.base_url == "http://h:1/v1"
    assert client.config.model == "qwen"
    assert client.server == "local" and client.component == "papers"


def test_explicit_settings_or_transport_keep_the_old_path():
    class Fake:
        def create(self, **kwargs):
            raise AssertionError("not called")

    client = build_llm_client(completions=Fake(), component="x")
    assert type(client) is LLMClient and client.server == ""


def test_an_openai_compatible_server_keeps_llmclient():
    with MockServer("openai_compatible") as srv, routed(srv, "gpu"):
        client = build_llm_client(component="chat")
        assert type(client) is LLMClient
        assert client.config.base_url == srv.base_url
        assert client.server == "gpu"
        srv.replies.append(reply("hello"))
        out = client.complete("hi")
    assert out.content == "hello" and out.server == "gpu"


# --------------------------------------------------------------------------- #
# Anthropic and Gemini through the bridge
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["anthropic", "gemini", "ollama"])
@pytest.mark.parametrize("stream", [False, True])
def test_tool_call_round_trip(kind, stream):
    with MockServer(kind) as srv, routed(srv, "kit"):
        srv.replies.append(reply(thinking="Let me search.", calls=[
            ("search", {"q": "mycorrhiza"})], signature="sig-XYZ/+=="))
        srv.replies.append(reply("Found three papers."))
        client = build_llm_client(component="chat")
        assert isinstance(client, KitClient)
        deltas = []
        call = client.complete_stream if stream else client.complete
        extra = {"on_delta": lambda k, t: deltas.append((k, t))} if stream else {}
        messages = [{"role": "system", "content": "Be brief."},
                    {"role": "user", "content": "Find mycorrhiza papers."}]
        first = call(messages, tools=TOOLS, tool_choice="auto", **extra)
        assert [c.name for c in first.tool_calls] == ["search"]
        assert json.loads(first.tool_calls[0].arguments) == {"q": "mycorrhiza"}
        assert first.server == "kit"
        if stream:
            assert ("thinking", "Let me search.") in deltas
        if kind != "ollama":
            assert first.opaque and first.opaque["kind"] == kind
        messages += [
            {"role": "assistant", "content": first.content or None,
             "tool_calls": [c.as_dict() for c in first.tool_calls],
             "opaque": first.opaque},
            {"role": "tool", "tool_call_id": first.tool_calls[0].id,
             "content": "3 results"},
        ]
        second = call(messages, tools=TOOLS, **extra)
        assert second.content == "Found three papers."
        assert not second.tool_calls
        sent = json.dumps(srv.requests[1])
    # The tool result went back, attached to its call.
    assert "3 results" in sent
    # System text was lifted out of the message list for the hosted kinds.
    if kind == "anthropic":
        body = srv.requests[1]
        assert body["system"] == "Be brief."
        assert all(m["role"] != "system" for m in body["messages"])
        assistant = body["messages"][1]["content"]
        # The thinking block comes back first and byte-identical.
        assert assistant[0] == {"type": "thinking", "thinking": "Let me search.",
                                "signature": "sig-XYZ/+=="}
        assert assistant[1]["type"] == "tool_use"
        assert body["messages"][2]["content"][0]["type"] == "tool_result"
    if kind == "gemini":
        body = srv.requests[1]
        model_turn = body["contents"][1]
        calls = [p for p in model_turn["parts"] if "functionCall" in p]
        assert len(calls) == 1  # carried once, not duplicated
        import base64

        assert base64.b64decode(calls[0]["thoughtSignature"]) == b"sig-XYZ/+=="
        response = body["contents"][2]["parts"][0]["functionResponse"]
        assert response["name"] == "search"
        assert body["systemInstruction"]["parts"][0]["text"] == "Be brief."
    # Every call is in the ledger under the server that answered.
    row = LLMUsageDaily.objects.get(component="chat", server="kit")
    assert row.calls == 2 and row.failures == 0
    assert row.prompt_tokens > 0 and row.completion_tokens > 0


@pytest.mark.django_db
def test_streamed_text_arrives_as_deltas_and_stop_cancels():
    with MockServer("anthropic") as srv, routed(srv):
        srv.replies.append(reply("one two three"))
        client = build_llm_client(component="chat")
        pieces = []
        out = client.complete_stream("count", on_delta=lambda k, t: pieces.append(t))
        assert "".join(pieces) == "one two three" == out.content
        srv.replies.append(reply("never shown in full"))
        out = client.complete_stream("again", on_delta=lambda k, t: None,
                                     should_stop=lambda: True)
        assert out.finish_reason == "cancelled"


def test_opaque_state_is_byte_identical_and_kind_scoped():
    blocks = [{"type": "thinking", "thinking": "t", "signature": "ÅßÇ+/=="}]
    opaque = json.loads(json.dumps({"kind": "anthropic", "blocks": blocks}))
    message = {"role": "assistant", "content": "", "opaque": opaque,
               "tool_calls": [{"id": "c", "type": "function",
                               "function": {"name": "f", "arguments": "{}"}}]}
    same = to_kit_messages([message], "anthropic")[0]
    assert same.thinking_raw == blocks
    other = to_kit_messages([message], "gemini")[0]
    assert other.thinking_raw is None
    assert opaque_state("anthropic", {"content": blocks}) == opaque


@pytest.mark.django_db
def test_usage_counts_cached_input_once():
    with MockServer("anthropic") as srv, routed(srv):
        srv.replies.append(reply("x"))
        out = build_llm_client(component="chat").complete("hi", reasoning="none")
    # input 30 + cache read 5, reported additively by Anthropic.
    assert out.usage["prompt_tokens"] == 35
    assert out.usage["completion_tokens"] == 7
    assert out.usage["cached_tokens"] == 5


@pytest.mark.django_db
def test_a_context_overflow_is_named():
    with MockServer("anthropic") as srv, routed(srv):
        srv.errors.append((400, {"type": "error", "error": {
            "type": "invalid_request_error",
            "message": "prompt is too long: 250000 tokens > 200000 maximum"}}))
        with pytest.raises(LLMContextLengthError) as exc:
            build_llm_client(component="chat").complete("long")
    assert is_context_length_error(exc.value)
    assert LLMUsageDaily.objects.get(component="chat", server="remote").failures == 1


def test_openai_context_errors_are_recognised():
    class BadRequest(Exception):
        status_code = 400

    assert is_context_length_error(BadRequest(
        "This model's maximum context length is 32768 tokens"))
    assert not is_context_length_error(BadRequest("unknown parameter"))


def test_a_cloud_route_is_never_built_while_cloud_is_off():
    with MockServer("anthropic") as srv:
        with override_settings(LLM_SERVERS=_servers(srv.server_entry("claude")),
                               LLM_ROUTES={"chat": "claude"},
                               LLM_ALLOW_CLOUD=False, LLM_FALLBACK=[]):
            client = build_llm_client(component="chat")
    assert type(client) is LLMClient and client.server == "local"


# --------------------------------------------------------------------------- #
# Fallback
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_a_down_server_falls_back_only_as_listed_and_the_ledger_names_it():
    with MockServer("openai_compatible") as backup:
        backup.replies.append(reply("from the backup"))
        entry = backup.server_entry("backup")
        dead = dead_url() + "/v1"
        with override_settings(LLM_SERVERS=_servers(entry), LLM_ROUTES={},
                               LLM_BASE_URL=dead, LLM_MODEL="qwen",
                               LLM_FALLBACK=["backup"]):
            client = build_llm_client(component="papers")
            assert isinstance(client, FallbackClient)
            out = client.complete("hi", model="qwen")
        assert out.content == "from the backup" and out.server == "backup"
        # The caller's model is for the routed server, not the fallback.
        assert backup.requests[0]["model"] == backup.model
        rows = {r.server: r for r in LLMUsageDaily.objects.filter(component="papers")}
        assert rows["local"].failures == 1 and rows["backup"].calls == 1
        assert rows["backup"].failures == 0

        # Not listed: no fallback, the failure is raised.
        with override_settings(LLM_SERVERS=_servers(entry), LLM_ROUTES={},
                               LLM_BASE_URL=dead, LLM_MODEL="qwen",
                               LLM_FALLBACK=[]):
            client = build_llm_client(component="papers")
            assert type(client) is LLMClient
            with pytest.raises(Exception) as exc:
                client.complete("hi")
            assert llm.is_unavailable_error(exc.value)


def test_a_local_server_never_falls_back_to_cloud_while_cloud_is_off():
    with MockServer("anthropic") as claude:
        with override_settings(LLM_SERVERS=_servers(claude.server_entry("claude")),
                               LLM_ROUTES={}, LLM_BASE_URL=dead_url() + "/v1",
                               LLM_MODEL="qwen", LLM_FALLBACK=["claude"],
                               LLM_ALLOW_CLOUD=False):
            client = build_llm_client(component="papers")
            assert type(client) is LLMClient
            with pytest.raises(Exception) as exc:  # noqa: B017 - SDK's own class
                client.complete("hi")
            assert llm.is_unavailable_error(exc.value)
    assert claude.requests == []


@pytest.mark.django_db
def test_an_open_circuit_skips_the_server():
    with MockServer("openai_compatible") as flaky, \
            MockServer("openai_compatible") as backup:
        flaky.fail_chat = 99
        entries = [flaky.server_entry("flaky"), backup.server_entry("backup")]
        with override_settings(LLM_SERVERS=_servers(*entries),
                               LLM_ROUTES={"x": "flaky"},
                               LLM_FALLBACK=["backup"]):
            client = build_llm_client(component="x")
            for _ in range(5):
                assert client.complete("hi").server == "backup"
    # Three failures open the circuit; the last two calls never reached it.
    assert len(flaky.requests) == 3
    assert len(backup.requests) == 5


@pytest.mark.django_db
def test_a_rejected_request_is_not_retried_elsewhere():
    with MockServer("anthropic") as claude, MockServer("openai_compatible") as backup:
        claude.errors.append((400, {"type": "error", "error": {
            "type": "invalid_request_error", "message": "bad schema"}}))
        entries = [claude.server_entry("claude"), backup.server_entry("backup")]
        with override_settings(LLM_SERVERS=_servers(*entries), LLM_ALLOW_CLOUD=True,
                               LLM_ROUTES={"x": "claude"}, LLM_FALLBACK=["backup"]):
            with pytest.raises(llm.LLMRequestError):
                build_llm_client(component="x").complete("hi")
    assert backup.requests == []


@pytest.mark.django_db
def test_ledger_rows_are_per_server():
    from apps.core import llm_usage

    day = date(2026, 11, 9)
    llm_usage.record("agent", ok=True, usage={"prompt_tokens": 3}, day=day)
    llm_usage.record("agent", ok=True, usage={"prompt_tokens": 5}, day=day,
                     server="claude")
    llm_usage.record("agent", ok=False, day=day, server="claude")
    rows = {r.server: r for r in LLMUsageDaily.objects.filter(day=day)}
    assert rows["local"].prompt_tokens == 3 and rows["local"].calls == 1
    assert rows["claude"].calls == 2 and rows["claude"].failures == 1
