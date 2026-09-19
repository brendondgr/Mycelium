"""Ambient Plan 06, delivered: tonight's questions go out as DMs with their
buttons at the person's send hour and appear on the bell; a confirmed change
that took effect is announced once."""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.utils import timezone

from apps.ambient.models import PendingSuggestion
from apps.content.models import Notification
from apps.integrations.models import DiscordOutboxMessage


@pytest.fixture
def ada(db):
    return User.objects.create_user("ada", "ada@example.org", "pw")


def _suggestion(user, **kwargs):
    defaults = {
        "kind": "interest",
        "topic": "conformal prediction",
        "explanation": "You brought this up on two days in the last two weeks.",
        "choices": [
            {"key": "reports", "label": "Include it in my reports"},
            {"key": "no", "label": "No, and don't ask about this"},
        ],
        "expires_at": timezone.now() + timedelta(days=14),
    }
    return PendingSuggestion.objects.create(user=user, **{**defaults, **kwargs})


def test_a_question_goes_out_with_buttons_and_rings_the_bell(ada):
    s = _suggestion(ada)
    call_command("deliver_ambient_questions")
    row = DiscordOutboxMessage.objects.get()
    assert row.kind == "ambient_question" and row.recipient_user == ada
    assert (row.subject_type, row.subject_id) == ("ambient_suggestion", str(s.pk))
    assert "Shall I" in row.content
    buttons = row.components[0]["components"]
    assert [b["custom_id"] for b in buttons] == [
        f"ambient:{s.pk}:reports",
        f"ambient:{s.pk}:no",
    ]
    bell = Notification.objects.get()
    assert bell.kind == "suggestion_pending" and "conformal prediction" in bell.title
    s.refresh_from_db()
    assert s.state == "asked" and s.asked_at is not None
    call_command("deliver_ambient_questions")  # nothing twice
    assert DiscordOutboxMessage.objects.count() == 1


def test_a_confirmed_change_is_announced_once(ada):
    now = timezone.now()
    _suggestion(
        ada, state="answered", verdict="confirmed", choice="reports", applied_at=now
    )
    _suggestion(
        ada,
        topic="kriging",
        state="answered",
        verdict="rejected",
        choice="no",
        applied_at=now,
    )
    call_command("deliver_ambient_questions")
    bells = Notification.objects.filter(kind="change_applied")
    assert [b.title for b in bells] == [
        "conformal prediction is now in your reports — you confirmed it"
    ]
    call_command("deliver_ambient_questions")
    assert Notification.objects.filter(kind="change_applied").count() == 1
