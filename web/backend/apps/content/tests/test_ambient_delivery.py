"""Ambient Plan 06, delivered: tonight's questions go out as DMs with their
buttons at the person's send hour and appear on the bell; a confirmed change
that took effect is announced once."""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.utils import timezone
from tools.retrieval.models import Notification

from apps.ambient.models import PendingSuggestion
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


def test_a_fact_told_to_mylo_is_echoed_once_and_an_undone_one_is_not(ada):
    from apps.ambient.models import AppliedChange
    from apps.research.models import Project

    project = Project.objects.create(name="Imaging pipeline", scope_user=ada)
    AppliedChange.objects.create(
        user=ada,
        project=project,
        kind="development_recorded",
        topic="annotation budget came through",
        surface="told",
    )
    AppliedChange.objects.create(
        user=ada,
        project=project,
        kind="development_recorded",
        topic="dropped the GNN baseline",
        surface="told",
        undone_at=timezone.now(),
    )
    call_command("deliver_ambient_questions")
    [bell] = Notification.objects.filter(kind="change_applied")
    assert bell.title.startswith("Noted on Imaging pipeline: annotation budget")
    assert bell.url == "/app/mylo-and-you"
    call_command("deliver_ambient_questions")
    assert Notification.objects.filter(kind="change_applied").count() == 1


def test_a_profile_edit_is_announced_in_its_own_words(ada):
    _suggestion(
        ada,
        state="answered",
        verdict="confirmed",
        choice="skill",
        applied_at=timezone.now(),
    )
    call_command("deliver_ambient_questions")
    [bell] = Notification.objects.filter(kind="change_applied")
    assert bell.title == "conformal prediction is now in your skills — you said yes"


def test_an_announcement_uses_the_persons_wording(ada):
    _suggestion(
        ada,
        state="answered",
        verdict="corrected",
        choice="skill",
        correction="conformal inference",
        applied_at=timezone.now(),
    )
    call_command("deliver_ambient_questions")
    [bell] = Notification.objects.filter(kind="change_applied")
    assert bell.title.startswith("conformal inference is now in your skills")


def test_everyone_named_in_a_meeting_is_told_once(ada):
    from apps.ambient.models import Source, TranscriptMeeting

    bo = User.objects.create_user("bo", "bo@example.org", "pw")
    source = Source.objects.create(kind="transcript", external_id="meeting:1")
    TranscriptMeeting.objects.create(
        source=source,
        organiser=ada,
        title="Imaging sync",
        occurred_at=timezone.now(),
        participant_ids=[ada.pk, bo.pk],
    )
    call_command("deliver_ambient_questions")
    call_command("deliver_ambient_questions")
    bells = Notification.objects.filter(title__startswith="Mylo read the meeting")
    assert sorted(b.user_id for b in bells) == sorted([ada.pk, bo.pk])
    assert TranscriptMeeting.objects.get().announced_at is not None
