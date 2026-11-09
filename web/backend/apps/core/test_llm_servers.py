"""The server registry: routing, discovery, health and the discovery cache.

Every server here is a loopback mock (``apps.core.llm_testservers``); no key and
no network are needed.
"""

import time

import pytest
from django.test import override_settings

from apps.core import llm_servers
from apps.core.llm_testservers import KINDS, MockServer, dead_url


@pytest.fixture(autouse=True)
def _fresh_registry(monkeypatch):
    monkeypatch.setenv("MOCK_LLM_KEY", "mock-key-value")
    llm_servers.reset()
    yield
    llm_servers.reset()


def _servers(*entries, local=None):
    table = {"local": local or {"name": "local", "synthesized": True,
                                "location_stated": False}}
    for entry in entries:
        table[entry["name"]] = entry
    return table


def test_default_install_routes_everything_to_the_env_endpoint():
    with override_settings(LLM_SERVERS={}, LLM_ROUTES={},
                           LLM_BASE_URL="http://host.docker.internal:4000/v1",
                           LLM_MODEL="qwen"):
        route = llm_servers.resolve("papers")
    assert (route.server, route.model, route.location) == ("local", "qwen", "local")
    assert route.base_url == "http://host.docker.internal:4000/v1"
    assert route.problem == ""
    assert route.public() == {"name": "qwen", "label": "Local model",
                              "location": "local", "server": "local"}


def test_routes_pick_server_and_model_and_dotted_parents():
    with MockServer("anthropic") as claude:
        entry = claude.server_entry("claude")
        with override_settings(
            LLM_SERVERS=_servers(entry), LLM_ALLOW_CLOUD=True,
            LLM_ROUTES={"agent": "claude", "intake": "local:small",
                        "intake.clusters": "claude:claude-big"},
            LLM_MODEL="qwen",
        ):
            assert llm_servers.resolve("agent").server == "claude"
            assert llm_servers.resolve("agent").model == claude.model
            assert llm_servers.resolve("agent").location == "cloud"
            assert llm_servers.resolve("intake.resume").model == "small"
            assert llm_servers.resolve("intake.clusters").model == "claude-big"
            assert llm_servers.resolve("papers").server == "local"
            assert llm_servers.resolve("papers").model == "qwen"


def test_a_cloud_route_is_not_honoured_while_cloud_is_off():
    with MockServer("anthropic") as claude:
        with override_settings(LLM_SERVERS=_servers(claude.server_entry("claude")),
                               LLM_ROUTES={"agent": "claude"},
                               LLM_ALLOW_CLOUD=False, LLM_MODEL="qwen"):
            route = llm_servers.resolve("agent")
    assert route.server == "local" and route.location == "local"
    assert "allow_cloud" in route.problem


def test_unknown_or_disabled_routes_fall_back_to_the_default():
    with MockServer("ollama") as ollama:
        off = ollama.server_entry("box", enabled=False)
        with override_settings(LLM_SERVERS=_servers(off),
                               LLM_ROUTES={"a": "ghost", "b": "box"}):
            assert llm_servers.resolve("a").server == "local"
            assert "no server" in llm_servers.resolve("a").problem
            assert llm_servers.resolve("b").server == "local"
            assert "disabled" in llm_servers.resolve("b").problem


def test_options_lists_models_and_context_windows_for_every_kind():
    servers = [MockServer(kind) for kind in KINDS]
    for srv in servers:
        srv.__enter__()
    try:
        entries = [srv.server_entry(srv.kind) for srv in servers]
        with override_settings(LLM_SERVERS=_servers(*entries), LLM_ALLOW_CLOUD=True,
                               LLM_BASE_URL=dead_url() + "/v1"):
            rows = {row["server"]: row for row in llm_servers.options()}
            for srv in servers:
                row = rows[srv.kind]
                assert row["ok"], (srv.kind, row["error"])
                assert row["location"] == ("cloud" if srv.kind in
                                           ("anthropic", "gemini") else "local")
                model = next(m for m in row["models"] if m["id"] == srv.model)
                assert model["context_window"] == srv.context, srv.kind
                assert llm_servers.context_window(srv.kind) == srv.context
            # The env endpoint is dead: a normal state, reported, not raised.
            assert rows["local"]["ok"] is False and rows["local"]["error"]
            # The key's variable is named nowhere near its value.
            assert "mock-key-value" not in repr(rows)
    finally:
        for srv in servers:
            srv.__exit__(None, None, None)


def test_a_dead_server_fails_fast_and_does_not_slow_the_others():
    with MockServer("openai_compatible") as live:
        dead = live.server_entry("dead", base_url=dead_url() + "/v1",
                                 connect_timeout=1.0)
        with override_settings(LLM_SERVERS=_servers(live.server_entry("live"), dead),
                               LLM_BASE_URL=live.base_url):
            started = time.monotonic()
            rows = {row["server"]: row for row in llm_servers.options()}
            elapsed = time.monotonic() - started
    assert rows["live"]["ok"] and rows["local"]["ok"]
    assert rows["dead"]["ok"] is False
    assert "reach" in rows["dead"]["error"].lower() or rows["dead"]["error"]
    assert elapsed < 1.0 + 2.0


def test_the_cache_is_used_on_the_second_call():
    with MockServer("openai_compatible") as srv:
        with override_settings(LLM_SERVERS=_servers(srv.server_entry("box")),
                               LLM_BASE_URL=dead_url() + "/v1"):
            first = {r["server"]: r for r in llm_servers.options()}
            calls = srv.list_calls
            second = {r["server"]: r for r in llm_servers.options()}
            assert srv.list_calls == calls
            assert first["box"]["cached"] is False and second["box"]["cached"]
            # A dead server's error is cached too (for a shorter time).
            assert second["local"]["cached"] is True
            llm_servers.options(force=True)
            assert srv.list_calls == calls + 1


def test_disabled_and_blocked_cloud_servers_are_listed_but_never_called():
    with MockServer("gemini") as gem, MockServer("ollama") as oll:
        entries = [gem.server_entry("gem"), oll.server_entry("oll", enabled=False)]
        with override_settings(LLM_SERVERS=_servers(*entries), LLM_ALLOW_CLOUD=False,
                               LLM_BASE_URL=dead_url() + "/v1"):
            rows = {row["server"]: row for row in llm_servers.options()}
    assert rows["gem"]["ok"] is False and "allow_cloud" in rows["gem"]["error"]
    assert rows["oll"]["error"] == "disabled"
    assert gem.list_calls == 0 and oll.list_calls == 0


def test_a_stated_context_window_wins_and_unknown_falls_back():
    with MockServer("openai_compatible") as srv:
        entry = srv.server_entry("box", context_window=12345)
        with override_settings(LLM_SERVERS=_servers(entry),
                               LLM_BASE_URL=dead_url() + "/v1"):
            assert llm_servers.context_window("box") == 12345
            assert llm_servers.context_window("local") == 32768


def test_health_names_the_reason():
    with override_settings(LLM_SERVERS={}, LLM_BASE_URL=dead_url() + "/v1"):
        ok, reason = llm_servers.health("local")
        assert ok is False and reason
        assert llm_servers.health("ghost") == (False, "no server named 'ghost'")
