"""Two reminders on two rounds of the same conference.

The requirement this whole schema change exists for. Before it, the uniqueness
tuple was ``(target, content, deadline_kind)``, so a second reminder on a second
paper deadline was not a new subscription — it silently *reconfigured* the first
one, and the reader ended up with one reminder where they had asked for two.
"""

from __future__ import annotations

from datetime import date

import pytest
from django.contrib.auth.models import User
from tools.retrieval.deadlines_projection import rebuild_deadlines_for
from tools.retrieval.models import (
    ContentDeadline,
    ContentItem,
    ReminderSubscription,
    SavedOpportunity,
)

from apps.content.reminders import (
    create_or_update_subscription,
    reminder_copy,
    resync_snapshot,
)

pytestmark = pytest.mark.django_db

TODAY = "2026-08-17"
_Area = SavedOpportunity.Area
_Kind = SavedOpportunity.DeadlineKind


def _structured(kind: str, instant: str, round_label: str = "") -> dict:
    return {
        "kind": kind,
        "raw": instant,
        "instant": instant,
        "basis": "AoE",
        "round_label": round_label,
        "source": "conf:ccf_deadlines",
        "is_estimated": False,
        "extension_count": 0,
    }


@pytest.fixture
def conference() -> ContentItem:
    """A venue shaped like the ones the requirement names: a workshop deadline,
    two full-paper rounds, and the event itself."""
    item = ContentItem.objects.create(
        type=ContentItem.Type.CONFERENCE,
        source="conf:ccf_deadlines",
        external_id="multi-round",
        metadata={
            "name": "A Venue With Several Deadlines",
            "prune_after": "2027-03-20",
            "event_start": "2027-03-14",
            "deadlines_structured": [
                _structured("submission", "2026-10-01T23:59:00Z", "workshop track"),
                _structured("submission", "2026-11-15T23:59:00Z", "round 1"),
                _structured("submission", "2027-01-15T23:59:00Z", "round 2"),
                _structured("abstract", "2026-09-20T23:59:00Z"),
            ],
        },
    )
    rebuild_deadlines_for(item, TODAY, detect_changes=False)
    return item


def _subscribe(user, item, row) -> ReminderSubscription:
    sub, _ = create_or_update_subscription(
        target_user=user,
        content=item,
        deadline_kind=row.kind,
        deadline_round_key=row.round_key,
        area=_Area.CONFERENCE,
        title="A Venue With Several Deadlines",
        round_label=row.round_label,
        due_date=row.due_date,
        offsets=[(1, "week")],
        today=date.fromisoformat(TODAY),
    )
    return sub


def test_every_round_gets_its_own_addressable_row(conference):
    rows = list(conference.deadline_rows.all())
    assert len(rows) == 5  # three paper rounds, one abstract, one event

    manuscript = {r.round_label: r for r in rows if r.kind == _Kind.MANUSCRIPT}
    assert set(manuscript) == {"workshop track", "round 1", "round 2"}
    assert manuscript["round 2"].due_date.isoformat() == "2027-01-15"
    # Only the earliest of them is the headline deadline.
    assert manuscript["workshop track"].is_next is True
    assert manuscript["round 2"].is_next is False


def test_two_rounds_of_one_kind_hold_two_independent_reminders(conference):
    user = User.objects.create_user("rounds")
    rows = {r.round_label: r for r in conference.deadline_rows.all()}

    first = _subscribe(user, conference, rows["round 1"])
    second = _subscribe(user, conference, rows["round 2"])

    assert first.id != second.id
    assert ReminderSubscription.objects.filter(target_user=user).count() == 2
    assert first.due_date.isoformat() == "2026-11-15"
    assert second.due_date.isoformat() == "2027-01-15"


def test_a_repeat_on_the_same_round_still_reconfigures_rather_than_duplicating(
    conference,
):
    """Widening the key must not lose the behaviour it was widened from."""
    user = User.objects.create_user("repeat")
    row = {r.round_label: r for r in conference.deadline_rows.all()}["round 1"]

    first = _subscribe(user, conference, row)
    again = _subscribe(user, conference, row)

    assert first.id == again.id
    assert ReminderSubscription.objects.filter(target_user=user).count() == 1


def test_a_fired_message_names_which_deadline_it_is_about(conference):
    """"Manuscript due Jan 15" is ambiguous on a venue with three of them."""
    user = User.objects.create_user("copy")
    row = {r.round_label: r for r in conference.deadline_rows.all()}["round 2"]
    sub = _subscribe(user, conference, row)

    _title, body = reminder_copy(sub, row.due_date, 14)
    assert "round 2" in body
    assert "14 days left" in body


def test_an_alert_can_concern_the_conference_itself(conference):
    user = User.objects.create_user("event")
    event = conference.deadline_rows.get(kind=_Kind.EVENT)
    sub = _subscribe(user, conference, event)

    assert sub.due_date.isoformat() == "2027-03-14"
    _title, body = reminder_copy(sub, event.due_date, 30)
    assert body.startswith("Conference due")


def test_a_reminder_follows_its_own_round_when_that_round_moves(conference):
    """The stability property ``round_key`` exists for.

    The key is the collector's ``(kind, label)`` identity and deliberately not
    the date, so an extension updates the round in place. The reminder must
    re-sync to the *new* date of the round it was set on — not silently
    re-point at whichever round is now nearest.
    """
    user = User.objects.create_user("moved")
    rows = {r.round_label: r for r in conference.deadline_rows.all()}
    sub = _subscribe(user, conference, rows["round 2"])

    conference.metadata["deadlines_structured"] = [
        _structured("submission", "2026-10-01T23:59:00Z", "workshop track"),
        _structured("submission", "2026-11-15T23:59:00Z", "round 1"),
        _structured("submission", "2027-02-28T23:59:00Z", "round 2"),  # extended
        _structured("abstract", "2026-09-20T23:59:00Z"),
    ]
    conference.save(update_fields=["metadata"])
    changes = rebuild_deadlines_for(conference, TODAY)

    assert [(c.kind, c.round_key) for c in changes] == [
        (_Kind.MANUSCRIPT, "submission:round 2")
    ]
    resync_snapshot(sub)
    sub.refresh_from_db()
    assert sub.due_date.isoformat() == "2027-02-28"
    # And the row it points at is still the same row, not a replacement.
    assert ContentDeadline.objects.filter(
        content=conference, kind=_Kind.MANUSCRIPT, round_key="submission:round 2"
    ).count() == 1


def test_a_round_that_passes_stops_being_addressable(conference):
    """Specs only ever cover future dates, so a passed round's row is removed —
    the same way the old per-kind row moved on once its date went by."""
    rebuild_deadlines_for(conference, "2026-12-01", detect_changes=False)
    labels = {r.round_label for r in conference.deadline_rows.all()}
    assert "workshop track" not in labels
    assert {"round 1", "round 2"} <= labels or "round 2" in labels
