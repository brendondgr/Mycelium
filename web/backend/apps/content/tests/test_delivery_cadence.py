"""Cadence decides what is pushed, and never what is computed (plan Phase 0).

``WatchPreference.cadence`` and ``LabWatchPreference.cadence`` existed for months
before anything read them: onboarding, the profile editor and the lab editor all
wrote the field, and ``eligible_recipients`` / ``eligible_labs`` ignored it, so
every linked target got a Discord post every day whatever they chose. These tests
are the contract that read side now owes.

Every test names its own date rather than asking the clock. The whole subject here
is which weekday it is, so a suite that runs green Tuesday and red Monday would be
testing the calendar instead of the code.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from tools.retrieval.models import ContentItem, RelevanceScore

from apps.accounts.models import Lab, LabWatchPreference, WatchCadence, WatchPreference
from apps.content import delivery
from apps.content.briefing import generate_briefing_for_user
from apps.content.daily_report_send import eligible_recipients
from apps.content.lab_digest import eligible_labs
from apps.content.tests.entitle import entitle_user
from apps.integrations.models import DiscordOutboxMessage
from apps.integrations.services import resolve
from apps.integrations.testing import bind
from apps.integrations.tests.base import discord_test_settings, grant_bot_server

MONDAY = date(2026, 9, 21)
TUESDAY = date(2026, 9, 22)
FRIDAY = date(2026, 9, 25)
SATURDAY = date(2026, 9, 26)
SUNDAY = date(2026, 9, 27)


# --------------------------------------------------------------------------- #
# The matrix (plan §3.1)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("cadence", "day", "expected"),
    [
        (WatchCadence.DAILY, MONDAY, {delivery.DAILY}),
        (WatchCadence.DAILY, TUESDAY, {delivery.DAILY}),
        (WatchCadence.DAILY, FRIDAY, {delivery.DAILY}),
        (WatchCadence.DAILY, SATURDAY, {delivery.DAILY}),
        (WatchCadence.DAILY, SUNDAY, {delivery.DAILY}),
        (WatchCadence.WEEKLY, MONDAY, {delivery.WEEKLY}),
        (WatchCadence.WEEKLY, TUESDAY, set()),
        (WatchCadence.WEEKLY, FRIDAY, set()),
        (WatchCadence.WEEKLY, SATURDAY, set()),
        (WatchCadence.WEEKLY, SUNDAY, set()),
    ],
)
def test_the_cadence_matrix(cadence, day, expected) -> None:
    assert delivery.push_kinds(cadence, day) == expected


def test_daily_cadence_gets_a_daily_on_monday_never_the_weekly() -> None:
    """Someone who chose "Daily digest" is never sent a weekly instead."""
    kinds = delivery.push_kinds(WatchCadence.DAILY, MONDAY)
    assert kinds == {delivery.DAILY}
    assert delivery.WEEKLY not in kinds


def test_daily_cadence_covers_the_weekend() -> None:
    """Daily means every day: sign-up promises a message, not four of seven."""
    for day in (SATURDAY, SUNDAY):
        assert delivery.push_kinds(WatchCadence.DAILY, day) == {delivery.DAILY}


def test_weekly_cadence_is_silent_every_day_but_monday() -> None:
    """The weekend is not special for a weekly reader — every non-Monday is quiet."""
    for day in (TUESDAY, FRIDAY, SATURDAY, SUNDAY):
        assert delivery.push_kinds(WatchCadence.WEEKLY, day) == set()


def test_urgent_alerts_are_the_only_between_monday_exception() -> None:
    """Open decision OD2: opt-in, off by default, and never a second daily."""
    assert delivery.push_kinds(WatchCadence.WEEKLY, TUESDAY) == set()
    assert delivery.push_kinds(WatchCadence.WEEKLY, TUESDAY, urgent_opt_in=True) == {
        delivery.URGENT
    }
    # A daily-cadence reader hears about a moved deadline in the next morning's
    # daily, so raising a second message would be the same news twice.
    assert delivery.push_kinds(WatchCadence.DAILY, TUESDAY, urgent_opt_in=True) == {
        delivery.DAILY
    }


def test_an_unknown_or_missing_cadence_falls_back_to_daily() -> None:
    """Daily is what every existing row has been receiving, whatever it stored."""
    for value in (None, "", "fortnightly"):
        assert delivery.normalise_cadence(value) == delivery.CADENCE_DAILY
        assert delivery.push_kinds(value, TUESDAY) == {delivery.DAILY}


# --------------------------------------------------------------------------- #
# Send time
# --------------------------------------------------------------------------- #
@pytest.fixture
def reader(db) -> User:
    user = User.objects.create_user("reader", password="x")
    WatchPreference.objects.create(user=user, categories=["papers"])
    entitle_user(user)
    return user


@pytest.mark.django_db
def test_not_before_holds_row_until_local_send_hour(reader: User) -> None:
    """8am in the recipient's zone, not 8am on the run host (plan 3.2, OD3)."""
    reader.watch.timezone = "Asia/Tokyo"
    reader.watch.send_hour_local = 8
    reader.watch.save(update_fields=["timezone", "send_hour_local"])

    when = delivery.send_time(reader, TUESDAY)

    assert when == datetime(2026, 9, 22, 8, tzinfo=ZoneInfo("Asia/Tokyo"))
    assert when.astimezone(ZoneInfo("UTC")).hour == 23  # the Monday before, in UTC


@pytest.mark.django_db
def test_a_lab_keeps_its_own_hour_and_zone(db) -> None:
    """A lab's schedule already lived on ``Lab`` for reminders; it stays there."""
    lab = Lab.objects.create(
        name="Pulse Lab", slug="pulse", timezone="Europe/Berlin", send_hour_local=9
    )
    assert delivery.send_time(lab, TUESDAY) == datetime(
        2026, 9, 22, 9, tzinfo=ZoneInfo("Europe/Berlin")
    )


@pytest.mark.django_db
def test_an_unreadable_zone_falls_back_rather_than_raising(reader: User) -> None:
    """One bad zone name must not stop the batch behind it."""
    reader.watch.timezone = "Mars/Olympus"
    reader.watch.save(update_fields=["timezone"])
    assert delivery.send_time(reader, TUESDAY).tzinfo is not None


# --------------------------------------------------------------------------- #
# The gate, end to end
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_weekly_cadence_user_gets_no_tuesday_dm(reader: User) -> None:
    reader.watch.cadence = WatchCadence.WEEKLY
    reader.watch.save(update_fields=["cadence"])

    assert eligible_recipients(None, on=TUESDAY) == []
    assert DiscordOutboxMessage.objects.filter(kind="daily_report").count() == 0


@pytest.mark.django_db
def test_daily_cadence_user_is_a_tuesday_recipient(reader: User) -> None:
    assert [u.id for u in eligible_recipients(None, on=TUESDAY)] == [reader.id]


@pytest.mark.django_db
def test_a_daily_reader_is_a_recipient_at_the_weekend(reader: User) -> None:
    """The weekend blackout is gone: "Daily digest" covers Saturday and Sunday."""
    assert [u.id for u in eligible_recipients(None, on=SATURDAY)] == [reader.id]
    assert [u.id for u in eligible_recipients(None, on=SUNDAY)] == [reader.id]


@pytest.mark.django_db
def test_a_weekly_reader_is_not_a_recipient_at_the_weekend(reader: User) -> None:
    reader.watch.cadence = WatchCadence.WEEKLY
    reader.watch.save(update_fields=["cadence"])
    assert eligible_recipients(None, on=SATURDAY) == []
    assert eligible_recipients(None, on=SUNDAY) == []


@pytest.mark.django_db
def test_weekly_cadence_user_still_gets_daily_web_briefing(reader: User) -> None:
    """Plan D2: cadence changes what is pushed, never what is computed or shown."""
    reader.watch.cadence = WatchCadence.WEEKLY
    reader.watch.save(update_fields=["cadence"])
    content = ContentItem.objects.create(
        type=ContentItem.Type.PAPER,
        source="test",
        external_id="p1",
        source_url="https://example.org/p1",
        metadata={"title": "A paper"},
    )
    today = "2026-09-22"
    RelevanceScore.objects.create(
        content=content,
        target_user=reader,
        score=0.8,
        signals={
            "suggested": True,
            "rank": 1,
            "top_rank": 1,
            "entered_top_on": today,
            "first_seen": today,
            "headline": "Headline",
            "reason": "Why it fits.",
        },
    )

    briefing = generate_briefing_for_user(reader, complete=lambda _s, _u: None)

    assert briefing.body.strip()
    assert eligible_recipients(None, on=TUESDAY) == []


@pytest.mark.django_db
def test_a_weekly_cadence_lab_channel_is_quiet_until_monday(db) -> None:
    with discord_test_settings:
        lab = Lab.objects.create(name="Pulse Lab", slug="pulse")
        LabWatchPreference.objects.update_or_create(
            lab=lab, defaults={"cadence": WatchCadence.WEEKLY}
        )
        grant_bot_server(lab)
        bind(lab=lab, guild_id="g-pulse", updates="chan-1")
        lab.refresh_from_db()

        assert eligible_labs([lab], on=TUESDAY) == []
        assert eligible_labs([lab], on=MONDAY, kind=delivery.WEEKLY) == [lab]


@pytest.mark.django_db
def test_a_scheduled_row_is_not_claimed_before_its_send_hour(reader: User) -> None:
    """``not_before`` reuses ``next_attempt_at``, which the drain already filters on.

    No new machinery: a held row retries, dead-letters and reports exactly like
    every other row, and ``claim_outbox_batch`` needs no knowledge of scheduling.
    """
    from apps.integrations.services import outbox

    now = timezone.now()
    outbox.enqueue_dm(
        dedupe_key="scheduled:1",
        kind="daily_report",
        user=reader,
        content="held",
        not_before=now + timedelta(hours=3),
    )
    row = DiscordOutboxMessage.objects.get(dedupe_key="scheduled:1")
    assert row.next_attempt_at > now

    assert resolve.claim_outbox_batch(now=now) == []
    claimed = resolve.claim_outbox_batch(now=now + timedelta(hours=4))
    assert [r.dedupe_key for r in claimed] == ["scheduled:1"]


@pytest.mark.django_db
def test_a_send_hour_already_past_is_due_at_once(reader: User) -> None:
    """A run that finishes late delivers now, rather than holding for a day."""
    from apps.integrations.services import outbox

    now = timezone.now()
    outbox.enqueue_dm(
        dedupe_key="late:1",
        kind="daily_report",
        user=reader,
        content="late",
        not_before=now - timedelta(hours=5),
    )
    row = DiscordOutboxMessage.objects.get(dedupe_key="late:1")
    assert row.next_attempt_at <= timezone.now()
    assert [r.dedupe_key for r in resolve.claim_outbox_batch()] == ["late:1"]


@pytest.mark.django_db
def test_run_analytics_counts_a_held_row_as_scheduled_not_pending(reader: User) -> None:
    """A report waiting for someone's morning is not a backlog (plan 0.3)."""
    from apps.content.run_analytics import collect_delivery
    from apps.integrations.services import outbox

    outbox.enqueue_dm(
        dedupe_key="held:1",
        kind="daily_report",
        user=reader,
        content="held",
        not_before=timezone.now() + timedelta(hours=6),
    )

    counted = collect_delivery(timezone.localdate())

    assert counted.reports_queued == 1
    assert counted.reports_scheduled == 1
    assert counted.reports_pending == 0


# --------------------------------------------------------------------------- #
# The backfill (plan M3 / open decision OD1)
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_existing_watch_rows_backfilled_to_daily(db) -> None:
    """Nobody's experience changes silently on the day cadence becomes real.

    The stored default was ``weekly`` while every row was in fact receiving daily
    posts. The backfill records what people were getting; the choice is offered
    forward rather than applied retroactively.
    """
    user = User.objects.create_user("fresh", password="x")
    row = WatchPreference.objects.create(user=user)
    assert row.cadence == WatchCadence.DAILY

    lab = Lab.objects.create(name="New Lab", slug="new-lab")
    assert LabWatchPreference.objects.get(lab=lab).cadence == WatchCadence.DAILY


@pytest.mark.django_db
def test_the_timeline_placeholders_have_their_documented_defaults(db) -> None:
    """Plan D5 / M1: 14 days of buffer, 60 days of writing window."""
    user = User.objects.create_user("fresh", password="x")
    watch = WatchPreference.objects.create(user=user)
    assert (watch.deadline_buffer_days, watch.min_paper_window_days) == (14, 60)
    assert watch.urgent_alerts is False
    assert (watch.timezone, watch.send_hour_local) == ("America/New_York", 8)

    lab = Lab.objects.create(name="New Lab", slug="new-lab")
    lab_watch = LabWatchPreference.objects.get(lab=lab)
    assert (lab_watch.deadline_buffer_days, lab_watch.min_paper_window_days) == (14, 60)
    assert (lab.timezone, lab.send_hour_local) == ("America/New_York", 9)
