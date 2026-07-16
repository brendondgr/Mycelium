"""R3 — personal reminders → Discord DM (transport mocked).

Patches ``discord_api._request`` so ``create_message`` / ``open_dm_raw`` run their real
body-building logic (letting us assert ``allowed_mentions.parse == []``) while the HTTP
round-trip is faked. Live DM delivery needs a real bot token + a linked test account
and is a manual smoke — see the plan's R3 verification note.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.contrib.auth.models import User

from apps.content.models import (
    ContentDeadline,
    ContentItem,
    Notification,
    ReminderFire,
    SavedOpportunity,
)
from apps.content.reminders import create_subscription
from apps.content.reminders_discord import escape_mentions, send_personal_dm
from apps.content.reminders_tick import run_tick
from apps.integrations.models import DiscordIdentity
from apps.integrations.services import discord_api
from apps.integrations.services.discord_api import RawResponse, create_message

TODAY = date(2026, 7, 16)
_Kind = SavedOpportunity.DeadlineKind
_Area = SavedOpportunity.Area


class _Transport:
    """A fake ``discord_api._request`` recording calls and returning canned rows."""

    def __init__(self):
        self.calls: list[dict] = []
        self.dm = RawResponse(200, {"id": "dm-chan"})
        self.message = RawResponse(200, {"id": "msg-1"})

    def __call__(self, method, path, *, auth=None, json_body=None, **kwargs):
        self.calls.append({"method": method, "path": path, "json_body": json_body})
        if path == "/users/@me/channels":
            return self.dm
        if path.endswith("/messages"):
            return self.message
        return RawResponse(404, {})

    def message_bodies(self) -> list[dict]:
        return [c["json_body"] for c in self.calls if c["path"].endswith("/messages")]


@pytest.fixture
def transport(monkeypatch, settings):
    settings.DISCORD_BOT_TOKEN = "test-token"
    stub = _Transport()
    monkeypatch.setattr(discord_api, "_request", stub)
    return stub


@pytest.fixture
def user(db):
    return User.objects.create_user("dm-user")


def _active_identity(user, *, dm_ok=True, channel="dm-chan"):
    return DiscordIdentity.objects.create(
        user=user,
        discord_user_id="900123",
        link_method=DiscordIdentity.LinkMethod.OAUTH,
        state=DiscordIdentity.State.ACTIVE,
        dm_ok=dm_ok,
        dm_channel_id=channel,
    )


def _personal_sub(user, *, title="Neural grant", due=None):
    due = due or TODAY + timedelta(days=7)
    item = ContentItem.objects.create(
        type=ContentItem.Type.GRANT, source="pivot", external_id="g-dm"
    )
    ContentDeadline.objects.create(
        content=item,
        kind=_Kind.APPLICATION,
        due_date=due,
        confidence=ContentDeadline.Confidence.CONFIRMED,
    )
    return create_subscription(
        target_user=user,
        content=item,
        deadline_kind=_Kind.APPLICATION,
        area=_Area.GRANT,
        title=title,
        due_date=due,
        offsets=[(1, "week")],
        today=TODAY,
    )


# --------------------------------------------------------------------------- #
# allowed_mentions safety
# --------------------------------------------------------------------------- #


def test_allowed_mentions_parse_is_always_empty(transport) -> None:
    create_message("chan", content="hi", allowed_mentions={"users": ["1", "2"]})
    body = transport.message_bodies()[0]
    assert body["allowed_mentions"]["parse"] == []
    assert body["allowed_mentions"]["users"] == ["1", "2"]


def test_create_message_forces_parse_empty_even_with_everyone(transport) -> None:
    create_message("chan", content="@everyone read this")
    body = transport.message_bodies()[0]
    assert body["allowed_mentions"] == {"parse": []}  # no users/roles, no parse cats


def test_escape_mentions_neutralizes_at() -> None:
    assert escape_mentions("@everyone urgent") == "@​everyone urgent"
    assert escape_mentions("plain text") == "plain text"


@pytest.mark.django_db
def test_scraped_title_containing_everyone_produces_no_ping(transport, user) -> None:
    _active_identity(user)
    sub = _personal_sub(user, title="@everyone urgent grant")
    outcome = send_personal_dm(sub, sub.title, "Application due Jul 23 — 7 days left")
    assert outcome.ok
    body = transport.message_bodies()[0]
    assert body["allowed_mentions"] == {"parse": []}
    # The scraped title is escaped in the embed, so it can't render as a mention.
    assert "@​everyone" in body["embeds"][0]["title"]


# --------------------------------------------------------------------------- #
# send_personal_dm outcomes
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_send_personal_dm_success_with_cached_channel(transport, user) -> None:
    _active_identity(user, channel="cached-chan")
    sub = _personal_sub(user)
    outcome = send_personal_dm(sub, sub.title, "body")
    assert outcome.ok
    assert outcome.message_id == "msg-1"
    # Used the cached channel — no open-DM call.
    assert all(c["path"] != "/users/@me/channels" for c in transport.calls)
    assert transport.calls[-1]["path"] == "/channels/cached-chan/messages"


@pytest.mark.django_db
def test_send_personal_dm_opens_dm_when_uncached(transport, user) -> None:
    _active_identity(user, channel="")
    transport.dm = RawResponse(200, {"id": "opened-chan"})
    sub = _personal_sub(user)
    outcome = send_personal_dm(sub, sub.title, "body")
    assert outcome.ok
    assert transport.calls[0]["path"] == "/users/@me/channels"
    assert transport.calls[-1]["path"] == "/channels/opened-chan/messages"
    DiscordIdentity.objects.get(user=user).refresh_from_db()
    assert DiscordIdentity.objects.get(user=user).dm_channel_id == "opened-chan"


@pytest.mark.django_db
def test_send_personal_dm_403_marks_unreachable(transport, user) -> None:
    identity = _active_identity(user, channel="cached-chan")
    transport.message = RawResponse(403, {"code": 50007})
    sub = _personal_sub(user)
    outcome = send_personal_dm(sub, sub.title, "body")
    assert not outcome.ok
    assert outcome.unreachable
    identity.refresh_from_db()
    assert identity.dm_ok is False


@pytest.mark.django_db
def test_send_personal_dm_no_identity_is_unreachable(transport, user) -> None:
    sub = _personal_sub(user)
    outcome = send_personal_dm(sub, sub.title, "body")
    assert not outcome.ok
    assert outcome.unreachable
    assert transport.calls == []  # never hit the network


@pytest.mark.django_db
def test_send_personal_dm_no_bot_token_is_unreachable(user, settings) -> None:
    settings.DISCORD_BOT_TOKEN = ""
    _active_identity(user)
    sub = _personal_sub(user)
    outcome = send_personal_dm(sub, sub.title, "body")
    assert not outcome.ok
    assert outcome.unreachable


# --------------------------------------------------------------------------- #
# Tick wiring
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_tick_dms_personal_reminder_and_records_channel(transport, user) -> None:
    _active_identity(user)
    _personal_sub(user)  # fires today (1-week offset, due in 7 days)
    result = run_tick(TODAY)
    assert result.notifications == 1  # in-app still delivered
    fire = ReminderFire.objects.get(state=ReminderFire.Result.SENT)
    assert fire.channel == ReminderFire.Channel.DISCORD_DM
    assert fire.discord_message_id == "msg-1"
    assert Notification.objects.count() == 1  # the bell copy


@pytest.mark.django_db
def test_tick_dm_failure_still_delivers_in_app(transport, user) -> None:
    _active_identity(user)
    transport.message = RawResponse(500, {})  # Discord 5xx
    _personal_sub(user)
    result = run_tick(TODAY)
    assert result.notifications == 1
    fire = ReminderFire.objects.get()
    assert fire.state == ReminderFire.Result.SENT  # in-app succeeded
    assert fire.channel == ReminderFire.Channel.IN_APP  # DM did not land
    assert Notification.objects.count() == 1
