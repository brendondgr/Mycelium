"""Attention share: which project a person is actually spending time on.

Plan 03's acceptance criterion — attention over a fixture week matches the hand
count — plus the three things left out of it on purpose: unresolved messages,
repeats, and Mylo's own lines.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from apps.accounts.models import Lab
from apps.ambient import attention, read, retention
from apps.ambient.models import PlaceKind, ProjectAttention, RawMessageRef, Source
from apps.research.models import Project


@pytest.fixture
def lab(db):
    return Lab.objects.create(name="PULSE", slug="pulse")


@pytest.fixture
def source(lab):
    return Source.objects.create(
        kind=Source.Kind.DISCORD_GUILD,
        external_id="g",
        lab=lab,
        consent_state=Source.Consent.ACTIVE,
    )


@pytest.fixture
def ada(db):
    return User.objects.create_user("ada", "ada@example.org", "pw")


@pytest.fixture
def projects(lab):
    return (
        Project.objects.create(name="Imaging", scope_lab=lab),
        Project.objects.create(name="Annotation", scope_lab=lab),
    )


_counter = iter(range(10_000))


def _msg(source, speaker, project, *, days_ago, repeat_of=None, deleted=False):
    return RawMessageRef.objects.create(
        source=source,
        external_id=f"m{next(_counter)}",
        place_kind=PlaceKind.CHANNEL,
        speaker=speaker,
        speaker_kind="linked" if speaker else "mylo",
        sent_at=timezone.now() - timedelta(days=days_ago, hours=1),
        project=project,
        project_confidence=1.0 if project else 0.0,
        repeat_of=repeat_of,
        deleted_at=timezone.now() if deleted else None,
    )


def _share(user, project):
    return ProjectAttention.objects.get(user=user, project=project)


def test_a_fixture_week_matches_the_hand_count(source, ada, projects):
    imaging, annotation = projects
    # This week: 6 on imaging, 2 on annotation. Earlier this month: 4 more on
    # annotation. By hand: 7-day 6/8 and 2/8; 28-day 6/12 and 6/12.
    for _ in range(6):
        _msg(source, ada, imaging, days_ago=2)
    for _ in range(2):
        _msg(source, ada, annotation, days_ago=3)
    for _ in range(4):
        _msg(source, ada, annotation, days_ago=20)

    attention.recompute()

    assert _share(ada, imaging).share_7d == pytest.approx(0.75)
    assert _share(ada, annotation).share_7d == pytest.approx(0.25)
    assert _share(ada, imaging).share_28d == pytest.approx(0.5)
    assert _share(ada, annotation).share_28d == pytest.approx(0.5)
    assert _share(ada, imaging).messages_7d == 6
    assert _share(ada, annotation).messages_28d == 6


def test_unresolved_messages_are_not_time_spent_on_nothing(source, ada, projects):
    imaging, _ = projects
    _msg(source, ada, imaging, days_ago=1)
    for _ in range(9):
        _msg(source, ada, None, days_ago=1)
    attention.recompute()
    assert _share(ada, imaging).share_7d == pytest.approx(1.0)


def test_one_thought_pasted_three_times_is_one_piece_of_attention(
    source, ada, projects
):
    imaging, annotation = projects
    original = _msg(source, ada, imaging, days_ago=1)
    _msg(source, ada, imaging, days_ago=1, repeat_of=original)
    _msg(source, ada, imaging, days_ago=1, repeat_of=original)
    _msg(source, ada, annotation, days_ago=1)
    attention.recompute()
    assert _share(ada, imaging).share_7d == pytest.approx(0.5)


def test_deleted_messages_and_mylos_lines_do_not_count(source, ada, projects):
    imaging, annotation = projects
    _msg(source, ada, imaging, days_ago=1)
    _msg(source, ada, annotation, days_ago=1, deleted=True)
    _msg(source, None, annotation, days_ago=1)
    attention.recompute()
    assert _share(ada, imaging).share_7d == pytest.approx(1.0)
    assert not ProjectAttention.objects.filter(project=annotation).exists()


def test_a_project_nobody_has_mentioned_in_four_weeks_drops_off(
    source, ada, projects
):
    imaging, annotation = projects
    _msg(source, ada, annotation, days_ago=1)
    attention.recompute()
    RawMessageRef.objects.all().delete()
    _msg(source, ada, imaging, days_ago=1)
    attention.recompute()
    assert list(read.attention_for(ada).values_list("project__name", flat=True)) == [
        "Imaging"
    ]


def test_an_older_project_keeps_its_month_and_loses_its_week(source, ada, projects):
    imaging, annotation = projects
    _msg(source, ada, imaging, days_ago=1)
    _msg(source, ada, annotation, days_ago=15)
    attention.recompute()
    assert _share(ada, annotation).share_7d == 0.0
    assert _share(ada, annotation).share_28d == pytest.approx(0.5)


def test_attention_is_per_person(source, ada, projects):
    imaging, annotation = projects
    bo = User.objects.create_user("bo", "bo@example.org", "pw")
    _msg(source, ada, imaging, days_ago=1)
    _msg(source, bo, annotation, days_ago=1)
    attention.recompute()
    assert _share(ada, imaging).share_7d == 1.0
    assert _share(bo, annotation).share_7d == 1.0
    assert not ProjectAttention.objects.filter(user=ada, project=annotation).exists()


def test_references_outlive_the_attention_window(settings):
    settings.AMBIENT_REF_RETENTION_DAYS = 7
    settings.AMBIENT_REPEAT_WINDOW_DAYS = 3
    assert retention.ref_retention_days() == attention.LONG_DAYS + 1
