"""Pacing: a burst to one channel is spaced out instead of sent back to back.

Discord rate limits per channel, a forum hardest of all. A drain leaves a gap
between posts to the same channel, opens only a few forum threads per channel, and
hands the rest on to the next drain without spending their attempts.
"""

from __future__ import annotations

import pytest
from django.utils import timezone

from apps.integrations.models import DiscordOutboxMessage
from apps.integrations.services import discord_api, outbox
from apps.integrations.services.discord_api import RawResponse

_Status = DiscordOutboxMessage.Status
_Mode = DiscordOutboxMessage.Mode


class _Discord:
    def __init__(self):
        self.posts: list[str] = []
        self.limit_after: int | None = None  # 429 once this many have gone out
        self.retry_after = 40.0

    def __call__(self, method, path, *, auth=None, json_body=None, **kwargs):
        if self.limit_after is not None and len(self.posts) >= self.limit_after:
            return RawResponse(429, {}, retry_after=self.retry_after)
        self.posts.append(path)
        return RawResponse(200, {"id": f"id-{len(self.posts)}"})


@pytest.fixture
def discord(monkeypatch, settings):
    settings.DISCORD_BOT_TOKEN = "test-token"
    settings.DISCORD_OUTBOX_RETRY_SECONDS = 300
    settings.DISCORD_OUTBOX_SPACING_SECONDS = 2.0
    settings.DISCORD_OUTBOX_THREADS_PER_DRAIN = 4
    stub = _Discord()
    monkeypatch.setattr(discord_api, "_request", stub)
    return stub


@pytest.fixture
def naps(monkeypatch):
    taken: list[float] = []
    monkeypatch.setattr(outbox, "_sleep", taken.append)
    return taken


def _threads(count: int, channel: str = "forum-1") -> None:
    for n in range(count):
        row, _ = outbox.enqueue_channel(
            dedupe_key=f"{channel}-{n}", kind="announcement", channel_id=channel
        )
        row.mode = _Mode.FORUM_THREAD
        row.extra = {"name": f"Thread {n}"}
        row.save(update_fields=["mode", "extra"])


@pytest.mark.django_db
def test_one_drain_opens_a_few_threads_and_hands_the_rest_on(discord, naps) -> None:
    _threads(10)
    now = timezone.now()

    result = outbox.drain(now=now)

    assert result.delivered == 4 and result.paced == 6
    assert naps == [2.0, 2.0, 2.0]  # a gap between each, none before the first
    waiting = DiscordOutboxMessage.objects.filter(status=_Status.PENDING)
    assert waiting.count() == 6
    # Handed on, not failed: no attempt spent, no error recorded, due in order.
    assert all(r.attempts == 0 and r.last_error_reason == "" for r in waiting)
    due = sorted(r.next_attempt_at for r in waiting)
    assert due[0] > now and len(set(due)) == 6


@pytest.mark.django_db
def test_later_drains_finish_the_burst(discord, naps) -> None:
    _threads(10)
    now = timezone.now()

    for minute in range(3):
        outbox.drain(now=now + timezone.timedelta(minutes=minute))

    assert len(discord.posts) == 10
    assert not DiscordOutboxMessage.objects.exclude(status=_Status.SENT).exists()


@pytest.mark.django_db
def test_a_rate_limit_stops_that_channel_for_the_rest_of_the_drain(
    discord, naps
) -> None:
    _threads(4)
    discord.limit_after = 2
    now = timezone.now()

    result = outbox.drain(now=now)

    # Two went out, the third met the limit, the fourth was never tried.
    assert result.delivered == 2 and result.retried == 1 and result.paced == 1
    limited = DiscordOutboxMessage.objects.get(last_error_reason="rate_limited")
    untried = DiscordOutboxMessage.objects.get(
        status=_Status.PENDING, last_error_reason=""
    )
    assert untried.attempts == 0
    # It waits out the same limit before it is tried.
    assert untried.next_attempt_at > limited.next_attempt_at


@pytest.mark.django_db
def test_each_channel_is_paced_on_its_own(discord, naps) -> None:
    _threads(3, "forum-a")
    _threads(3, "forum-b")

    result = outbox.drain()

    assert result.delivered == 6 and result.paced == 0
    assert naps == [2.0] * 4  # two gaps per channel


@pytest.mark.django_db
def test_plain_channel_posts_are_spaced_but_not_capped(discord, naps) -> None:
    for n in range(6):
        outbox.enqueue_channel(
            dedupe_key=f"msg-{n}", kind="lab_digest", channel_id="chan", content="hi"
        )

    result = outbox.drain()

    assert result.delivered == 6 and result.paced == 0
    assert naps == [2.0] * 5
