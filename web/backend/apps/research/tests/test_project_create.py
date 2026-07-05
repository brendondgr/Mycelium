"""Creating projects within a lab (or personally) via POST /api/projects/."""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts.models import Lab, LabMembership
from apps.research.models import Project


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def _lab_with(role: str, is_lead: bool = False) -> tuple[User, Lab]:
    user = User.objects.create_user(username="u", password="p")
    lab = Lab.objects.create(name="Reyes Lab", slug="reyes-lab")
    LabMembership.objects.create(user=user, lab=lab, role=role, is_lead=is_lead)
    return user, lab


@pytest.mark.django_db
def test_manager_creates_lab_project(client: APIClient) -> None:
    user, lab = _lab_with(LabMembership.Role.OWNER, is_lead=True)
    client.force_authenticate(user)

    resp = client.post(
        "/api/projects/",
        {"name": "Oceanography", "lab": "reyes-lab"},
        format="json",
    )
    assert resp.status_code == 201

    project = Project.objects.get(name="Oceanography")
    assert project.scope_lab_id == lab.id
    assert project.scope_user_id is None

    listing = client.get("/api/projects/?lab=reyes-lab")
    assert any(p["name"] == "Oceanography" for p in listing.data)


@pytest.mark.django_db
def test_non_manager_cannot_create_lab_project(client: APIClient) -> None:
    user, lab = _lab_with(LabMembership.Role.MEMBER)
    client.force_authenticate(user)

    resp = client.post(
        "/api/projects/",
        {"name": "Blocked", "lab": "reyes-lab"},
        format="json",
    )
    assert resp.status_code == 403
    assert not Project.objects.filter(name="Blocked").exists()


@pytest.mark.django_db
def test_personal_project_scoped_to_caller(client: APIClient) -> None:
    user = User.objects.create_user(username="solo", password="p")
    client.force_authenticate(user)

    resp = client.post("/api/projects/", {"name": "Solo work"}, format="json")
    assert resp.status_code == 201

    project = Project.objects.get(name="Solo work")
    assert project.scope_user_id == user.id
    assert project.scope_lab_id is None


@pytest.mark.django_db
def test_project_requires_a_name(client: APIClient) -> None:
    user = User.objects.create_user(username="u", password="p")
    client.force_authenticate(user)
    resp = client.post("/api/projects/", {"name": "   "}, format="json")
    assert resp.status_code == 400


@pytest.mark.django_db
def test_creating_lab_project_requires_authentication(client: APIClient) -> None:
    assert client.post("/api/projects/", {"name": "X"}).status_code in (401, 403)
