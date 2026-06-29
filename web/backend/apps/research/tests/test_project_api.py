"""Read-only project list endpoint with cascade visibility + lab filter."""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts.models import Lab, LabMembership
from apps.research.models import Project, ProjectMember


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.mark.django_db
def test_projects_require_authentication(client: APIClient) -> None:
    assert client.get("/api/projects/").status_code in (401, 403)


@pytest.mark.django_db
def test_member_sees_only_visible_projects(client: APIClient) -> None:
    user = User.objects.create_user(username="u", password="p")
    mine = Project.objects.create(name="Mine", scope_user=user)
    ProjectMember.objects.create(project=mine, user=user)
    other = User.objects.create_user(username="other", password="p")
    Project.objects.create(name="Theirs", scope_user=other)

    client.force_authenticate(user)
    resp = client.get("/api/projects/")
    assert resp.status_code == 200
    names = {p["name"] for p in resp.data}
    assert names == {"Mine"}


@pytest.mark.django_db
def test_lab_head_sees_lab_projects_non_member_does_not(client: APIClient) -> None:
    lead = User.objects.create_user(username="lead", password="p")
    outsider = User.objects.create_user(username="out", password="p")
    lab = Lab.objects.create(name="Reyes Lab", slug="reyes-lab")
    LabMembership.objects.create(
        user=lead, lab=lab, role=LabMembership.Role.OWNER, is_lead=True
    )
    Project.objects.create(name="Drought study", scope_lab=lab)

    client.force_authenticate(lead)
    assert {p["name"] for p in client.get("/api/projects/").data} == {"Drought study"}

    client.force_authenticate(outsider)
    assert client.get("/api/projects/").data == []


@pytest.mark.django_db
def test_lab_filter_narrows_to_one_lab(client: APIClient) -> None:
    head = User.objects.create_user(username="head", password="p")
    lab_a = Lab.objects.create(name="Lab A", slug="lab-a")
    lab_b = Lab.objects.create(name="Lab B", slug="lab-b")
    for lab in (lab_a, lab_b):
        LabMembership.objects.create(
            user=head, lab=lab, role=LabMembership.Role.ADMIN
        )
    Project.objects.create(name="A1", scope_lab=lab_a)
    Project.objects.create(name="B1", scope_lab=lab_b)

    client.force_authenticate(head)
    resp = client.get("/api/projects/?lab=lab-a")
    assert {p["name"] for p in resp.data} == {"A1"}


@pytest.mark.django_db
def test_serializer_surfaces_goal_hints_and_members(client: APIClient) -> None:
    user = User.objects.create_user(
        username="lena", password="p", first_name="Lena", last_name="Reyes"
    )
    project = Project.objects.create(
        name="Drought study",
        scope_user=user,
        goals={"status": "On track", "progress": 68, "goal": "Map signaling"},
    )
    ProjectMember.objects.create(project=project, user=user)

    client.force_authenticate(user)
    row = client.get("/api/projects/").data[0]
    assert row["status"] == "On track"
    assert row["progress"] == 68
    assert row["scope"] == "user"
    assert row["scope_name"] == "Personal"
    assert row["member_count"] == 1
    assert row["members"][0]["initials"] == "LR"
    assert row["members"][0]["name"] == "Lena Reyes"


@pytest.mark.django_db
def test_missing_goal_hints_serialize_as_null(client: APIClient) -> None:
    user = User.objects.create_user(username="u", password="p")
    Project.objects.create(name="Bare", scope_user=user)
    client.force_authenticate(user)
    row = client.get("/api/projects/").data[0]
    assert row["status"] is None
    assert row["progress"] is None
