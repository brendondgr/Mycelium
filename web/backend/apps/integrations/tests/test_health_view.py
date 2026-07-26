"""`GET /api/integrations/discord/health?lab=` — why nothing is arriving.

A lab lead asking "why is nobody getting anything?" needs one answer that names the
cause, since it could be the guild, a channel, the add-on or one person's settings.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts.models import Lab, LabMembership
from apps.integrations.models import DiscordGuildLink, DiscordIdentity

from .base import clear_discord_cache, discord_test_settings

URL = "/api/integrations/discord/health"


@pytest.fixture(autouse=True)
def _settings():
    with discord_test_settings:
        clear_discord_cache()
        yield
        clear_discord_cache()


@pytest.fixture
def client():
    return APIClient()


def _lab_with_manager():
    lab = Lab.objects.create(name="Neuro", slug="neuro")
    owner = User.objects.create_user("owner")
    LabMembership.objects.create(user=owner, lab=lab, role=LabMembership.Role.OWNER)
    return lab, owner


@pytest.mark.django_db
def test_a_non_manager_is_refused(client) -> None:
    lab, _owner = _lab_with_manager()
    member = User.objects.create_user("member")
    LabMembership.objects.create(user=member, lab=lab, role=LabMembership.Role.MEMBER)
    client.force_authenticate(member)

    assert client.get(f"{URL}?lab=neuro").status_code == 403


@pytest.mark.django_db
def test_an_unlinked_lab_renders_an_empty_state_not_an_error(client) -> None:
    """A lab that never connected Discord should read as 'not set up', not broken."""
    _lab, owner = _lab_with_manager()
    client.force_authenticate(owner)

    response = client.get(f"{URL}?lab=neuro")

    assert response.status_code == 200
    assert response.data["guild"]["state"] is None
    assert response.data["channels"]["updates"]["bound"] is False


@pytest.mark.django_db
def test_it_names_which_channel_is_unreachable(client) -> None:
    lab, owner = _lab_with_manager()
    DiscordGuildLink.objects.create(
        lab=lab,
        guild_id="g1",
        state=DiscordGuildLink.State.ACTIVE,
        updates_channel_id="c-updates",
        updates_channel_ok=False,
        announcement_channel_id="c-deadlines",
        announcement_channel_ok=True,
    )
    client.force_authenticate(owner)

    channels = client.get(f"{URL}?lab=neuro").data["channels"]

    assert channels["updates"]["ok"] is False
    assert channels["announcements"]["ok"] is True


@pytest.mark.django_db
def test_the_roster_says_who_is_reachable_and_who_is_not(client) -> None:
    lab, owner = _lab_with_manager()
    blocked = User.objects.create_user("blocked")
    never = User.objects.create_user("never")
    LabMembership.objects.create(user=blocked, lab=lab, role=LabMembership.Role.MEMBER)
    LabMembership.objects.create(user=never, lab=lab, role=LabMembership.Role.MEMBER)
    DiscordIdentity.objects.create(
        user=blocked,
        discord_user_id="1",
        state=DiscordIdentity.State.ACTIVE,
        link_method=DiscordIdentity.LinkMethod.OAUTH,
        dm_ok=False,
    )
    client.force_authenticate(owner)

    members = {m["username"]: m for m in client.get(f"{URL}?lab=neuro").data["members"]}

    assert members["blocked"]["linked"] is True
    assert members["blocked"]["dm_ok"] is False  # connected, but DMs closed
    assert members["never"]["linked"] is False  # never connected at all
    assert members["never"]["dm_ok"] is None  # distinct from "blocked"


@pytest.mark.django_db
def test_a_lapsed_addon_is_reported_as_its_own_cause(client) -> None:
    """Distinct from a broken channel: nothing is wrong, the plan just lapsed."""
    lab, owner = _lab_with_manager()
    DiscordGuildLink.objects.create(
        lab=lab, guild_id="g1", state=DiscordGuildLink.State.ACTIVE, addon_ok=False
    )
    client.force_authenticate(owner)

    assert client.get(f"{URL}?lab=neuro").data["addon"]["active"] is False
