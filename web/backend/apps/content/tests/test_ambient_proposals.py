"""Ambient Plan 08, the project side: a development from conversation becomes a
reflection proposal for the project's editors, and only accepting it applies
it — recorded, and undoable to exactly what was there. (Here because the
ambient app may not import ``apps.content``.)"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from apps.accounts.models import Lab, LabMembership, Profile
from apps.ambient import review
from apps.ambient.models import AppliedChange, ProjectDevelopment, Visibility
from apps.research.models import Project, ProjectMember, ProjectState


@pytest.fixture
def ada(db):
    user = User.objects.create_user("ada", "ada@example.org", "pw")
    Profile.objects.get_or_create(user=user)
    return user


# -- project state, through proposals -----------------------------------------------


@pytest.fixture
def lab_project(ada):
    lab = Lab.objects.create(name="PULSE", slug="pulse")
    LabMembership.objects.create(user=ada, lab=lab, is_lead=True)
    bo = User.objects.create_user("bo", "bo@example.org", "pw")
    LabMembership.objects.create(user=bo, lab=lab)
    project = Project.objects.create(name="Imaging pipeline", scope_lab=lab)
    for person in (ada, bo):
        ProjectMember.objects.create(project=project, user=person)
    ProjectState.objects.create(
        project=project,
        slow={
            "blockers": [
                {"id": "b1", "text": "no annotation budget"},
                {"id": "b2", "text": "waiting for GPUs"},
            ],
            "method": ["graph neural networks", "random forests"],
        },
    )
    return project, bo


def _development(project, speaker, change, topic, *, visibility=Visibility.LAB):
    return ProjectDevelopment.objects.create(
        project=project,
        speaker=speaker,
        change=change,
        topic=topic,
        text="Reported this in the lab channel.",
        force="fact",
        occurred_on=timezone.localdate(),
        status="confirmed",
        origin="conversation",
        visibility=visibility,
    )


def test_a_closed_blocker_is_proposed_to_editors_and_accepting_applies_it(
    ada, lab_project, client
):
    from apps.content.ambient_proposals import propose
    from apps.content.models import ReflectionProposal

    project, bo = lab_project
    _development(project, bo, "blocker_closed", "annotation budget")
    assert propose() == 1
    proposal = ReflectionProposal.objects.get()
    assert proposal.target_user == ada and proposal.kind == "close_blocker"
    assert [b["id"] for b in proposal.proposal["slow"]["blockers"]] == ["b2"]
    assert propose() == 0  # once
    client.force_login(ada)
    response = client.post(
        f"/api/reflections/{proposal.pk}/action/",
        {"action": "accept"},
        content_type="application/json",
    )
    assert response.status_code == 200, response.content
    state = ProjectState.objects.get(project=project)
    assert [b["id"] for b in state.slow["blockers"]] == ["b2"]
    change = AppliedChange.objects.get(kind="state_edit")
    assert change.field == "slow.blockers" and change.project == project
    review.undo(change, by=ada)
    state.refresh_from_db()
    assert [b["id"] for b in state.slow["blockers"]] == ["b1", "b2"]


def test_a_dropped_and_an_adopted_method(ada, lab_project):
    from apps.content.ambient_proposals import propose
    from apps.content.models import ReflectionProposal

    project, bo = lab_project
    _development(project, bo, "method_dropped", "graph neural networks")
    _development(project, bo, "method_adopted", "conformal prediction")
    _development(project, bo, "method_adopted", "random forests")  # already stated
    assert propose() == 2
    kinds = {
        p.kind: p.proposal["slow"]["method"] for p in ReflectionProposal.objects.all()
    }
    assert kinds["drop_method"] == ["random forests"]
    assert kinds["add_method"] == [
        "graph neural networks",
        "random forests",
        "conformal prediction",
    ]


def test_a_private_development_is_proposed_only_to_its_speaker(ada, lab_project):
    from apps.content.ambient_proposals import propose
    from apps.content.models import ReflectionProposal

    project, bo = lab_project
    _development(
        project,
        ada,
        "blocker_closed",
        "annotation budget",
        visibility=Visibility.PERSONAL,
    )
    propose()
    assert list(
        ReflectionProposal.objects.values_list("target_user__username", flat=True)
    ) == ["ada"]


def test_a_declined_proposal_rests(ada, lab_project):
    from apps.content.ambient_proposals import propose
    from apps.content.models import ReflectionProposal

    project, bo = lab_project
    _development(project, bo, "blocker_closed", "annotation budget")
    propose()
    ReflectionProposal.objects.update(status="rejected", decided_at=timezone.now())
    assert propose() == 0


def test_a_proposal_is_withdrawn_when_its_development_is_undone(ada, lab_project):
    from apps.content.ambient_proposals import propose
    from apps.content.models import ReflectionProposal

    project, bo = lab_project
    development = _development(project, bo, "blocker_closed", "annotation budget")
    propose()
    ProjectDevelopment.objects.filter(pk=development.pk).update(status="rejected")
    assert propose() == 0
    assert ReflectionProposal.objects.get().status == "expired"


def test_a_forgotten_development_takes_its_proposal_with_it(ada, lab_project):
    from apps.content.ambient_proposals import propose
    from apps.content.models import ReflectionProposal

    project, bo = lab_project
    development = _development(project, bo, "method_dropped", "graph neural networks")
    propose()
    development.delete()
    propose()
    assert ReflectionProposal.objects.get().status == "expired"


def test_an_accepted_proposal_is_not_withdrawn_later(ada, lab_project):
    from apps.content.ambient_proposals import propose
    from apps.content.models import ReflectionProposal

    project, bo = lab_project
    development = _development(project, bo, "blocker_closed", "annotation budget")
    propose()
    ReflectionProposal.objects.update(status="accepted", decided_at=timezone.now())
    development.delete()
    propose()
    assert ReflectionProposal.objects.get().status == "accepted"


def test_someone_it_was_not_raised_to_cannot_accept_it(ada, lab_project, client):
    from apps.content.ambient_proposals import propose
    from apps.content.models import ReflectionProposal

    project, bo = lab_project
    _development(project, bo, "blocker_closed", "annotation budget")
    propose()
    proposal = ReflectionProposal.objects.get()
    for person in (bo, User.objects.create_user("cy", "cy@example.org", "pw")):
        client.force_login(person)
        response = client.post(
            f"/api/reflections/{proposal.pk}/action/",
            {"action": "accept"},
            content_type="application/json",
        )
        assert response.status_code in (403, 404)
        listing = client.get("/api/reflections/")
        assert str(proposal.pk) not in listing.content.decode()
    state = ProjectState.objects.get(project=project)
    assert len(state.slow["blockers"]) == 2


def test_accepting_changes_only_the_named_field(ada, lab_project, client):
    from apps.content.ambient_proposals import propose
    from apps.content.models import ReflectionProposal

    project, bo = lab_project
    before = ProjectState.objects.get(project=project)
    before.apply({})  # normalised, as any accepted edit leaves it
    before.save()
    slow = {k: v for k, v in before.slow.items() if k != "blockers"}
    fast = dict(before.fast)
    _development(project, bo, "blocker_closed", "annotation budget")
    propose()
    client.force_login(ada)
    client.post(
        f"/api/reflections/{ReflectionProposal.objects.get().pk}/action/",
        {"action": "accept"},
        content_type="application/json",
    )
    after = ProjectState.objects.get(project=project)
    assert {k: v for k, v in after.slow.items() if k != "blockers"} == slow
    assert dict(after.fast) == fast


def test_an_undo_after_a_later_edit_is_refused(ada, lab_project, client):
    from apps.content.ambient_proposals import propose
    from apps.content.models import ReflectionProposal

    project, bo = lab_project
    _development(project, bo, "blocker_closed", "annotation budget")
    propose()
    client.force_login(ada)
    client.post(
        f"/api/reflections/{ReflectionProposal.objects.get().pk}/action/",
        {"action": "accept"},
        content_type="application/json",
    )
    state = ProjectState.objects.get(project=project)
    state.apply({"slow": {"blockers": []}})
    state.save()
    with pytest.raises(ValueError):
        review.undo(AppliedChange.objects.get(kind="state_edit"), by=ada)
    state.refresh_from_db()
    assert state.slow["blockers"] == []


def test_a_rejected_proposal_records_no_change(ada, lab_project, client):
    from apps.content.ambient_proposals import propose
    from apps.content.models import ReflectionProposal

    project, bo = lab_project
    _development(project, bo, "blocker_closed", "annotation budget")
    propose()
    client.force_login(ada)
    client.post(
        f"/api/reflections/{ReflectionProposal.objects.get().pk}/action/",
        {"action": "reject"},
        content_type="application/json",
    )
    assert not AppliedChange.objects.exists()
    assert len(ProjectState.objects.get(project=project).slow["blockers"]) == 2


def test_a_proposal_rings_the_bell_once_and_leaves_it_when_withdrawn(ada, lab_project):
    from apps.content.ambient_proposals import propose
    from apps.content.models import Notification

    project, bo = lab_project
    development = _development(project, bo, "blocker_closed", "annotation budget")
    propose()
    propose()
    [bell] = Notification.objects.filter(user=ada)
    assert bell.kind == "suggestion_pending"
    assert bell.title == "Is “annotation budget” still blocking Imaging pipeline?"
    assert bell.url == f"/app/projects/{project.pk}"
    ProjectDevelopment.objects.filter(pk=development.pk).update(status="rejected")
    propose()
    bell.refresh_from_db()
    assert bell.dismissed_at is not None
