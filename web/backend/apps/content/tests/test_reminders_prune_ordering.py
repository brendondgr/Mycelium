"""R2 — job ordering + the prune → reminder-stale hook.

The daily chain must run the tick before prune so a moved deadline is seen live; the
pre_delete hook is the backstop that stops a reminder firing on an orphaned snapshot.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.contrib.auth.models import User

from apps.content import reminders
from apps.content.models import (
    ContentDeadline,
    ContentItem,
    Notification,
    ReminderSubscription,
    SavedOpportunity,
)
from apps.content.reminders import create_subscription
from apps.content.reminders_tick import run_tick

TODAY = date(2026, 7, 16)
_Kind = SavedOpportunity.DeadlineKind
_Area = SavedOpportunity.Area
_State = ReminderSubscription.State


@pytest.fixture
def user(db):
    return User.objects.create_user("prune-user")


@pytest.fixture(autouse=True)
def pinned_prune_clock(monkeypatch):
    """Pin the prune → stale hook's wall clock to ``TODAY`` for this whole module.

    The hook runs from a ``pre_delete`` receiver, which cannot be handed a reference
    date and so reads ``reminders.reference_today()``. Every deadline here is anchored
    to ``TODAY``; leaving this one on the real clock made the module's verdict depend
    on the day it was run, and two tests here duly went red once the wall clock passed
    ``TODAY + 7 days``.
    """
    monkeypatch.setattr(reminders, "reference_today", lambda: TODAY)


def _content_with_deadline(due: date):
    item = ContentItem.objects.create(
        type=ContentItem.Type.GRANT,
        source="pivot",
        external_id=f"g-{due}",
        metadata={"title": "Grant", "prune_after": due.isoformat()},
    )
    ContentDeadline.objects.create(
        content=item,
        kind=_Kind.APPLICATION,
        due_date=due,
        confidence=ContentDeadline.Confidence.CONFIRMED,
    )
    return item


def _subscribe(user, content, due):
    return create_subscription(
        target_user=user,
        content=content,
        deadline_kind=_Kind.APPLICATION,
        area=_Area.GRANT,
        title="Grant",
        due_date=due,
        offsets=[(1, "week")],
        today=TODAY,
    )


@pytest.mark.django_db
def test_deadline_moved_earlier_prunes_item_and_marks_subscription_stale(user) -> None:
    content = _content_with_deadline(TODAY + timedelta(days=30))
    sub = _subscribe(user, content, TODAY + timedelta(days=30))

    # Deadline jumps earlier, into the past; the projection is rebuilt to match.
    row = content.deadline_rows.get()
    row.due_date = TODAY - timedelta(days=5)
    row.save(update_fields=["due_date"])

    content.delete()  # the daily prune deletes the now-expired item

    sub.refresh_from_db()
    assert sub.state == _State.STALE
    assert sub.content_id is None
    # And it never fires on the old (later) snapshot date.
    assert run_tick(TODAY).notifications == 0
    assert Notification.objects.count() == 0


@pytest.mark.django_db
def test_item_pruned_with_future_deadline_still_fires_from_snapshot(user) -> None:
    content = _content_with_deadline(TODAY + timedelta(days=7))
    sub = _subscribe(user, content, TODAY + timedelta(days=7))

    content.delete()  # deleted for a non-deadline reason; deadline still upcoming

    sub.refresh_from_db()
    assert sub.state == _State.ACTIVE  # future deadline → survives on snapshot
    assert sub.content_id is None
    assert sub.due_date == TODAY + timedelta(days=7)
    assert run_tick(TODAY).notifications == 1


@pytest.mark.django_db
def test_delete_with_missing_projection_row_marks_stale(user) -> None:
    content = _content_with_deadline(TODAY + timedelta(days=30))
    sub = _subscribe(user, content, TODAY + timedelta(days=30))
    content.deadline_rows.all().delete()  # projection row gone before the item

    content.delete()

    sub.refresh_from_db()
    assert sub.state == _State.STALE


def test_tick_runs_before_prune_in_the_daily_chain() -> None:
    """Assert the ordering config, not just the behavior.

    The nightly stages are declared per tool and assembled by
    ``tools._framework.nightly``; this reads the assembled plan, which is what
    ``ops/nightly/manual_all.py`` runs.
    """
    from tools._framework import nightly

    planned = nightly.as_tuples(nightly.plan_for()[0])
    names = [command for command, _args, _intro in planned]
    watched = ("run_daily_opportunities", "run_reminder_tick", "prune_opportunities")
    order = [name for name in names if name in watched]
    assert order == [
        "run_daily_opportunities",
        "run_reminder_tick",
        "prune_opportunities",
    ]
    # Opportunities must ingest without pruning so the tick sees live deadlines.
    args = dict((command, a) for command, a, _intro in planned)
    assert "--no-prune" in args["run_daily_opportunities"]
