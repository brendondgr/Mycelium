"""The two guarantees Phase A exists to protect, written before the mechanism.

Written as ``xfail(strict=True)`` before the mechanism existed, and un-marked in A-5
once they genuinely passed — ``strict`` is what forced that, since an unexpected pass
fails the build too.

Why these two specifically. Introducing a queue is most likely to regress exactly
the duplicate-prevention rules that already work:

1. **Nothing is lost to a blip.** Today ``reminders_tick._seal`` writes a
   ``ReminderFire`` row whether or not Discord accepted the message, and
   ``_triggered_keys`` only checks that a row *exists* — so one 503 retires that
   reminder permanently.
2. **One subscription still sends one message a day.** The anti-burst rule
   (``test_reminders_tick.py::test_worker_down_48h_no_burst``) falls out of the tick
   calling ``_deliver`` once and sealing every triggered offset with that single
   outcome. A queue must not turn one logical notification into three messages.

Imports of the not-yet-existing outbox are deliberately *inside* the test bodies:
at module scope they would be a collection error rather than an honest xfail.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.contrib.auth.models import User
from tools.retrieval.models import (
    ContentDeadline,
    ContentItem,
    ReminderSubscription,
    SavedOpportunity,
)

from apps.content.reminders import create_subscription
from apps.content.reminders_tick import run_tick
from apps.content.tests.entitle import paid_plan
from apps.integrations.services import discord_api
from apps.integrations.services.discord_api import RawResponse

TODAY = date(2026, 7, 16)
_Kind = SavedOpportunity.DeadlineKind
_Area = SavedOpportunity.Area


@pytest.fixture
def user(db):
    """A reminder recipient on a paid plan — Discord delivery is gated on one."""
    person = User.objects.create_user("outbox-user")
    paid_plan(person)
    return person


@pytest.fixture
def linked(user, settings):
    """An ACTIVE Discord identity with a cached DM channel, and a bot token."""
    from apps.integrations.models import DiscordIdentity

    settings.DISCORD_BOT_TOKEN = "test-token"
    DiscordIdentity.objects.create(
        user=user,
        discord_user_id="900000000000000001",
        state=DiscordIdentity.State.ACTIVE,
        link_method=DiscordIdentity.LinkMethod.OAUTH,
        dm_channel_id="dm-chan",
        dm_ok=True,
    )
    return user


class _FlakyTransport:
    """Fails every message send with ``status`` until ``heal()`` is called."""

    def __init__(self, status: int = 503):
        self.status = status
        self.calls: list[dict] = []
        self.healthy = False

    def heal(self) -> None:
        self.healthy = True

    def __call__(self, method, path, *, auth=None, json_body=None, **kwargs):
        self.calls.append({"method": method, "path": path, "json_body": json_body})
        if path == "/users/@me/channels":
            return RawResponse(200, {"id": "dm-chan"})
        if path.endswith("/messages"):
            if self.healthy:
                return RawResponse(200, {"id": "msg-1"})
            return RawResponse(self.status, {})
        return RawResponse(404, {})

    @property
    def message_posts(self) -> list[dict]:
        return [c for c in self.calls if c["path"].endswith("/messages")]


def _content_with_deadline(due: date):
    item = ContentItem.objects.create(
        type=ContentItem.Type.GRANT,
        source="pivot",
        external_id=f"outbox-{due}",
        metadata={"title": "Test grant"},
    )
    ContentDeadline.objects.create(
        content=item,
        kind=_Kind.APPLICATION,
        due_date=due,
        confidence=ContentDeadline.Confidence.CONFIRMED,
    )
    return item


def _subscribe(user, *, due, offsets, content=None):
    return create_subscription(
        target_user=user,
        content=content,
        deadline_kind=_Kind.APPLICATION,
        area=_Area.GRANT,
        title="Test grant",
        due_date=due,
        offsets=offsets,
        today=TODAY,
    )


@pytest.mark.django_db
def test_transient_discord_failure_is_retried_not_lost(
    linked, monkeypatch, settings
) -> None:
    """A 503 must delay delivery, not cancel it."""
    from apps.integrations.services.outbox import drain

    settings.DISCORD_OUTBOX_RETRY_SECONDS = 0  # no waiting in tests
    transport = _FlakyTransport(503)
    monkeypatch.setattr(discord_api, "_request", transport)

    due = TODAY + timedelta(days=7)
    _subscribe(
        linked, due=due, offsets=[(1, "week")], content=_content_with_deadline(due)
    )

    run_tick(TODAY)
    drain()  # Discord is down
    assert transport.message_posts, "the first attempt should have been made"

    transport.heal()
    drain()  # Discord is back

    delivered = [c for c in transport.message_posts]
    assert len(delivered) >= 2, "the reminder must be re-attempted after the outage"

    from apps.integrations.services import resolve

    assert resolve.outbox_counters(since=None)["delivered"] == 1


@pytest.mark.django_db
def test_one_subscription_one_message_per_day_survives_queueing(
    linked, monkeypatch
) -> None:
    """Three offsets arriving at once still produce one queued message, one send.

    The end-to-end restatement of ``test_worker_down_48h_no_burst``: a queue must
    not turn one logical notification into three Discord messages.
    """
    from apps.integrations.services.outbox import drain

    transport = _FlakyTransport()
    transport.heal()
    monkeypatch.setattr(discord_api, "_request", transport)

    due = TODAY + timedelta(days=10)
    _subscribe(
        linked,
        due=due,
        offsets=[(2, "day"), (5, "day"), (1, "week")],
        content=_content_with_deadline(due),
    )

    # The worker was down; the catch-up tick sees all three fire dates at once.
    result = run_tick(TODAY + timedelta(days=9))
    assert result.notifications == 1

    from apps.integrations.models import DiscordOutboxMessage

    assert DiscordOutboxMessage.objects.count() == 1, "one message, not three"

    drain()
    assert len(transport.message_posts) == 1, "one Discord send, not three"

    sub = ReminderSubscription.objects.get()
    assert sub.fires.count() == 3  # all three offsets sealed by the single fire
