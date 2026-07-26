"""Delivery, retry, and giving up — the behaviour the whole phase exists for.

The transport is faked at ``discord_api._request``, so the real payload building,
``allowed_mentions.parse == []`` enforcement, and nonce handling all run; only the
socket is replaced.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from apps.integrations.models import DiscordIdentity, DiscordOutboxMessage
from apps.integrations.services import discord_api, outbox, resolve
from apps.integrations.services.discord_api import RawResponse
from apps.integrations.services.discord_failure import Reason

_Status = DiscordOutboxMessage.Status


class _Transport:
    """Scripted Discord. ``message_status`` drives what a message POST returns."""

    def __init__(self):
        self.calls: list[dict] = []
        self.message_status = 200
        self.message_body: dict = {"id": "msg-1"}
        self.retry_after: float | None = None

    def __call__(self, method, path, *, auth=None, json_body=None, **kwargs):
        self.calls.append({"method": method, "path": path, "json_body": json_body})
        if path == "/users/@me/channels":
            return RawResponse(200, {"id": "dm-chan"})
        if path.endswith("/messages"):
            return RawResponse(
                self.message_status, self.message_body, retry_after=self.retry_after
            )
        return RawResponse(404, {})

    @property
    def sends(self) -> list[dict]:
        return [c for c in self.calls if c["path"].endswith("/messages")]


@pytest.fixture
def transport(monkeypatch, settings):
    settings.DISCORD_BOT_TOKEN = "test-token"
    settings.DISCORD_OUTBOX_RETRY_SECONDS = 300
    settings.DISCORD_OUTBOX_MAX_ATTEMPTS = 5
    stub = _Transport()
    monkeypatch.setattr(discord_api, "_request", stub)
    return stub


@pytest.fixture
def user(db):
    return User.objects.create_user("drain-user")


@pytest.fixture
def linked(user):
    DiscordIdentity.objects.create(
        user=user,
        discord_user_id="900000000000000002",
        state=DiscordIdentity.State.ACTIVE,
        link_method=DiscordIdentity.LinkMethod.OAUTH,
        dm_channel_id="cached-chan",
        dm_ok=True,
    )
    return user


def _queue_dm(user, key="dm-1"):
    row, _ = outbox.enqueue_dm(
        dedupe_key=key, kind="reminder", user=user, content="hello"
    )
    return row


# --------------------------------------------------------------------------- #
# The happy path
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_a_queued_dm_is_delivered_and_settled(linked, transport) -> None:
    row = _queue_dm(linked)

    result = outbox.drain()

    assert result.delivered == 1
    row.refresh_from_db()
    assert row.status == _Status.SENT
    assert row.discord_message_id == "msg-1"
    assert transport.sends[0]["path"] == "/channels/cached-chan/messages"


@pytest.mark.django_db
def test_delivery_carries_an_enforced_nonce(linked, transport) -> None:
    """The nonce is what makes a retry after an ambiguous timeout safe."""
    row = _queue_dm(linked)
    outbox.drain()

    body = transport.sends[0]["json_body"]
    assert body["nonce"] == str(row.pk)
    assert body["enforce_nonce"] is True
    assert len(body["nonce"]) <= discord_api.NONCE_MAX_LENGTH


@pytest.mark.django_db
def test_a_settled_message_is_never_sent_again(linked, transport) -> None:
    _queue_dm(linked)
    outbox.drain()
    outbox.drain()
    outbox.drain()

    assert len(transport.sends) == 1


# --------------------------------------------------------------------------- #
# Temporary failures — retry
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_a_server_error_is_retried_and_then_delivered(linked, transport) -> None:
    """The original bug, inverted: an outage delays a message, it does not lose it."""
    row = _queue_dm(linked)

    transport.message_status = 503
    result = outbox.drain()
    assert result.retried == 1
    row.refresh_from_db()
    assert row.status == _Status.PENDING
    assert row.last_error_reason == Reason.UPSTREAM

    transport.message_status = 200
    later = timezone.now() + timedelta(seconds=301)
    assert outbox.drain(now=later).delivered == 1

    row.refresh_from_db()
    assert row.status == _Status.SENT
    assert row.attempts == 2


@pytest.mark.django_db
def test_rate_limit_waits_at_least_as_long_as_discord_asked(linked, transport) -> None:
    """Discord's Retry-After may lengthen the wait, never shorten it."""
    row = _queue_dm(linked)
    transport.message_status = 429
    transport.retry_after = 900  # far longer than the 300s default

    before = timezone.now()
    outbox.drain(now=before)

    row.refresh_from_db()
    assert row.last_error_reason == Reason.RATE_LIMITED
    assert (row.next_attempt_at - before).total_seconds() >= 900


@pytest.mark.django_db
def test_a_short_retry_after_does_not_shorten_the_wait(linked, transport) -> None:
    row = _queue_dm(linked)
    transport.message_status = 429
    transport.retry_after = 2  # honouring this would re-enter the same rate limit

    before = timezone.now()
    outbox.drain(now=before)

    row.refresh_from_db()
    assert (row.next_attempt_at - before).total_seconds() >= 300


# --------------------------------------------------------------------------- #
# Permanent failures — stop, and record why
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_a_blocked_dm_stops_immediately_and_marks_the_person_unreachable(
    linked, transport
) -> None:
    row = _queue_dm(linked)
    transport.message_status = 403
    transport.message_body = {"code": 50007}

    result = outbox.drain()

    assert result.failed == 1
    assert result.retried == 0  # retrying a blocked DM accomplishes nothing
    row.refresh_from_db()
    assert row.status == _Status.FAILED
    assert row.last_error_reason == Reason.DM_BLOCKED

    identity = resolve.active_identity_for_user(linked)
    assert identity.dm_ok is False  # the failure taught us about the link

    outbox.drain(now=timezone.now() + timedelta(days=1))
    assert len(transport.sends) == 1  # and it is never attempted again


@pytest.mark.django_db
def test_a_deleted_channel_is_permanent(user, transport) -> None:
    outbox.enqueue_channel(
        dedupe_key="chan-1", kind="lab_digest", channel_id="gone", content="hi"
    )
    transport.message_status = 404
    transport.message_body = {"code": 10003}

    result = outbox.drain()

    assert result.failed == 1
    assert (
        DiscordOutboxMessage.objects.get().last_error_reason == Reason.CHANNEL_GONE
    )


@pytest.mark.django_db
def test_a_user_who_never_linked_is_not_retried(user, transport) -> None:
    _queue_dm(user)  # no DiscordIdentity at all

    result = outbox.drain()

    assert result.failed == 1
    assert transport.sends == []  # we never even reached Discord


@pytest.mark.django_db
def test_a_missing_bot_token_is_permanent_not_an_endless_retry(
    linked, monkeypatch, settings
) -> None:
    settings.DISCORD_BOT_TOKEN = ""
    _queue_dm(linked)

    result = outbox.drain()

    assert result.failed == 1
    assert (
        DiscordOutboxMessage.objects.get().last_error_reason == Reason.NOT_CONFIGURED
    )


# --------------------------------------------------------------------------- #
# Giving up
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_attempts_are_capped_and_the_message_is_dead_lettered(
    linked, transport, settings
) -> None:
    settings.DISCORD_OUTBOX_MAX_ATTEMPTS = 5
    settings.DISCORD_OUTBOX_RETRY_SECONDS = 300
    row = _queue_dm(linked)
    transport.message_status = 503

    now = timezone.now()
    for attempt in range(6):  # one more pass than the ceiling allows
        outbox.drain(now=now + timedelta(seconds=301 * attempt))

    row.refresh_from_db()
    assert row.attempts == 5, "a sixth attempt must never happen"
    assert row.status == _Status.DEAD
    assert len(transport.sends) == 5


@pytest.mark.django_db
def test_one_logical_message_is_sent_once_not_once_per_attempt(
    linked, transport
) -> None:
    """Five attempts, one delivery — the 'don't spam them' half of the policy."""
    row = _queue_dm(linked)

    transport.message_status = 503
    outbox.drain()
    outbox.drain(now=timezone.now() + timedelta(seconds=301))
    transport.message_status = 200
    outbox.drain(now=timezone.now() + timedelta(seconds=602))

    row.refresh_from_db()
    assert row.status == _Status.SENT
    assert DiscordOutboxMessage.objects.count() == 1
    assert sum(1 for c in transport.sends if c) == 3  # attempts
    # ...but only the last one succeeded, so the person saw exactly one message.
    assert row.discord_message_id == "msg-1"


# --------------------------------------------------------------------------- #
# The deliberate carve-outs
# --------------------------------------------------------------------------- #
# Two senders must keep answering synchronously and must never grow an outbox row.
# Asserted here so nobody "finishes the migration" later by accident.


@pytest.mark.django_db
def test_preflight_channel_still_answers_synchronously(transport) -> None:
    """`/setup` has to tell the admin now whether the bind worked."""
    from apps.content.reminders_discord import preflight_channel

    outcome = preflight_channel("chan-1")

    assert outcome.ok is True  # a real verdict, not "queued"
    assert transport.sends, "preflight must reach Discord directly"
    assert DiscordOutboxMessage.objects.count() == 0


@pytest.mark.django_db
def test_the_ops_error_sink_does_not_go_through_the_queue(transport, settings) -> None:
    """Routing the outage reporter through the outbox would silence it."""
    from apps.integrations.services import errors

    settings.DISCORD_ERROR_CHANNEL_ID = "err-chan"
    errors.post_embed("Outbox down", "everything is on fire", severity="error")

    assert DiscordOutboxMessage.objects.count() == 0
