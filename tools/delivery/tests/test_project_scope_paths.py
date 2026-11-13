"""What an ``invite_only`` project lets slip without being named, on the
delivery side (scoping plan, Phases 4 and 5): member fit, saves and reminders
made inside the project, collaborator search, a narrowed
project's stored alerts and lab report, and open announcement threads.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest
from apps.accounts.models import Department, Lab, LabMembership
from apps.research import visibility
from apps.research.models import Project, ProjectMember
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


@pytest.fixture
def org(db):
    head = User.objects.create_user("head", "head@example.org", "pw")
    pi = User.objects.create_user("pi", "pi@example.org", "pw")
    on = User.objects.create_user("on", "on@example.org", "pw")
    off = User.objects.create_user("off", "off@example.org", "pw")
    dept = Department.objects.create(owner=head, name="Biology")
    lab = Lab.objects.create(name="Reef", slug="reef-indirect", department=dept)
    LabMembership.objects.create(
        user=pi, lab=lab, role=LabMembership.Role.OWNER, is_lead=True
    )
    for user in (on, off):
        LabMembership.objects.create(user=user, lab=lab)
    projects = {}
    for scope in ("invite_only", "lab", "department", "public"):
        project = Project.objects.create(
            name=f"P {scope}", scope_lab=lab, visibility=scope
        )
        ProjectMember.objects.create(
            project=project, user=on, role=ProjectMember.Role.OWNER
        )
        projects[scope] = project
    return SimpleNamespace(
        head=head, pi=pi, on=on, off=off, dept=dept, lab=lab, projects=projects
    )


def _verified(*users):
    from apps.accounts.models import Profile

    for user in users:
        Profile.objects.filter(user=user).update(is_verified=True)


@pytest.fixture
def life(db):
    head = User.objects.create_user("head", "head@example.org", "pw")
    pi = User.objects.create_user("pi", "pi@example.org", "pw")
    own = User.objects.create_user("own", "own@example.org", "pw")
    ed = User.objects.create_user("ed", "ed@example.org", "pw")
    mem = User.objects.create_user("mem", "mem@example.org", "pw")
    _verified(head, pi, own, ed, mem)
    dept = Department.objects.create(owner=head, name="Biology")
    lab = Lab.objects.create(name="Reef", slug="reef-life", department=dept)
    LabMembership.objects.create(
        user=pi, lab=lab, role=LabMembership.Role.OWNER, is_lead=True
    )
    for user in (own, ed, mem):
        LabMembership.objects.create(user=user, lab=lab)
    project = Project.objects.create(name="Kelp", scope_lab=lab, visibility="lab")
    ProjectMember.objects.create(
        project=project, user=own, role=ProjectMember.Role.OWNER
    )
    ProjectMember.objects.create(
        project=project, user=ed, role=ProjectMember.Role.EDITOR
    )
    ProjectMember.objects.create(project=project, user=mem)
    return SimpleNamespace(
        head=head, pi=pi, own=own, ed=ed, mem=mem, dept=dept, lab=lab, project=project
    )


def _client(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def _bell(user):
    from tools.delivery.models import Notification

    return list(
        Notification.objects.filter(
            user=user, kind=Notification.Kind.PROJECT_SCOPE
        ).values_list("title", flat=True)
    )


# --------------------------------------------------------------------------- #
# Member fit
# --------------------------------------------------------------------------- #
def test_member_fit_names_only_members_of_an_invite_only_project(org):
    from tools.recommendation.member_fit import scope_members

    people = scope_members({"target_project": org.projects["invite_only"]})
    assert {u.username for u in people} == {"on"}
    wider = scope_members({"target_project": org.projects["lab"]})
    assert {u.username for u in wider} == {"pi", "on", "off"}


def test_project_recommendations_offer_only_members_of_an_invite_only_project(org):
    assert visibility.candidate_people_ids(org.projects["invite_only"]) == {org.on.pk}
    assert visibility.candidate_people_ids(org.projects["department"]) >= {
        org.pi.pk,
        org.off.pk,
    }


# --------------------------------------------------------------------------- #
# Saves and reminders from inside an invite_only project
# --------------------------------------------------------------------------- #
@pytest.fixture
def grant(db):
    from tools.retrieval.models import ContentDeadline, ContentItem

    item = ContentItem.objects.create(
        type=ContentItem.Type.GRANT,
        source="pivot",
        external_id="g-1",
        metadata={"title": "Reef grant"},
    )
    ContentDeadline.objects.create(
        content=item,
        kind="application",
        due_date=timezone.localdate() + timedelta(days=40),
    )
    return item


def test_a_save_from_an_invite_only_project_is_personal_only(org, grant):
    client = APIClient()
    client.force_authenticate(org.pi)
    refused = client.post(
        "/api/opportunities/save/",
        {
            "content_id": str(grant.pk),
            "lab_slug": org.lab.slug,
            "project_id": str(org.projects["invite_only"].pk),
        },
        format="json",
    )
    assert refused.status_code == 400
    assert "invite-only" in refused.json()["detail"]
    allowed = client.post(
        "/api/opportunities/save/",
        {
            "content_id": str(grant.pk),
            "lab_slug": org.lab.slug,
            "project_id": str(org.projects["lab"].pk),
        },
        format="json",
    )
    assert allowed.status_code == 201


def test_a_reminder_from_an_invite_only_project_reaches_its_author_only(org, grant):
    from tools.delivery.models import ReminderSubscription

    client = APIClient()
    client.force_authenticate(org.pi)
    body = {
        "content_id": str(grant.pk),
        "deadline_kind": "application",
        "project_id": str(org.projects["invite_only"].pk),
    }
    refused = client.post(
        "/api/reminders/",
        {**body, "scope": "lab", "lab_slug": org.lab.slug},
        format="json",
    )
    assert refused.status_code == 400
    assert not ReminderSubscription.objects.filter(target_lab=org.lab).exists()

    personal = client.post(
        "/api/reminders/", {**body, "scope": "personal"}, format="json"
    )
    # 201 when the plan allows reminders, 403 when it does not — either way the
    # only possible target is the person, never the lab's channel.
    assert personal.status_code in (200, 201, 403)
    assert not ReminderSubscription.objects.filter(target_lab=org.lab).exists()


def test_a_project_id_the_caller_cannot_open_is_refused(org, grant):
    client = APIClient()
    client.force_authenticate(org.off)
    response = client.post(
        "/api/opportunities/save/",
        {
            "content_id": str(grant.pk),
            "project_id": str(org.projects["invite_only"].pk),
        },
        format="json",
    )
    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# Collaborator search from a project
# --------------------------------------------------------------------------- #
def test_a_project_search_log_keeps_slots_not_the_project(org):
    from apps.collab.models import Appearance, SearchLog

    fields = {f.name for f in SearchLog._meta.get_fields()}
    assert not {"project", "project_id", "target_project"} & fields
    appearance = {f.name for f in Appearance._meta.get_fields()}
    assert not {"project", "project_id", "slots", "entry"} & appearance


# --------------------------------------------------------------------------- #
# Narrowing
# --------------------------------------------------------------------------- #
def test_narrowing_tells_nobody_and_takes_effect_on_the_next_run(life):
    from tools.delivery.alert_report import open_alerts
    from tools.delivery.daily_report import compile_report_for_lab
    from tools.delivery.models import ProjectAlert
    from tools.retrieval.models import ContentItem

    item = ContentItem.objects.create(
        type=ContentItem.Type.GRANT, source="pivot", external_id="n1", metadata={}
    )
    ProjectAlert.objects.create(
        project=life.project,
        target_lab=life.lab,
        content=item,
        trigger=ProjectAlert.Trigger.UNBLOCKS,
        fired_on=timezone.localdate(),
        status=ProjectAlert.Status.OPEN,
    )
    assert open_alerts({"target_lab": life.lab})
    assert "Kelp" in {p.label for p in compile_report_for_lab(life.lab).projects}

    response = _client(life.own).patch(
        f"/api/projects/{life.project.pk}/",
        {"visibility": "invite_only"},
        format="json",
    )
    assert response.status_code == 200
    assert response.json()["scope_change"]["widened"] is False
    assert not _bell(life.mem)
    # The stored alert stays stored, but no lab read returns it any more.
    assert ProjectAlert.objects.filter(project=life.project).exists()
    assert open_alerts({"target_lab": life.lab}) == []
    assert "Kelp" not in {p.label for p in compile_report_for_lab(life.lab).projects}


def test_an_open_thread_drops_a_narrowed_projects_team_on_its_next_update(life):
    from tools.delivery.discord_announcements import scrub_narrowed

    alignment = {
        "projects": ["Kelp"],
        "project_teams": [{"project_id": str(life.project.pk), "name": "Kelp"}],
    }
    write_up = {
        "why_it_matters": "The Kelp project needs this.",
        "who_should_look": [
            {"kind": "project", "name": "Kelp", "members": ["Ed"]},
            {"kind": "person", "name": "Pi"},
        ],
    }
    same = scrub_narrowed(alignment, write_up, "lab")
    assert same == (alignment, write_up, [])

    life.project.visibility = "invite_only"
    life.project.save(update_fields=["visibility"])
    new_alignment, new_write_up, dropped = scrub_narrowed(alignment, write_up, "lab")
    assert dropped == ["Kelp"]
    assert new_alignment["project_teams"] == [] and new_alignment["projects"] == []
    assert [p["name"] for p in new_write_up["who_should_look"]] == ["Pi"]
    assert "Kelp" not in new_write_up["why_it_matters"]
