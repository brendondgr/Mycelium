"""When Mylo interrupts someone, and how hard it is for it to do so twice.

An alert is a much stronger claim than a recommendation: not "this is relevant"
but "something happened to **this project** and here is what to do". Everything
in these tests is about keeping that claim true — the once-ever rule, the daily
cap, the calibration gate, and the two triggers that are arithmetic and therefore
do not wait for it.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from tools.retrieval.models import (
    ContentDeadline,
    ContentItem,
    Notification,
    ProjectAlert,
    SavedOpportunity,
)

from apps.accounts.models import Lab, WatchPreference
from apps.content import alerts as alert_engine
from apps.content.alert_report import (
    attention_section,
    block_for,
    notify,
    open_alerts,
)
from apps.research.models import Project, ProjectState

TODAY = date(2026, 9, 11)
# Named weekdays, because the urgent-alert rule is entirely about which day it
# is and a test that asked the clock would pass on Tuesday and fail on Monday.
TUESDAY = date(2026, 9, 22)
SATURDAY = date(2026, 9, 26)


def _item(title: str, ctype: str = ContentItem.Type.PAPER) -> ContentItem:
    return ContentItem.objects.create(
        type=ctype,
        source="test",
        external_id=title,
        source_url=f"https://example.org/{title.replace(' ', '-')}",
        metadata={"title": title},
    )


@pytest.fixture
def owner(db) -> User:
    user = User.objects.create_user("owner", password="p")
    WatchPreference.objects.create(user=user, categories=["papers"])
    return user


@pytest.fixture
def project(owner: User) -> Project:
    project = Project.objects.create(name="Synapse", scope_user=owner)
    ProjectState.objects.create(project=project).apply(
        {
            "slow": {
                "claimed_contribution": "A measurement-validity study",
                "blockers": [{"text": "No labeled evaluation set"}],
            },
            "fast": {
                "milestones": [
                    {
                        "kind": "draft_by",
                        "what": "paper draft",
                        "date": "2026-10-09",
                    }
                ]
            },
        }
    ).save()
    project.refresh_from_db()
    return project


def _candidate(project, content, trigger, **evidence) -> alert_engine.Candidate:
    return alert_engine.Candidate(
        project=project, content=content, trigger=trigger, evidence=evidence
    )


# --------------------------------------------------------------------------- #
# Firing once, and only once
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_alert_fires_once_per_target_project_item_trigger(
    owner: User, project: Project
) -> None:
    """News the morning it is found; noise every morning after."""
    content = _item("A paper")
    candidate = _candidate(
        project, content, ProjectAlert.Trigger.TIMELINE, due_date="2026-11-13"
    )

    first = alert_engine.persist([candidate], {"target_user": owner}, today=TODAY)
    second = alert_engine.persist(
        [candidate], {"target_user": owner}, today=TODAY + timedelta(days=1)
    )

    assert (first.fired, second.fired) == (1, 0)
    assert second.duplicates == 1
    assert ProjectAlert.objects.count() == 1


@pytest.mark.django_db
def test_the_same_item_can_fire_for_two_different_triggers(
    owner: User, project: Project
) -> None:
    """A paper that both overlaps and unblocks is two pieces of news."""
    content = _item("A paper")

    alert_engine.persist(
        [
            _candidate(project, content, ProjectAlert.Trigger.TIMELINE),
            _candidate(project, content, ProjectAlert.Trigger.DEADLINE_MOVED, days=2),
        ],
        {"target_user": owner},
        today=TODAY,
    )

    assert ProjectAlert.objects.count() == 2


@pytest.mark.django_db
def test_daily_alert_cap_holds_overflow_for_monday(
    owner: User, project: Project
) -> None:
    """Four things that all need attention today is a reader who attends to none.

    Held, not dropped: the Monday weekly picks them up, so nothing is lost — it
    is just not shouted.
    """
    candidates = [
        _candidate(project, _item(f"Paper {n}"), ProjectAlert.Trigger.TIMELINE)
        for n in range(6)
    ]

    run = alert_engine.persist(candidates, {"target_user": owner}, today=TODAY, cap=3)

    assert run.fired == 3
    assert run.held == 3
    assert ProjectAlert.objects.filter(status=ProjectAlert.Status.HELD).count() == 3


# --------------------------------------------------------------------------- #
# The calibration gate (plan 3.8)
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_arithmetic_triggers_fire_before_any_calibration(
    owner: User, project: Project, settings
) -> None:
    """A date is a date. Nothing about it needs measuring first."""
    settings.PROJECT_ALERTS_ENABLED = False

    run = alert_engine.persist(
        [
            _candidate(project, _item("Venue"), ProjectAlert.Trigger.TIMELINE),
            _candidate(
                project, _item("Grant"), ProjectAlert.Trigger.DEADLINE_MOVED, days=3
            ),
        ],
        {"target_user": owner},
        today=TODAY,
    )

    assert run.fired == 2
    assert run.skipped_disabled == 0


@pytest.mark.django_db
def test_similarity_triggers_wait_for_their_thresholds(
    owner: User, project: Project, settings
) -> None:
    """A threshold set by taste fires constantly or never; both lose the reader."""
    settings.PROJECT_ALERTS_ENABLED = False

    run = alert_engine.persist(
        [
            _candidate(project, _item("A"), ProjectAlert.Trigger.OVERLAP_RISK),
            _candidate(project, _item("B"), ProjectAlert.Trigger.UNBLOCKS),
            _candidate(project, _item("C"), ProjectAlert.Trigger.TEAM_GAP),
        ],
        {"target_user": owner},
        today=TODAY,
    )

    assert run.fired == 0
    assert run.skipped_disabled == 3
    assert ProjectAlert.objects.count() == 0

    settings.PROJECT_ALERTS_ENABLED = True
    enabled = alert_engine.persist(
        [_candidate(project, _item("D"), ProjectAlert.Trigger.OVERLAP_RISK)],
        {"target_user": owner},
        today=TODAY,
    )
    assert enabled.fired == 1


# --------------------------------------------------------------------------- #
# Priority
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_the_cap_spends_its_budget_on_the_time_critical_first(
    owner: User, project: Project, settings
) -> None:
    settings.PROJECT_ALERTS_ENABLED = True
    candidates = [
        _candidate(project, _item("Gap"), ProjectAlert.Trigger.TEAM_GAP),
        _candidate(project, _item("Venue"), ProjectAlert.Trigger.TIMELINE),
        _candidate(
            project, _item("Moved"), ProjectAlert.Trigger.DEADLINE_MOVED, days=2
        ),
        _candidate(
            project, _item("Overlap"), ProjectAlert.Trigger.OVERLAP_RISK, score=0.9
        ),
    ]

    alert_engine.persist(candidates, {"target_user": owner}, today=TODAY, cap=2)

    fired = set(
        ProjectAlert.objects.filter(status=ProjectAlert.Status.OPEN).values_list(
            "trigger", flat=True
        )
    )
    assert fired == {
        ProjectAlert.Trigger.DEADLINE_MOVED,
        ProjectAlert.Trigger.OVERLAP_RISK,
    }


@pytest.mark.django_db
def test_a_sooner_deadline_outranks_a_later_one(
    owner: User, project: Project
) -> None:
    candidates = [
        _candidate(
            project, _item("Later"), ProjectAlert.Trigger.DEADLINE_MOVED, days=12
        ),
        _candidate(
            project, _item("Sooner"), ProjectAlert.Trigger.DEADLINE_MOVED, days=2
        ),
    ]

    ranked = alert_engine.rank_candidates(candidates)

    assert [c.content.metadata["title"] for c in ranked] == ["Sooner", "Later"]


# --------------------------------------------------------------------------- #
# A moved deadline
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_only_a_deadline_that_actually_moved_counts(
    owner: User, project: Project
) -> None:
    """Narrow on purpose: this is the one alert allowed between Mondays."""
    moved = _item("Moved grant", ContentItem.Type.GRANT)
    steady = _item("Steady grant", ContentItem.Type.GRANT)
    ContentDeadline.objects.create(
        content=moved,
        kind=SavedOpportunity.DeadlineKind.APPLICATION,
        due_date=TODAY + timedelta(days=6),
        previous_due_date=TODAY + timedelta(days=40),
        changed_at=timezone.now(),
        confidence=ContentDeadline.Confidence.CONFIRMED,
    )
    ContentDeadline.objects.create(
        content=steady,
        kind=SavedOpportunity.DeadlineKind.APPLICATION,
        due_date=TODAY + timedelta(days=6),
        changed_at=timezone.now(),
        confidence=ContentDeadline.Confidence.CONFIRMED,
    )

    found = alert_engine.deadline_moved_candidates(
        project, [moved.id, steady.id], buffer_days=14, today=TODAY
    )

    assert [candidate.content.id for candidate in found] == [moved.id]
    assert found[0].evidence["moved_earlier"] is True


@pytest.mark.django_db
def test_a_deadline_beyond_the_buffer_is_not_urgent(
    owner: User, project: Project
) -> None:
    item = _item("Distant grant", ContentItem.Type.GRANT)
    ContentDeadline.objects.create(
        content=item,
        kind=SavedOpportunity.DeadlineKind.APPLICATION,
        due_date=TODAY + timedelta(days=90),
        previous_due_date=TODAY + timedelta(days=120),
        changed_at=timezone.now(),
        confidence=ContentDeadline.Confidence.CONFIRMED,
    )

    assert (
        alert_engine.deadline_moved_candidates(
            project, [item.id], buffer_days=14, today=TODAY
        )
        == []
    )


# --------------------------------------------------------------------------- #
# What the reader sees
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_the_attention_section_is_written_from_evidence_not_by_a_model(
    owner: User, project: Project
) -> None:
    """Every number in it came from a matcher (plan H2)."""
    content = _item("A venue", ContentItem.Type.CONFERENCE)
    ProjectAlert.objects.create(
        target_user=owner,
        project=project,
        content=content,
        trigger=ProjectAlert.Trigger.TIMELINE,
        fired_on=timezone.localdate(),
        evidence={
            "due_date": "2026-11-13",
            "slack_days": 35,
            "milestone_what": "paper draft",
            "buffer_days": 14,
            "buffer_source": "you",
            "anticipated": True,
        },
    )

    section = attention_section(
        [block_for(alert) for alert in open_alerts({"target_user": owner})]
    )

    assert section.startswith("## Needs your attention")
    assert "### Synapse · fits your timeline" in section
    assert "35 days after paper draft" in section
    assert "projected from the last cycle" in section
    assert "%" not in section


@pytest.mark.django_db
def test_project_alert_notifications_fire_for_every_cadence(
    owner: User, project: Project
) -> None:
    """Cadence governs Discord; the bell is what makes that true (plan 3.7)."""
    ProjectAlert.objects.create(
        target_user=owner,
        project=project,
        content=_item("A paper"),
        trigger=ProjectAlert.Trigger.TIMELINE,
        fired_on=timezone.localdate(),
        evidence={"due_date": "2026-11-13"},
    )
    rows = open_alerts({"target_user": owner})

    assert notify(rows) == 1
    assert notify(rows) == 0  # idempotent — the key mirrors the alert's own

    bell = Notification.objects.get()
    assert bell.kind == Notification.Kind.PROJECT_ALERT
    assert bell.title == "Synapse · fits your timeline"


@pytest.mark.django_db
def test_a_lab_alert_does_not_ring_every_members_bell(db) -> None:
    """One finding ringing eight times is how a bell gets ignored."""
    lab = Lab.objects.create(name="Pulse", slug="pulse")
    project = Project.objects.create(
        name="Ariadne", scope_lab=lab, share_in_lab_reports=True
    )
    ProjectAlert.objects.create(
        target_lab=lab,
        project=project,
        content=_item("A paper"),
        trigger=ProjectAlert.Trigger.TIMELINE,
        fired_on=timezone.localdate(),
    )

    assert notify(open_alerts({"target_lab": lab})) == 0
    assert Notification.objects.count() == 0


# --------------------------------------------------------------------------- #
# The one exception to "weekly means Mondays" (open decision OD2)
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_an_urgent_alert_reaches_only_a_weekly_reader_who_asked_for_it(
    owner: User, project: Project
) -> None:
    """Every clause of the rule is load-bearing, so every clause is checked."""
    from apps.accounts.models import WatchCadence
    from apps.content.urgent_alerts import eligible_alerts

    alert = ProjectAlert.objects.create(
        target_user=owner,
        project=project,
        content=_item("Moved grant", ContentItem.Type.GRANT),
        trigger=ProjectAlert.Trigger.DEADLINE_MOVED,
        fired_on=TUESDAY,
        evidence={"days": 6, "previous_due_date": "2026-10-21",
                  "due_date": "2026-09-17", "moved_earlier": True},
    )

    # Daily cadence: they hear about it in tomorrow's daily, so a second message
    # would be the same news twice.
    assert eligible_alerts(owner, on=TUESDAY) == []

    owner.watch.cadence = WatchCadence.WEEKLY
    owner.watch.save(update_fields=["cadence"])
    owner.refresh_from_db()
    # Weekly, but they never opted in.
    assert eligible_alerts(owner, on=TUESDAY) == []

    owner.watch.urgent_alerts = True
    owner.watch.save(update_fields=["urgent_alerts"])
    owner.refresh_from_db()
    assert [row.id for row in eligible_alerts(owner, on=TUESDAY)] == [alert.id]

    # Never at the weekend, opt-in or not — invariant 2 is one rule in one place.
    assert eligible_alerts(owner, on=SATURDAY) == []


@pytest.mark.django_db
def test_only_a_moved_deadline_is_ever_urgent(owner: User, project: Project) -> None:
    """Not a small daily: the other four triggers wait for Monday."""
    from apps.accounts.models import WatchCadence
    from apps.content.urgent_alerts import eligible_alerts

    owner.watch.cadence = WatchCadence.WEEKLY
    owner.watch.urgent_alerts = True
    owner.watch.save(update_fields=["cadence", "urgent_alerts"])
    owner.refresh_from_db()
    for trigger in (
        ProjectAlert.Trigger.OVERLAP_RISK,
        ProjectAlert.Trigger.UNBLOCKS,
        ProjectAlert.Trigger.TIMELINE,
        ProjectAlert.Trigger.TEAM_GAP,
    ):
        ProjectAlert.objects.create(
            target_user=owner,
            project=project,
            content=_item(f"Item {trigger}"),
            trigger=trigger,
            fired_on=TUESDAY,
        )

    assert eligible_alerts(owner, on=TUESDAY) == []


@pytest.mark.django_db
def test_the_urgent_message_costs_the_reader_one_glance(
    owner: User, project: Project
) -> None:
    """No statistics, no attachment: they asked not to be interrupted."""
    from apps.content.urgent_alerts import urgent_embed

    alert = ProjectAlert.objects.create(
        target_user=owner,
        project=project,
        content=_item("Moved grant", ContentItem.Type.GRANT),
        trigger=ProjectAlert.Trigger.DEADLINE_MOVED,
        fired_on=TUESDAY,
        evidence={"days": 6, "previous_due_date": "2026-10-21",
                  "due_date": "2026-09-17", "moved_earlier": True},
    )

    embed = urgent_embed(alert)

    assert embed["title"] == "A deadline moved on something you saved"
    assert "moved earlier" in embed["description"]
    assert "2026-09-17" in embed["description"]
    assert "6 days away" in embed["description"]
    assert "fields" not in embed
    assert "you asked to hear about these" in embed["footer"]["text"]


@pytest.mark.django_db
def test_an_urgent_alert_is_keyed_on_the_alert_not_the_day(
    owner: User, project: Project
) -> None:
    """A deadline re-read every night must raise one message, not seven."""
    alert = ProjectAlert.objects.create(
        target_user=owner,
        project=project,
        content=_item("Moved grant", ContentItem.Type.GRANT),
        trigger=ProjectAlert.Trigger.DEADLINE_MOVED,
        fired_on=TUESDAY,
    )
    from apps.content import delivery

    key = delivery.urgent_alert_key(owner, str(alert.id))

    assert str(alert.id) in key
    assert TUESDAY.isoformat() not in key
