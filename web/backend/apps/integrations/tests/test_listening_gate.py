"""The `/setup` listening switch's manager gate, and a lead PI's Discord rights.

``mylo.listening._manager_gate`` used to return ``link.lab`` — a field
``DiscordGuildLink`` stopped having when a server became a guild row plus one
binding per lab or department. Every allowed call raised ``AttributeError``.
It now returns the lab the gate itself resolved.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model

from apps.accounts.models import Lab, LabMembership
from apps.integrations.services import gate, resolve
from apps.integrations.testing import bind

from .base import _LOCMEM, clear_discord_cache

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))
from mylo import listening  # noqa: E402

User = get_user_model()
pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clean_cache(settings):
    settings.CACHES = _LOCMEM
    settings.BILLING_ENFORCE_ENTITLEMENTS = False
    clear_discord_cache()
    yield
    clear_discord_cache()


def _member(username: str, lab: Lab, *, snowflake: str, **fields) -> User:
    user = User.objects.create_user(username)
    resolve.bind_identity(user, snowflake, method=resolve.LINK_OAUTH)
    LabMembership.objects.create(user=user, lab=lab, **fields)
    return user


def test_a_manager_gets_the_servers_lab_back() -> None:
    lab = Lab.objects.create(name="Reef", slug="reef")
    _member("pi", lab, snowflake="11", role=LabMembership.Role.OWNER)
    bind(lab=lab, guild_id="g1")

    found, refusal = listening._manager_gate("g1", "11")

    assert refusal is None
    assert found == lab


def test_a_plain_member_is_refused() -> None:
    lab = Lab.objects.create(name="Reef", slug="reef")
    _member("student", lab, snowflake="12", role=LabMembership.Role.MEMBER)
    bind(lab=lab, guild_id="g1")

    found, refusal = listening._manager_gate("g1", "12")

    assert found is None
    assert refusal is not None


def test_an_unconnected_server_is_refused() -> None:
    found, refusal = listening._manager_gate("nowhere", "11")
    assert found is None
    assert refusal[0] == "not_active"


def test_a_lead_pi_may_configure_the_lab_from_discord() -> None:
    """A lead PI holds every right an admin does — the bot agrees with the web."""
    lab = Lab.objects.create(name="Reef", slug="reef")
    _member("pi", lab, snowflake="13", role=LabMembership.Role.MEMBER, is_lead=True)
    bind(lab=lab, guild_id="g1")

    verdict = gate.authorize(discord_user_id="13", action="setup", guild_id="g1")
    assert verdict.ok

    found, refusal = listening._manager_gate("g1", "13")
    assert refusal is None
    assert found == lab
