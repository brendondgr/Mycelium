"""``GET api/admin/llm/servers/``: staff-only, read-only, never leaks a key."""

import pytest
from django.contrib.auth.models import User
from django.test import override_settings
from rest_framework.test import APIClient

from apps.core import llm_servers
from apps.core.llm_testservers import MockServer, dead_url

URL = "/api/admin/llm/servers/"
pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setenv("MOCK_LLM_KEY", "mock-key-value")
    llm_servers.reset()
    yield
    llm_servers.reset()


def _client(staff: bool) -> APIClient:
    user = User.objects.create_user(username=f"u{staff}", password="x",
                                    is_staff=staff)
    c = APIClient()
    c.force_authenticate(user)
    return c


def test_only_staff_may_read_it():
    assert APIClient().get(URL).status_code in (401, 403)
    assert _client(False).get(URL).status_code == 403


def test_lists_servers_routes_and_a_dead_server_is_ok_false():
    with MockServer("anthropic") as claude:
        table = {"local": {"name": "local", "synthesized": True,
                           "location_stated": False},
                 "claude": claude.server_entry("claude")}
        with override_settings(LLM_SERVERS=table, LLM_ALLOW_CLOUD=True,
                               LLM_ROUTES={"agent": "claude"},
                               LLM_BASE_URL=dead_url() + "/v1", LLM_MODEL="qwen",
                               LLM_API_KEY="local-secret-value"):
            response = _client(True).get(URL)
    assert response.status_code == 200
    body = response.json()
    rows = {r["server"]: r for r in body["servers"]}
    assert rows["local"]["ok"] is False and rows["local"]["error"]
    assert rows["claude"]["ok"] is True and rows["claude"]["location"] == "cloud"
    assert rows["claude"]["api_key_env"] == "MOCK_LLM_KEY"
    assert rows["claude"]["has_key"] is True
    assert body["routes"]["agent"]["server"] == "claude"
    assert body["routes"]["*"]["server"] == "local"
    text = response.content.decode()
    assert "mock-key-value" not in text and "local-secret-value" not in text


def test_post_is_refused():
    assert _client(True).post(URL, {}).status_code == 405
