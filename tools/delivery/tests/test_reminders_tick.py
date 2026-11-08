"""R1 — the reminder tick: offsets, sealing, one-per-day cap, snapshot resync.

The §14 regression assertions applicable to R1 (in-app delivery only). Pure
relational, runs on SQLite. ``TODAY`` anchors every date so the tests never call
``date.today()``.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from apps.accounts.models import Lab, LabMembership
from django.contrib.auth.models import User

from tools.delivery import reminders
from tools.delivery.models import (
    Notification,
    ReminderFire,
    ReminderSubscription,
    SavedOpportunity,
)
from tools.delivery.reminders import (
    ReminderError,
    create_subscription,
    offset_fire_date,
)
from tools.delivery.reminders_tick import run_tick
from tools.retrieval.models import ContentDeadline, ContentItem

TODAY = date(2026, 7, 16)
_Kind = SavedOpportunity.DeadlineKind
_Area = SavedOpportunity.Area


@pytest.fixture
def user(db):
    return User.objects.create_user("reminder-user")


@pytest.fixture
def pinned_prune_clock(monkeypatch):
    """Pin the prune → stale hook's wall clock to ``TODAY``.

    ``content.delete()`` fires a ``pre_delete`` receiver, which cannot be handed a
    reference date and so reads ``reminders.reference_today()``. Every other date in
    this module is anchored to ``TODAY``; without pinning this one too, any test that
    deletes content silently rots the day the real clock passes the fixture deadline.
    """
    monkeypatch.setattr(reminders, "reference_today", lambda: TODAY)


def _content_with_deadline(due: date | None, kind=_Kind.APPLICATION):
    item = ContentItem.objects.create(
        type=ContentItem.Type.GRANT,
        source="pivot",
        external_id=f"g-{due}-{kind}",
        metadata={"title": "Test grant"},
    )
    ContentDeadline.objects.create(
        content=item,
        kind=kind,
        due_date=due,
        confidence=(
            ContentDeadline.Confidence.CONFIRMED
            if due
            else ContentDeadline.Confidence.ROLLING
        ),
    )
    return item


def _subscribe(user, *, due, offsets, content=None, kind=_Kind.APPLICATION):
    return create_subscription(
        target_user=user,
        content=content,
        deadline_kind=kind,
        area=_Area.GRANT,
        title="Test grant",
        due_date=due,
        offsets=offsets,
        today=TODAY,
    )


# --------------------------------------------------------------------------- #
# Sealing & the one-per-day cap
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_subscribing_with_backdated_offsets_sends_nothing_immediately(user) -> None:
    due = TODAY + timedelta(days=21)  # three weeks out
    _subscribe(user, due=due, offsets=[(2, "month"), (1, "month")])
    result = run_tick(TODAY)
    assert result.notifications == 0
    assert Notification.objects.count() == 0
    fires = ReminderFire.objects.all()
    assert fires.count() == 2
    assert all(f.state == ReminderFire.Result.SKIPPED for f in fires)
    assert all(f.skip_reason == "backdated_on_create" for f in fires)


@pytest.mark.django_db
def test_equivalent_offsets_one_week_and_seven_days_fire_once(user) -> None:
    due = TODAY + timedelta(days=7)  # both offsets resolve to fire_date == TODAY
    _subscribe(user, due=due, offsets=[(1, "week"), (7, "day")])
    result = run_tick(TODAY)
    assert result.notifications == 1
    assert Notification.objects.count() == 1
    sent = ReminderFire.objects.filter(state=ReminderFire.Result.SENT)
    assert sent.count() == 2  # both sealed by the single fire


@pytest.mark.django_db
def test_forward_jump_past_multiple_offsets_sends_one_message(user) -> None:
    content = _content_with_deadline(TODAY + timedelta(days=100))
    _subscribe(
        user,
        due=TODAY + timedelta(days=100),
        offsets=[(2, "month"), (1, "month"), (1, "week")],
        content=content,
    )
    assert run_tick(TODAY).fired == 0  # nothing due yet

    row = content.deadline_rows.get()
    row.due_date = TODAY + timedelta(days=3)  # jumped forward past all three
    row.save(update_fields=["due_date"])

    result = run_tick(TODAY)
    assert result.notifications == 1
    assert Notification.objects.count() == 1
    assert ReminderFire.objects.filter(state=ReminderFire.Result.SENT).count() == 3


@pytest.mark.django_db
def test_tick_is_idempotent_within_a_day(user) -> None:
    due = TODAY + timedelta(days=7)
    _subscribe(user, due=due, offsets=[(1, "week")])
    run_tick(TODAY)
    run_tick(TODAY)  # same day, again
    assert Notification.objects.count() == 1
    assert ReminderFire.objects.filter(state=ReminderFire.Result.SENT).count() == 1


@pytest.mark.django_db
def test_worker_down_48h_no_burst(user) -> None:
    content = _content_with_deadline(TODAY + timedelta(days=10))
    _subscribe(
        user,
        due=TODAY + timedelta(days=10),
        offsets=[(2, "day"), (5, "day"), (1, "week")],
        content=content,
    )
    assert run_tick(TODAY).fired == 0  # all fire dates still in the future
    # Worker was down; the catch-up tick sees all three fire dates arrived at once.
    result = run_tick(TODAY + timedelta(days=9))
    assert result.notifications == 1  # one message, not a burst
    assert ReminderFire.objects.filter(state=ReminderFire.Result.SENT).count() == 3


# --------------------------------------------------------------------------- #
# Moved deadlines
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_moved_deadline_unseals_offset_and_fires_with_current_days_remaining(
    user,
) -> None:
    content = _content_with_deadline(date(2026, 11, 1))
    _subscribe(user, due=date(2026, 11, 1), offsets=[(2, "month")], content=content)
    assert run_tick(TODAY).fired == 0  # 2-month fire date (Sep 1) is future

    row = content.deadline_rows.get()
    row.due_date = date(2026, 8, 30)  # moved up to ~1.5 months out
    row.save(update_fields=["due_date"])

    result = run_tick(TODAY)
    assert result.notifications == 1
    note = Notification.objects.get()
    assert "45 days left" in note.body  # actual days, not "your 2-month reminder"
    fire = ReminderFire.objects.get(state=ReminderFire.Result.SENT)
    assert fire.days_remaining == 45


@pytest.mark.django_db
def test_deadline_moves_later_previously_sent_stays_sent_not_resent(user) -> None:
    content = _content_with_deadline(TODAY + timedelta(days=1))
    _subscribe(
        user, due=TODAY + timedelta(days=1), offsets=[(1, "day")], content=content
    )
    assert run_tick(TODAY).notifications == 1  # fires (fire_date == TODAY)

    row = content.deadline_rows.get()
    row.due_date = TODAY + timedelta(days=60)  # pushed far out
    row.save(update_fields=["due_date"])

    result = run_tick(TODAY)
    assert result.fired == 0  # new fire date is in the future
    assert Notification.objects.count() == 1  # the original, not re-sent


@pytest.mark.django_db
def test_snapshot_due_date_resyncs_from_content_deadline_each_tick(user) -> None:
    content = _content_with_deadline(date(2026, 12, 1))
    sub = _subscribe(
        user, due=date(2026, 12, 1), offsets=[(1, "week")], content=content
    )

    row = content.deadline_rows.get()
    row.due_date = date(2026, 12, 20)
    row.save(update_fields=["due_date"])

    run_tick(TODAY)
    sub.refresh_from_db()
    assert sub.due_date == date(2026, 12, 20)


# --------------------------------------------------------------------------- #
# Prune survival, deadline-passed, dateless
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_reminder_survives_content_prune_via_snapshot(user, pinned_prune_clock) -> None:
    content = _content_with_deadline(TODAY + timedelta(days=7))
    _subscribe(
        user, due=TODAY + timedelta(days=7), offsets=[(1, "week")], content=content
    )
    content.delete()  # pruned → content_id goes NULL, snapshot remains

    result = run_tick(TODAY)
    assert result.notifications == 1  # fired from the snapshot
    sub = ReminderSubscription.objects.get()
    assert sub.content_id is None
    assert sub.due_date == TODAY + timedelta(days=7)


@pytest.mark.django_db
def test_reminder_never_fires_after_deadline_passes(user) -> None:
    _subscribe(user, due=TODAY - timedelta(days=1), offsets=[(1, "day")])
    result = run_tick(TODAY)
    assert result.notifications == 0
    assert result.fired_out == 1
    assert ReminderSubscription.objects.get().state == (
        ReminderSubscription.State.FIRED_OUT
    )


@pytest.mark.django_db
def test_no_date_marks_subscription_stale(user) -> None:
    content = _content_with_deadline(TODAY + timedelta(days=7))
    _subscribe(
        user, due=TODAY + timedelta(days=7), offsets=[(1, "week")], content=content
    )
    # The projection later loses the date (e.g. re-scraped as rolling).
    row = content.deadline_rows.get()
    row.due_date = None
    row.save(update_fields=["due_date"])

    result = run_tick(TODAY)
    assert result.staled == 1
    assert ReminderSubscription.objects.get().state == ReminderSubscription.State.STALE


@pytest.mark.django_db
def test_rolling_fellowship_cannot_be_subscribed(user) -> None:
    with pytest.raises(ReminderError):
        _subscribe(user, due=None, offsets=[(1, "week")])


@pytest.mark.django_db
def test_conference_abstract_and_event_are_independently_subscribable(user) -> None:
    item = ContentItem.objects.create(
        type=ContentItem.Type.CONFERENCE, source="pivot", external_id="conf-1"
    )
    ContentDeadline.objects.create(
        content=item,
        kind=_Kind.ABSTRACT,
        due_date=TODAY + timedelta(days=30),
        confidence=ContentDeadline.Confidence.CONFIRMED,
    )
    ContentDeadline.objects.create(
        content=item,
        kind=_Kind.EVENT,
        due_date=TODAY + timedelta(days=120),
        confidence=ContentDeadline.Confidence.CONFIRMED,
    )
    abstract = create_subscription(
        target_user=user,
        content=item,
        deadline_kind=_Kind.ABSTRACT,
        area=_Area.CONFERENCE,
        title="Conf",
        due_date=TODAY + timedelta(days=30),
        offsets=[(1, "week")],
        today=TODAY,
    )
    event = create_subscription(
        target_user=user,
        content=item,
        deadline_kind=_Kind.EVENT,
        area=_Area.CONFERENCE,
        title="Conf",
        due_date=TODAY + timedelta(days=120),
        offsets=[(1, "week")],
        today=TODAY,
    )
    assert abstract.pk != event.pk
    assert ReminderSubscription.objects.count() == 2


# --------------------------------------------------------------------------- #
# Calendar math (pure)
# --------------------------------------------------------------------------- #


def test_relativedelta_months_are_calendar_not_thirty_days() -> None:
    assert offset_fire_date(date(2026, 3, 31), 1, "month") == date(2026, 2, 28)
    assert offset_fire_date(date(2026, 5, 31), 1, "month") == date(2026, 4, 30)
    # Not 30-day math: 2 months before Apr 30 is Feb 28, not Mar 1.
    assert offset_fire_date(date(2026, 4, 30), 2, "month") == date(2026, 2, 28)


def test_eighteen_months_and_two_years_offsets_are_calendar() -> None:
    assert offset_fire_date(date(2028, 1, 15), 18, "month") == date(2026, 7, 15)
    assert offset_fire_date(date(2028, 1, 15), 2, "year") == date(2026, 1, 15)
    assert offset_fire_date(date(2028, 1, 15), 10, "day") == date(2028, 1, 5)


# --------------------------------------------------------------------------- #
# Bounds & lab delivery
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_too_many_offsets_rejected(user) -> None:
    six_offsets = [(n, "day") for n in range(1, 7)]
    with pytest.raises(ReminderError):
        _subscribe(user, due=TODAY + timedelta(days=30), offsets=six_offsets)


@pytest.mark.django_db
def test_exactly_one_target_required(user) -> None:
    lab = Lab.objects.create(name="Lab", slug="lab")
    with pytest.raises(ReminderError):
        create_subscription(
            target_user=user,
            target_lab=lab,
            deadline_kind=_Kind.APPLICATION,
            area=_Area.GRANT,
            title="x",
            due_date=TODAY + timedelta(days=10),
            offsets=[(1, "week")],
            today=TODAY,
        )


@pytest.mark.django_db
def test_lab_reminder_notifies_every_lab_member() -> None:
    lab = Lab.objects.create(name="Lab", slug="lab")
    members = [User.objects.create_user(f"m{i}") for i in range(3)]
    for m in members:
        LabMembership.objects.create(user=m, lab=lab)
    create_subscription(
        target_lab=lab,
        deadline_kind=_Kind.APPLICATION,
        area=_Area.GRANT,
        title="Lab grant",
        due_date=TODAY + timedelta(days=7),
        offsets=[(1, "week")],
        today=TODAY,
    )
    result = run_tick(TODAY)
    assert result.notifications == 3
    assert Notification.objects.count() == 3
