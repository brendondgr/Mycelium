"""Telling someone their Discord message never arrived — once, in the app.

The "don't spam them" half of the retry policy. Five attempts must produce one
notice, and it must reach whoever can actually act on the failure.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from tools.retrieval.models import Notification

from apps.accounts.models import Lab, LabMembership
from apps.integrations.models import (
    DiscordIdentity,
    DiscordOutboxMessage,
)
from apps.integrations.services import discord_api, outbox
from apps.integrations.services.discord_api import RawResponse
from apps.integrations.testing import bind

_Kind = Notification.Kind


class _Transport:
    def __init__(self, status=503, body=None):
        self.status = status
        self.body = body or {}
        self.calls: list[dict] = []

    def __call__(self, method, path, *, auth=None, json_body=None, **kwargs):
        self.calls.append({"path": path})
        if path == "/users/@me/channels":
            return RawResponse(200, {"id": "dm-chan"})
        return RawResponse(self.status, self.body)


@pytest.fixture
def settings_fast(settings):
    settings.DISCORD_BOT_TOKEN = "test-token"
    settings.DISCORD_OUTBOX_MAX_ATTEMPTS = 5
    settings.DISCORD_OUTBOX_RETRY_SECONDS = 300
    return settings


@pytest.fixture
def user(db):
    return User.objects.create_user("dead-user")


@pytest.fixture
def linked(user):
    DiscordIdentity.objects.create(
        user=user,
        discord_user_id="900000000000000003",
        state=DiscordIdentity.State.ACTIVE,
        link_method=DiscordIdentity.LinkMethod.OAUTH,
        dm_channel_id="dm-chan",
        dm_ok=True,
    )
    return user


def _drain_until_settled(monkeypatch, transport, rounds=8):
    monkeypatch.setattr(discord_api, "_request", transport)
    now = timezone.now()
    for i in range(rounds):
        outbox.drain(now=now + timedelta(seconds=301 * i))


@pytest.mark.django_db
def test_five_attempts_produce_one_notification_not_five(
    linked, settings_fast, monkeypatch
) -> None:
    outbox.enqueue_dm(dedupe_key="dm-dead", kind="reminder", user=linked, content="hi")

    _drain_until_settled(monkeypatch, _Transport(503))

    row = DiscordOutboxMessage.objects.get()
    assert row.status == DiscordOutboxMessage.Status.DEAD
    assert row.attempts == 5
    notices = Notification.objects.filter(kind=_Kind.DELIVERY_FAILED)
    assert notices.count() == 1


@pytest.mark.django_db
def test_draining_again_afterwards_does_not_re_notify(
    linked, settings_fast, monkeypatch
) -> None:
    outbox.enqueue_dm(dedupe_key="dm-dead", kind="reminder", user=linked, content="hi")
    _drain_until_settled(monkeypatch, _Transport(503))

    outbox.drain(now=timezone.now() + timedelta(days=3))

    assert Notification.objects.filter(kind=_Kind.DELIVERY_FAILED).count() == 1


@pytest.mark.django_db
def test_a_blocked_dm_tells_the_person_how_to_fix_it(
    linked, settings_fast, monkeypatch
) -> None:
    """Permanent, so it is reported on the first attempt rather than after five."""
    outbox.enqueue_dm(dedupe_key="dm-blocked", kind="reminder", user=linked)
    monkeypatch.setattr(discord_api, "_request", _Transport(403, {"code": 50007}))

    outbox.drain()

    note = Notification.objects.get(kind=_Kind.DELIVERY_FAILED)
    assert note.user == linked
    assert "direct messages are closed" in note.body.lower()
    assert DiscordOutboxMessage.objects.get().attempts == 1  # not five


@pytest.mark.django_db
def test_a_failed_channel_post_tells_the_lab_managers_only(
    db, settings_fast, monkeypatch
) -> None:
    """Members can't rebind a channel, so pinging them would be pure noise."""
    lab = Lab.objects.create(name="Lab", slug="lab")
    bind(lab=lab, state="pending_setup", guild_id="g1")
    owner = User.objects.create_user("owner")
    member = User.objects.create_user("member")
    LabMembership.objects.create(
        user=owner, lab=lab, role=LabMembership.Role.OWNER
    )
    LabMembership.objects.create(
        user=member, lab=lab, role=LabMembership.Role.MEMBER
    )

    outbox.enqueue_channel(
        dedupe_key="chan-dead", kind="reminder", channel_id="c1", lab=lab
    )
    monkeypatch.setattr(discord_api, "_request", _Transport(403, {"code": 50013}))
    outbox.drain()

    told = set(
        Notification.objects.filter(kind=_Kind.DELIVERY_FAILED).values_list(
            "user__username", flat=True
        )
    )
    assert told == {"owner"}


@pytest.mark.django_db
def test_the_notice_never_goes_back_out_over_discord(
    linked, settings_fast, monkeypatch
) -> None:
    """If Discord is the broken thing, a Discord notice fails for the same reason."""
    outbox.enqueue_dm(dedupe_key="dm-blocked", kind="reminder", user=linked)
    monkeypatch.setattr(discord_api, "_request", _Transport(403, {"code": 50007}))

    outbox.drain()

    assert Notification.objects.filter(kind=_Kind.DELIVERY_FAILED).count() == 1
    # Exactly one outbox row: the failure did not queue a message about itself.
    assert DiscordOutboxMessage.objects.count() == 1


@pytest.mark.django_db
def test_a_deleted_channel_names_the_actual_problem(
    db, settings_fast, monkeypatch
) -> None:
    lab = Lab.objects.create(name="Lab", slug="lab2")
    owner = User.objects.create_user("owner2")
    LabMembership.objects.create(user=owner, lab=lab, role=LabMembership.Role.OWNER)
    outbox.enqueue_channel(
        dedupe_key="chan-gone", kind="lab_digest", channel_id="c9", lab=lab
    )
    monkeypatch.setattr(discord_api, "_request", _Transport(404, {"code": 10003}))

    outbox.drain()

    note = Notification.objects.get(kind=_Kind.DELIVERY_FAILED)
    assert "no longer exists" in note.title.lower()
    assert "/setup" in note.body


@pytest.mark.django_db
def test_an_unnotifiable_failure_does_not_break_the_drain(
    db, settings_fast, monkeypatch
) -> None:
    """A channel post with no lab attached has nobody to tell — settle it anyway."""
    outbox.enqueue_channel(
        dedupe_key="orphan", kind="lab_digest", channel_id="c1", lab=None
    )
    monkeypatch.setattr(discord_api, "_request", _Transport(403, {"code": 50013}))

    result = outbox.drain()

    assert result.failed == 1
    assert Notification.objects.count() == 0
