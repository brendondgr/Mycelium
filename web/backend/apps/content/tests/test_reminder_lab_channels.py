"""The lab reminder channel-picker endpoint (GET /api/reminders/lab-channels/).

Manager-gated; reuses ``reminders_discord.list_postable_channels`` + the guild
link's announcement channel as the labelled default. Degrades to an empty list
(never 500) when the guild is unlinked or Discord is unreachable.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts.models import Lab, LabMembership
from apps.integrations.services import discord_api
from apps.integrations.services.discord_api import RawResponse
from apps.integrations.testing import bind


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture
def transport(monkeypatch, settings):
    """Stub the Discord REST transport with a fixed channel roster."""
    settings.DISCORD_BOT_TOKEN = "test-token"

    def _stub(method, path, *, auth=None, json_body=None, **kwargs):
        if path.endswith("/channels") and method == "GET":
            return RawResponse(
                200,
                {
                    "_list": [
                        {"id": "100", "name": "general", "type": 0},
                        {"id": "200", "name": "voice", "type": 2},
                        {"id": "400", "name": "announce", "type": 5},
                    ]
                },
            )
        return RawResponse(404, {})

    monkeypatch.setattr(discord_api, "_request", _stub)
    return _stub


def _manager(lab, username="pi") -> User:
    user = User.objects.create_user(username)
    LabMembership.objects.create(
        user=user, lab=lab, role=LabMembership.Role.OWNER
    )
    return user


@pytest.mark.django_db
def test_lists_postable_channels_and_labels_default(client, transport) -> None:
    lab = Lab.objects.create(name="Lab", slug="lab")
    bind(lab=lab, state="pending_setup", guild_id="g1", deadlines="400")
    user = _manager(lab)
    client.force_authenticate(user)

    resp = client.get("/api/reminders/lab-channels/", {"lab": "lab"})
    assert resp.status_code == 200
    # Only text (0) + announcement (5) — the voice channel is filtered out.
    assert [c["id"] for c in resp.data["channels"]] == ["100", "400"]
    assert resp.data["default_channel_id"] == "400"
    assert resp.data["default_channel_name"] == "announce"


@pytest.mark.django_db
def test_unlinked_guild_returns_empty_not_error(client) -> None:
    lab = Lab.objects.create(name="Lab", slug="lab")
    user = _manager(lab)
    client.force_authenticate(user)

    resp = client.get("/api/reminders/lab-channels/", {"lab": "lab"})
    assert resp.status_code == 200
    assert resp.data["channels"] == []
    assert resp.data["default_channel_id"] == ""


@pytest.mark.django_db
def test_non_manager_is_forbidden(client, transport) -> None:
    lab = Lab.objects.create(name="Lab", slug="lab")
    bind(lab=lab, state="pending_setup", guild_id="g1")
    member = User.objects.create_user("member")
    LabMembership.objects.create(
        user=member, lab=lab, role=LabMembership.Role.MEMBER
    )
    client.force_authenticate(member)

    resp = client.get("/api/reminders/lab-channels/", {"lab": "lab"})
    assert resp.status_code == 403


@pytest.mark.django_db
def test_unknown_lab_is_404(client) -> None:
    user = User.objects.create_user("u")
    client.force_authenticate(user)
    resp = client.get("/api/reminders/lab-channels/", {"lab": "nope"})
    assert resp.status_code == 404


@pytest.mark.django_db
def test_discord_failure_degrades_to_empty(client, monkeypatch, settings) -> None:
    settings.DISCORD_BOT_TOKEN = "test-token"
    lab = Lab.objects.create(name="Lab", slug="lab")
    bind(lab=lab, state="pending_setup", guild_id="g1", deadlines="400")
    user = _manager(lab)
    client.force_authenticate(user)

    def _boom(method, path, **kwargs):
        raise RuntimeError("discord down")

    monkeypatch.setattr(discord_api, "_request", _boom)
    resp = client.get("/api/reminders/lab-channels/", {"lab": "lab"})
    assert resp.status_code == 200
    assert resp.data["channels"] == []
    # The default id is still returned from the DB even when the roster call fails.
    assert resp.data["default_channel_id"] == "400"
