"""R4 — channel picker, channel-scoped preflight, and DST-correct firing.

Backend-verifiable parts of R4. The gateway ``/mylo setup`` channel option is a thin
caller of the linking layer over these functions and is a manual smoke.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from apps.accounts.models import Lab, LabMembership
from apps.integrations.services import discord_api, resolve
from apps.integrations.services.discord_api import RawResponse
from apps.integrations.testing import bind
from django.contrib.auth.models import User

from tools.delivery.models import Notification, ReminderFire, SavedOpportunity
from tools.delivery.reminders import create_subscription
from tools.delivery.reminders_discord import (
    list_postable_channels,
    preflight_channel,
)
from tools.delivery.reminders_tick import run_tick
from tools.retrieval.models import ContentDeadline, ContentItem

_Kind = SavedOpportunity.DeadlineKind
_Area = SavedOpportunity.Area


class _Transport:
    def __init__(self):
        self.calls: list[dict] = []
        self.channels = RawResponse(
            200,
            {
                "_list": [
                    {"id": "100", "name": "general", "type": 0},
                    {"id": "200", "name": "voice", "type": 2},
                    {"id": "300", "name": "category", "type": 4},
                    {"id": "400", "name": "announce", "type": 5},
                    {"id": "500", "name": "forum", "type": 15},
                ]
            },
        )
        self.message = RawResponse(200, {"id": "msg-1"})

    def __call__(self, method, path, *, auth=None, json_body=None, **kwargs):
        self.calls.append({"method": method, "path": path, "json_body": json_body})
        if path.endswith("/channels") and method == "GET":
            return self.channels
        if path.endswith("/messages"):
            return self.message
        return RawResponse(404, {})


@pytest.fixture
def transport(monkeypatch, settings):
    settings.DISCORD_BOT_TOKEN = "test-token"
    stub = _Transport()
    monkeypatch.setattr(discord_api, "_request", stub)
    return stub


# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_lab_has_timezone_defaults() -> None:
    lab = Lab.objects.create(name="Lab", slug="lab")
    assert lab.timezone == "America/New_York"
    assert lab.send_hour_local == 9


@pytest.mark.django_db
def test_guild_link_channel_fields_default_blank() -> None:
    lab = Lab.objects.create(name="Lab", slug="lab")
    binding = bind(lab=lab, state="pending_setup", guild_id="g1")
    assert resolve.route_channel(binding, "deadlines") == ""
    assert resolve.get_announcement_channel_for_lab(lab) == ""


# --------------------------------------------------------------------------- #
# Channel picker + preflight
# --------------------------------------------------------------------------- #


def test_list_postable_channels_filters_to_text_and_announcement(transport) -> None:
    channels = list_postable_channels("g1")
    assert [c["id"] for c in channels] == ["100", "400"]  # text + announcement only
    assert {c["type"] for c in channels} == {0, 5}


def test_preflight_channel_posts_a_confirmation_and_succeeds(transport) -> None:
    outcome = preflight_channel("100")
    assert outcome.ok
    # The proof is a real posted message, with the parse: [] guarantee.
    posts = [c for c in transport.calls if c["path"].endswith("/messages")]
    assert posts[0]["json_body"]["allowed_mentions"] == {"parse": []}


def test_preflight_channel_refused_when_send_denied(transport) -> None:
    transport.message = RawResponse(403, {"code": 50013})  # Missing Permissions
    outcome = preflight_channel("100")
    assert not outcome.ok
    assert outcome.unreachable
    # A real Discord 403 is NOT a server-side config gap: keep the two apart so the
    # caller can word the message correctly (overwrite vs. "not set up server-side").
    assert not outcome.not_configured
    assert outcome.error_code == 50013


def test_preflight_channel_missing_access_surfaces_50001(transport) -> None:
    transport.message = RawResponse(403, {"code": 50001})  # Missing Access
    outcome = preflight_channel("100")
    assert not outcome.ok
    assert outcome.unreachable
    assert not outcome.not_configured
    # 50001 means "not in the server / can't see it" — distinct from an overwrite.
    assert outcome.error_code == 50001


def test_preflight_channel_no_bot_token_is_unreachable(settings) -> None:
    settings.DISCORD_BOT_TOKEN = ""
    outcome = preflight_channel("100")
    assert not outcome.ok
    # No token → we never contacted Discord. This must be flagged distinctly so the
    # `/setup` handler never blames the channel's permissions for a server-side gap.
    assert outcome.not_configured
    assert outcome.error_code is None


# --------------------------------------------------------------------------- #
# resolve channel binding
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_set_and_get_announcement_channel() -> None:
    lab = Lab.objects.create(name="Lab", slug="lab")
    binding = bind(lab=lab, state="pending_setup", guild_id="g1")
    when = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)
    resolve.set_route(binding, "deadlines", "chan-42", verified_at=when)

    assert resolve.get_announcement_channel_for_lab(lab) == "chan-42"
    assert resolve.get_route(binding, "deadlines").verified_at == when


# --------------------------------------------------------------------------- #
# DST-correct firing
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_reminder_fires_correctly_across_dst_boundary() -> None:
    lab = Lab.objects.create(name="Lab", slug="lab", timezone="America/New_York")
    LabMembership.objects.create(user=User.objects.create_user("m"), lab=lab)
    item = ContentItem.objects.create(
        type=ContentItem.Type.GRANT, source="legacy", external_id="g-dst"
    )
    ContentDeadline.objects.create(
        content=item,
        kind=_Kind.APPLICATION,
        due_date=date(2026, 11, 8),
        confidence=ContentDeadline.Confidence.CONFIRMED,
    )
    create_subscription(
        target_lab=lab,
        content=item,
        deadline_kind=_Kind.APPLICATION,
        area=_Area.GRANT,
        title="Grant",
        due_date=date(2026, 11, 8),
        offsets=[(1, "week")],
        today=date(2026, 11, 1),
    )

    # 04:30 UTC on 2026-11-01 is 00:30 EDT (still EDT until 02:00) → local date is
    # Nov 1, not Oct 31. A fixed-EST calc would put it a day earlier and read 8 days.
    now = datetime(2026, 11, 1, 4, 30, tzinfo=UTC)
    result = run_tick(now=now)

    assert result.fired == 1
    fire = ReminderFire.objects.get()
    assert fire.days_remaining == 7  # computed in America/New_York, DST-correct
    assert "7 days left" in Notification.objects.get().body
