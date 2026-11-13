"""Project research focus: serialized shape + the edit endpoint that sets it.

A project's focus (areas / keywords / statement / watch topics) is what its daily
recommendations run against, stored in the free-form ``goals`` JSON and edited
through ``PATCH /api/projects/<id>/``.
"""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts.models import Lab, LabMembership
from apps.research.models import Project, ProjectMember


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.mark.django_db
def test_focus_serialized_from_explicit_goals(client: APIClient) -> None:
    user = User.objects.create_user(username="u", password="p")
    project = Project.objects.create(
        name="Cyber",
        scope_user=user,
        goals={"interests": {"areas": ["Cybersecurity"], "keywords": ["malware"]}},
    )
    ProjectMember.objects.create(project=project, user=user)

    client.force_authenticate(user)
    row = client.get("/api/projects/").data[0]
    assert row["focus"]["areas"] == ["Cybersecurity"]
    assert row["focus"]["keywords"] == ["malware"]
    # Watch topics fall back to the areas when none are set explicitly.
    assert row["focus"]["watch_topics"] == ["Cybersecurity"]


@pytest.mark.django_db
def test_focus_derived_from_legacy_goals(client: APIClient) -> None:
    user = User.objects.create_user(username="u", password="p")
    Project.objects.create(
        name="Legacy",
        scope_user=user,
        goals={"topics": ["Robotics"], "description": "Arm control"},
    )
    ProjectMember.objects.create(
        project=Project.objects.get(name="Legacy"), user=user
    )
    client.force_authenticate(user)
    row = client.get("/api/projects/").data[0]
    assert row["focus"]["areas"] == ["Robotics"]
    assert row["focus"]["statement"] == "Arm control"


@pytest.mark.django_db
def test_owner_edits_personal_project_focus(client: APIClient) -> None:
    user = User.objects.create_user(username="u", password="p")
    project = Project.objects.create(
        name="Old name", scope_user=user, goals={"status": "On track"}
    )

    client.force_authenticate(user)
    resp = client.patch(
        f"/api/projects/{project.id}/",
        {
            "name": "New name",
            "focus": {
                "areas": ["Quantum", "Quantum"],  # deduped
                "keywords": ["qubits"],
                "watch_topics": ["quantum error correction"],
            },
        },
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["name"] == "New name"
    assert resp.data["focus"]["areas"] == ["Quantum"]
    assert resp.data["focus"]["watch_topics"] == ["quantum error correction"]

    project.refresh_from_db()
    # The focus is merged into goals without clobbering the pre-existing status.
    assert project.goals["status"] == "On track"
    assert project.goals["interests"]["areas"] == ["Quantum"]


@pytest.mark.django_db
def test_lab_manager_edits_lab_project_but_member_cannot(client: APIClient) -> None:
    manager = User.objects.create_user(username="mgr", password="p")
    member = User.objects.create_user(username="mbr", password="p")
    lab = Lab.objects.create(name="Reyes Lab", slug="reyes-lab")
    LabMembership.objects.create(user=manager, lab=lab, role=LabMembership.Role.OWNER)
    LabMembership.objects.create(user=member, lab=lab, role=LabMembership.Role.MEMBER)
    project = Project.objects.create(name="Study", scope_lab=lab)
    ProjectMember.objects.create(project=project, user=member)

    # A rank-and-file member may view but not edit.
    client.force_authenticate(member)
    assert client.get(f"/api/projects/{project.id}/").status_code == 200
    denied = client.patch(
        f"/api/projects/{project.id}/", {"focus": {"areas": ["X"]}}, format="json"
    )
    assert denied.status_code == 403

    # The lab owner may edit.
    client.force_authenticate(manager)
    ok = client.patch(
        f"/api/projects/{project.id}/",
        {"focus": {"areas": ["Cybersecurity"]}},
        format="json",
    )
    assert ok.status_code == 200
    assert ok.data["focus"]["areas"] == ["Cybersecurity"]


@pytest.mark.django_db
def test_outsider_cannot_read_project(client: APIClient) -> None:
    owner = User.objects.create_user(username="owner", password="p")
    outsider = User.objects.create_user(username="out", password="p")
    project = Project.objects.create(name="Private", scope_user=owner)

    client.force_authenticate(outsider)
    assert client.get(f"/api/projects/{project.id}/").status_code == 404
