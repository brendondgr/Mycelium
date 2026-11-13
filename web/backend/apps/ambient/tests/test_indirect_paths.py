"""The indirect paths (scoping plan, Phase 4): what an ``invite_only`` project
lets slip without ever being named.

* Ambient: something said about an ``invite_only`` project in the lab's server is
  ``project`` evidence, never ``lab`` evidence; its developments reach the
  people who can open the project, not a lab surface.
* A narrowed project's stored changes drop out of every lab read.

Member fit, saves, reminders, files and chat are checked on the delivery side
(``tools/delivery/tests/test_project_scope_paths.py``).
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from apps.accounts.models import Department, Lab, LabMembership
from apps.ambient.models import PlaceKind, ProjectDevelopment, Visibility
from apps.ambient.read import developments_in_effect
from apps.ambient.reading import _owner, _visibility
from apps.research.models import Project, ProjectMember

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


# --------------------------------------------------------------------------- #
# Ambient
# --------------------------------------------------------------------------- #
def _said(org, project, place_kind=PlaceKind.CHANNEL, kind="project_development"):
    item = SimpleNamespace(
        kind=kind,
        line=SimpleNamespace(place_kind=place_kind, project_id=str(project.pk)),
    )
    conversation = SimpleNamespace(source=SimpleNamespace(lab_id=org.lab.pk))
    return item, conversation, {str(project.pk): project}


def test_said_in_the_lab_about_an_invite_only_project_is_project_evidence(org):
    assert _visibility(*_said(org, org.projects["invite_only"])) == Visibility.PROJECT
    assert _visibility(*_said(org, org.projects["lab"])) == Visibility.LAB
    # Said in a DM it stays with the person, whatever the project.
    assert (
        _visibility(*_said(org, org.projects["lab"], PlaceKind.DM))
        == Visibility.PERSONAL
    )


def test_an_invite_only_projects_topics_are_born_with_its_speaker(org):
    item, _conversation, projects = _said(org, org.projects["invite_only"])
    assert _owner(item, org.on, projects) == org.on
    item, _conversation, projects = _said(org, org.projects["lab"])
    assert _owner(item, org.on, projects) == org.lab


def _development(project, speaker, vis):
    return ProjectDevelopment.objects.create(
        project=project,
        speaker=speaker,
        change="dataset_arrived",
        topic="scanner data",
        text="the scanner data arrived",
        force="fact",
        occurred_on=date(2026, 11, 1),
        status=ProjectDevelopment.Status.ACTIVE,
        origin=ProjectDevelopment.Origin.TOLD,
        visibility=vis,
    )


def test_a_project_development_reaches_its_people_and_no_lab_surface(org):
    project = org.projects["invite_only"]
    dev = _development(project, org.on, Visibility.PROJECT)
    assert list(developments_in_effect(project, reader=org.on)) == [dev]
    assert list(developments_in_effect(project, reader=org.pi)) == [dev]  # overseer
    assert list(developments_in_effect(project, reader=org.off)) == []
    assert list(developments_in_effect(project)) == []  # a lab surface: no reader


def test_editing_alternatives_name_only_projects_the_editor_can_open(org):
    from apps.ambient.editing import alternatives

    names = {row["name"] for row in alternatives(org.projects["lab"], org.off)}
    assert "P invite_only" not in names


def test_narrowing_drops_stored_lab_changes_at_read(org):
    from apps.ambient.models import AppliedChange
    from apps.ambient.read import changes_between

    AppliedChange.objects.create(
        project=org.projects["lab"],
        user=org.on,
        kind=AppliedChange._meta.get_field("kind").choices[0][0],
        topic="scanner",
        visibility="lab",
    )
    window = {
        "since": timezone.now() - timedelta(days=1),
        "until": timezone.now() + timedelta(days=1),
    }
    assert changes_between(projects=[org.projects["lab"]], **window)
    org.projects["lab"].visibility = "invite_only"
    org.projects["lab"].save(update_fields=["visibility"])
    assert changes_between(projects=[org.projects["lab"]], **window) == []
