"""R5 — lab reminders: authorization, mention resolution, channel override, send.

Discord transport mocked. Live channel posting is a manual smoke.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.contrib.auth.models import User

from apps.accounts.models import Lab, LabMembership
from apps.content.models import (
    ContentDeadline,
    ContentItem,
    ReminderFire,
    SavedOpportunity,
)
from apps.content.reminders import ReminderError, create_subscription
from apps.content.reminders_discord import send_lab_channel
from apps.content.reminders_tick import run_tick
from apps.content.tests.entitle import entitle_lab, paid_plan
from apps.integrations.models import DiscordGuildLink, DiscordIdentity
from apps.integrations.services import discord_api, outbox
from apps.integrations.services.discord_api import RawResponse

TODAY = date(2026, 7, 16)
_Kind = SavedOpportunity.DeadlineKind
_Area = SavedOpportunity.Area


class _Transport:
    def __init__(self):
        self.calls: list[dict] = []
        self.message = RawResponse(200, {"id": "msg-1"})
        self.dm = RawResponse(200, {"id": "dm-chan"})

    def __call__(self, method, path, *, auth=None, json_body=None, **kwargs):
        self.calls.append({"method": method, "path": path, "json_body": json_body})
        if path == "/users/@me/channels":
            return self.dm
        if path.endswith("/messages"):
            return self.message
        return RawResponse(404, {})

    def posts(self) -> list[dict]:
        return [c for c in self.calls if c["path"].endswith("/messages")]


@pytest.fixture
def transport(monkeypatch, settings):
    settings.DISCORD_BOT_TOKEN = "test-token"
    stub = _Transport()
    monkeypatch.setattr(discord_api, "_request", stub)
    return stub


def _lab(*, channel="default-chan"):
    """A lab on a paid plan with a live, claimed Discord server.

    Both are part of the fixture, not the subject: lab reminders are gated on the
    lab's plan and guild link at create *and* send time, and these tests are about
    mention resolution and channel routing. ``test_reminder_access`` owns the gate.
    """
    lab = Lab.objects.create(name="Lab", slug="lab")
    DiscordGuildLink.objects.create(
        lab=lab, guild_id="g1", announcement_channel_id=channel
    )
    return entitle_lab(lab)


def _member(lab, username, *, role=LabMembership.Role.MEMBER, discord_id=None):
    user = User.objects.create_user(username)
    LabMembership.objects.create(user=user, lab=lab, role=role)
    paid_plan(user)
    if discord_id:
        DiscordIdentity.objects.create(
            user=user,
            discord_user_id=discord_id,
            link_method=DiscordIdentity.LinkMethod.OAUTH,
            state=DiscordIdentity.State.ACTIVE,
            dm_ok=True,
        )
    return user


def _lab_sub(lab, *, created_by=None, mentions=(), override="", due=None):
    due = due or TODAY + timedelta(days=7)
    item = ContentItem.objects.create(
        type=ContentItem.Type.GRANT, source="pivot", external_id=f"g-{override}-{due}"
    )
    ContentDeadline.objects.create(
        content=item,
        kind=_Kind.APPLICATION,
        due_date=due,
        confidence=ContentDeadline.Confidence.CONFIRMED,
    )
    return create_subscription(
        target_lab=lab,
        content=item,
        deadline_kind=_Kind.APPLICATION,
        area=_Area.GRANT,
        title="Lab grant",
        due_date=due,
        offsets=[(1, "week")],
        mentions=list(mentions),
        channel_id_override=override,
        created_by=created_by,
        today=TODAY,
    )


# --------------------------------------------------------------------------- #
# Authorization at config time
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_lab_member_cannot_manage_lab_reminders() -> None:
    lab = _lab()
    member = _member(lab, "plain-member")  # MEMBER, not a manager
    with pytest.raises(ReminderError):
        _lab_sub(lab, created_by=member)


@pytest.mark.django_db
def test_lab_manager_can_create_lab_reminder() -> None:
    lab = _lab()
    owner = _member(lab, "owner", role=LabMembership.Role.OWNER)
    sub = _lab_sub(lab, created_by=owner)
    assert sub.pk is not None


@pytest.mark.django_db
def test_lab_pi_lead_can_create_lab_reminder() -> None:
    # A PI (is_lead) is not owner/admin but may still create lab reminders.
    lab = _lab()
    pi = User.objects.create_user("pi")
    LabMembership.objects.create(
        user=pi, lab=lab, role=LabMembership.Role.MEMBER, is_lead=True
    )
    sub = _lab_sub(lab, created_by=pi)
    assert sub.pk is not None


@pytest.mark.django_db
def test_mention_target_must_be_lab_member() -> None:
    lab = _lab()
    owner = _member(lab, "owner", role=LabMembership.Role.OWNER)
    outsider = User.objects.create_user("outsider")  # no membership
    with pytest.raises(ReminderError):
        _lab_sub(lab, created_by=owner, mentions=[outsider])


# --------------------------------------------------------------------------- #
# Mention resolution + send
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_lab_reminder_pings_linked_members(transport) -> None:
    lab = _lab()
    linked = _member(lab, "linked", discord_id="777")
    sub = _lab_sub(lab, mentions=[linked])
    outcome = send_lab_channel(sub, sub.title, "Application due Jul 23 — 7 days left")
    assert outcome.ok and outcome.queued
    outbox.drain()
    post = transport.posts()[0]
    assert post["path"] == "/channels/default-chan/messages"
    assert "<@777>" in post["json_body"]["content"]
    assert post["json_body"]["allowed_mentions"] == {"parse": [], "users": ["777"]}


@pytest.mark.django_db
def test_unlinked_mention_target_renders_plain_text_not_dropped(transport) -> None:
    lab = _lab()
    unlinked = _member(lab, "unlinked-person")  # lab member, no Discord identity
    sub = _lab_sub(lab, mentions=[unlinked])
    outcome = send_lab_channel(sub, sub.title, "body")
    assert outcome.ok and outcome.queued
    outbox.drain()
    post = transport.posts()[0]
    # Named as plain text (escaped), no ping, and no explicit user id.
    assert "unlinked-person" in post["json_body"]["content"]
    assert "<@" not in post["json_body"]["content"]
    assert post["json_body"]["allowed_mentions"] == {"parse": []}
    assert outcome.has_unlinked is True


@pytest.mark.django_db
def test_scraped_everyone_title_produces_no_ping_in_lab_channel(transport) -> None:
    lab = _lab()
    sub = _lab_sub(lab)
    sub.title = "@everyone urgent grant"
    outcome = send_lab_channel(sub, sub.title, "body")
    assert outcome.ok and outcome.queued
    outbox.drain()
    body = transport.posts()[0]["json_body"]
    assert body["allowed_mentions"] == {"parse": []}
    assert "@​everyone" in body["embeds"][0]["title"]  # escaped in the embed


# --------------------------------------------------------------------------- #
# Channel override
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_per_reminder_override_beats_lab_default(transport) -> None:
    lab = _lab(channel="default-chan")
    sub = _lab_sub(lab, override="override-chan")
    send_lab_channel(sub, sub.title, "body")
    outbox.drain()
    assert transport.posts()[0]["path"] == "/channels/override-chan/messages"


@pytest.mark.django_db
def test_blank_override_falls_back_to_lab_default(transport) -> None:
    lab = _lab(channel="default-chan")
    sub = _lab_sub(lab, override="")
    send_lab_channel(sub, sub.title, "body")
    outbox.drain()
    assert transport.posts()[0]["path"] == "/channels/default-chan/messages"


@pytest.mark.django_db
def test_lab_reminder_with_no_channel_falls_back_to_in_app(transport) -> None:
    lab = _lab(channel="")  # nothing bound, no override
    _member(lab, "m1")
    _lab_sub(lab)
    result = run_tick(TODAY)
    outbox.drain()
    assert result.notifications == 1  # in-app to the member
    fire = ReminderFire.objects.get()
    assert fire.channel == ReminderFire.Channel.IN_APP
    assert transport.posts() == []  # nothing posted to any channel


# --------------------------------------------------------------------------- #
# Tick wiring + the personal-vs-lab boundary
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_tick_posts_lab_reminder_and_records_channel(transport) -> None:
    lab = _lab()
    _member(lab, "member-a", discord_id="111")
    sub = _lab_sub(lab, mentions=[User.objects.get(username="member-a")])
    result = run_tick(TODAY)
    assert result.notifications >= 1  # in-app to lab members
    fire = ReminderFire.objects.get(state=ReminderFire.Result.QUEUED)
    assert fire.channel == ReminderFire.Channel.DISCORD_CHANNEL
    assert fire.outbox_key
    outbox.drain()
    assert transport.posts()[0]["path"] == "/channels/default-chan/messages"
    sub.refresh_from_db()
    assert sub.has_unlinked_targets is False


@pytest.mark.django_db
def test_personal_reminder_never_appears_in_lab_channel(transport) -> None:
    # A personal reminder for a user who also has a lab must go to DM only.
    lab = _lab()
    user = _member(lab, "solo", discord_id="222")
    item = ContentItem.objects.create(
        type=ContentItem.Type.GRANT, source="pivot", external_id="g-personal"
    )
    ContentDeadline.objects.create(
        content=item,
        kind=_Kind.APPLICATION,
        due_date=TODAY + timedelta(days=7),
        confidence=ContentDeadline.Confidence.CONFIRMED,
    )
    create_subscription(
        target_user=user,
        content=item,
        deadline_kind=_Kind.APPLICATION,
        area=_Area.GRANT,
        title="Personal grant",
        due_date=TODAY + timedelta(days=7),
        offsets=[(1, "week")],
        today=TODAY,
    )
    run_tick(TODAY)
    fire = ReminderFire.objects.get()
    assert fire.channel == ReminderFire.Channel.DISCORD_DM  # not a channel post
    # The only channel touched was the user's DM channel, never the lab's.
    posted_paths = [c["path"] for c in transport.posts()]
    assert "/channels/default-chan/messages" not in posted_paths
