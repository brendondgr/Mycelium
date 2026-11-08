"""R6 — DEADLINE_MOVED announcements.

Feeds off the R0 change signal (changed_at + previous_due_date / previous_confidence)
and delivers a change notice on the reminder's own channel. Discord mocked.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from apps.accounts.models import Lab, LabMembership
from apps.billing.testing import entitle_lab, paid_plan
from apps.integrations.services import discord_api, outbox
from apps.integrations.services.discord_api import RawResponse
from apps.integrations.testing import bind
from django.contrib.auth.models import User

from tools.delivery.models import Notification, SavedOpportunity
from tools.delivery.reminders import create_subscription
from tools.delivery.reminders_announce import announce_deadline_changes
from tools.retrieval.deadlines_projection import rebuild_deadlines_for
from tools.retrieval.models import ContentDeadline, ContentItem

TODAY = date(2026, 9, 5)
NOW = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
_Kind = SavedOpportunity.DeadlineKind
_Area = SavedOpportunity.Area
_Conf = ContentDeadline.Confidence


@pytest.fixture
def user(db):
    person = User.objects.create_user("announce-user")
    paid_plan(person)  # change notices ride the same paid Discord path as reminders
    return person


def _content(due, *, confidence=_Conf.CONFIRMED):
    item = ContentItem.objects.create(
        type=ContentItem.Type.GRANT,
        source="pivot",
        external_id=f"g-{due}",
        metadata={"title": "Grant", "deadline_date": due.isoformat()},
    )
    ContentDeadline.objects.create(
        content=item, kind=_Kind.APPLICATION, due_date=due, confidence=confidence
    )
    return item


def _personal_sub(user, item, due):
    return create_subscription(
        target_user=user,
        content=item,
        deadline_kind=_Kind.APPLICATION,
        area=_Area.GRANT,
        title="Grant",
        due_date=due,
        offsets=[(1, "week")],
        today=TODAY,
    )


def _mark_moved(
    item, *, new_due, old_due, old_conf=_Conf.CONFIRMED, new_conf=_Conf.CONFIRMED
):
    row = item.deadline_rows.get()
    row.due_date = new_due
    row.previous_due_date = old_due
    row.confidence = new_conf
    row.previous_confidence = old_conf
    row.changed_at = NOW
    row.save()


@pytest.mark.django_db
def test_moved_deadline_announces_with_from_to_and_days(user) -> None:
    item = _content(date(2026, 11, 12))
    _personal_sub(user, item, date(2026, 11, 12))
    _mark_moved(item, new_due=date(2026, 10, 15), old_due=date(2026, 11, 12))

    result = announce_deadline_changes(TODAY, now=NOW)
    assert result.announced == 1
    note = Notification.objects.get(kind=Notification.Kind.DEADLINE_MOVED)
    assert note.user == user
    assert "moved from Nov 12 to Oct 15" in note.body
    assert "40 days left" in note.body  # Oct 15 − Sep 5


@pytest.mark.django_db
def test_anticipated_confirmed_reads_now_confirmed(user) -> None:
    item = _content(date(2026, 10, 15), confidence=_Conf.ANTICIPATED)
    _personal_sub(user, item, date(2026, 10, 15))
    # Same date, but the anticipated deadline became confirmed.
    _mark_moved(
        item,
        new_due=date(2026, 10, 15),
        old_due=None,
        old_conf=_Conf.ANTICIPATED,
        new_conf=_Conf.CONFIRMED,
    )

    announce_deadline_changes(TODAY, now=NOW)
    note = Notification.objects.get(kind=Notification.Kind.DEADLINE_MOVED)
    assert "now confirmed" in note.body
    assert "Oct 15" in note.body


@pytest.mark.django_db
def test_announce_is_idempotent_per_move(user) -> None:
    item = _content(date(2026, 11, 12))
    _personal_sub(user, item, date(2026, 11, 12))
    _mark_moved(item, new_due=date(2026, 10, 15), old_due=date(2026, 11, 12))

    assert announce_deadline_changes(TODAY, now=NOW).announced == 1
    assert announce_deadline_changes(TODAY, now=NOW).announced == 0  # rate-limited
    moved = Notification.objects.filter(kind=Notification.Kind.DEADLINE_MOVED)
    assert moved.count() == 1


@pytest.mark.django_db
def test_no_change_no_announcement(user) -> None:
    item = _content(date(2026, 11, 12))
    _personal_sub(user, item, date(2026, 11, 12))  # changed_at stays null
    assert announce_deadline_changes(TODAY, now=NOW).announced == 0


@pytest.mark.django_db
def test_stale_change_outside_window_not_announced(user) -> None:
    item = _content(date(2026, 11, 12))
    _personal_sub(user, item, date(2026, 11, 12))
    row = item.deadline_rows.get()
    row.due_date = date(2026, 10, 15)
    row.previous_due_date = date(2026, 11, 12)
    row.changed_at = NOW - timedelta(days=3)  # older than the window
    row.save()
    assert announce_deadline_changes(TODAY, now=NOW).announced == 0


@pytest.mark.django_db
def test_rebuild_move_then_announce_integration(user) -> None:
    from django.utils import timezone

    item = _content(date(2026, 11, 12))
    _personal_sub(user, item, date(2026, 11, 12))
    # A re-scrape moves the date; the R0 rebuild stamps changed_at with the real
    # clock, so this test uses the real now/today for the announce window too.
    item.metadata["deadline_date"] = "2026-10-15"
    item.save(update_fields=["metadata"])
    now = timezone.now()
    changes = rebuild_deadlines_for(item, now.date().isoformat())
    assert len(changes) == 1

    result = announce_deadline_changes()  # real now/today
    assert result.announced == 1
    assert "moved from Nov 12 to Oct 15" in Notification.objects.get(
        kind=Notification.Kind.DEADLINE_MOVED
    ).body


# --------------------------------------------------------------------------- #
# Lab announcement goes to the channel
# --------------------------------------------------------------------------- #


class _Transport:
    def __init__(self):
        self.calls: list[dict] = []
        self.message = RawResponse(200, {"id": "m"})

    def __call__(self, method, path, *, auth=None, json_body=None, **kwargs):
        self.calls.append({"method": method, "path": path, "json_body": json_body})
        if path.endswith("/messages"):
            return self.message
        return RawResponse(404, {})


@pytest.fixture
def transport(monkeypatch, settings):
    settings.DISCORD_BOT_TOKEN = "t"
    stub = _Transport()
    monkeypatch.setattr(discord_api, "_request", stub)
    return stub


@pytest.mark.django_db
def test_lab_deadline_move_posts_to_channel(transport) -> None:
    lab = Lab.objects.create(name="Lab", slug="lab")
    bind(lab=lab, state="pending_setup", guild_id="g1", deadlines="chan-1")
    entitle_lab(lab)  # a lab off-plan is not posted to at all
    LabMembership.objects.create(user=User.objects.create_user("m"), lab=lab)
    item = _content(date(2026, 11, 12))
    create_subscription(
        target_lab=lab,
        content=item,
        deadline_kind=_Kind.APPLICATION,
        area=_Area.GRANT,
        title="Grant",
        due_date=date(2026, 11, 12),
        offsets=[(1, "week")],
        today=TODAY,
    )
    _mark_moved(item, new_due=date(2026, 10, 15), old_due=date(2026, 11, 12))

    result = announce_deadline_changes(TODAY, now=NOW)
    assert result.announced == 1
    outbox.drain()
    posts = [c for c in transport.calls if c["path"].endswith("/messages")]
    assert posts[0]["path"] == "/channels/chan-1/messages"
    assert posts[0]["json_body"]["allowed_mentions"] == {"parse": []}
