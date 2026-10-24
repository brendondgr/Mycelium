"""Plan-gated creation, department scope, guided focus, and archiving via the API."""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts.models import Department, DeptMembership, Lab, LabMembership
from apps.billing.models import Subscription, Tier
from apps.research.models import Project


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def _sub(user: User, tier: str) -> None:
    Subscription.objects.create(tier=tier, scope_user=user)


def _create_status(client: APIClient, name: str) -> int:
    return client.post("/api/projects/", {"name": name}, format="json").status_code


# --------------------------------------------------------------------------- #
# Personal caps
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_free_user_capped_at_two_personal_projects(client: APIClient) -> None:
    user = User.objects.create_user(username="free", password="p")
    client.force_authenticate(user)
    assert _create_status(client, "One") == 201
    assert _create_status(client, "Two") == 201
    blocked = client.post("/api/projects/", {"name": "Three"}, format="json")
    assert blocked.status_code == 403
    assert blocked.data["code"] == "project_cap_reached"
    assert Project.objects.filter(scope_user=user).count() == 2


@pytest.mark.django_db
def test_spore_user_gets_five_personal_projects(client: APIClient) -> None:
    user = User.objects.create_user(username="spore", password="p")
    _sub(user, Tier.SPORE)
    client.force_authenticate(user)
    for i in range(5):
        assert client.post(
            "/api/projects/", {"name": f"P{i}"}, format="json"
        ).status_code == 201
    assert _create_status(client, "P6") == 403


@pytest.mark.django_db
def test_archiving_frees_a_personal_slot(client: APIClient) -> None:
    user = User.objects.create_user(username="free", password="p")
    client.force_authenticate(user)
    p1 = client.post("/api/projects/", {"name": "One"}, format="json").data
    client.post("/api/projects/", {"name": "Two"}, format="json")
    assert _create_status(client, "Three") == 403

    # Archive one → a slot opens.
    archived = client.post(f"/api/projects/{p1['id']}/archive/")
    assert archived.status_code == 200 and archived.data["is_archived"] is True
    assert _create_status(client, "Three") == 201


# --------------------------------------------------------------------------- #
# Lab caps + PI permission
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_pi_can_create_lab_project(client: APIClient) -> None:
    user = User.objects.create_user(username="pi", password="p")
    lab = Lab.objects.create(name="Reyes", slug="reyes")
    LabMembership.objects.create(
        user=user, lab=lab, role=LabMembership.Role.MEMBER, is_lead=True
    )
    Subscription.objects.create(tier=Tier.LAB, scope_lab=lab)
    client.force_authenticate(user)
    resp = client.post(
        "/api/projects/", {"name": "PI project", "lab": "reyes"}, format="json"
    )
    assert resp.status_code == 201


@pytest.mark.django_db
def test_unsubscribed_lab_cannot_create_projects(client: APIClient) -> None:
    user = User.objects.create_user(username="own", password="p")
    lab = Lab.objects.create(name="Poor", slug="poor")
    LabMembership.objects.create(user=user, lab=lab, role=LabMembership.Role.OWNER)
    client.force_authenticate(user)
    resp = client.post(
        "/api/projects/", {"name": "X", "lab": "poor"}, format="json"
    )
    assert resp.status_code == 403
    assert resp.data.get("code") == "project_cap_reached"


# --------------------------------------------------------------------------- #
# Department scope
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_department_owner_creates_department_project(client: APIClient) -> None:
    owner = User.objects.create_user(username="dean", password="p")
    dept = Department.objects.create(owner=owner, name="Bio")
    Subscription.objects.create(tier=Tier.CANOPY, scope_department=dept)
    client.force_authenticate(owner)
    resp = client.post(
        "/api/projects/",
        {"name": "Dept project", "department": str(dept.id)},
        format="json",
    )
    assert resp.status_code == 201
    project = Project.objects.get(name="Dept project")
    assert project.scope_department_id == dept.id


@pytest.mark.django_db
def test_non_manager_cannot_create_department_project(client: APIClient) -> None:
    owner = User.objects.create_user(username="dean", password="p")
    dept = Department.objects.create(owner=owner, name="Bio")
    Subscription.objects.create(tier=Tier.CANOPY, scope_department=dept)
    member = User.objects.create_user(username="rank", password="p")
    DeptMembership.objects.create(
        user=member, department=dept, role=DeptMembership.Role.MEMBER
    )
    client.force_authenticate(member)
    resp = client.post(
        "/api/projects/",
        {"name": "Blocked", "department": str(dept.id)},
        format="json",
    )
    assert resp.status_code == 403


# --------------------------------------------------------------------------- #
# Guided focus + clusters at creation
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_create_with_focus_and_clusters(client: APIClient) -> None:
    user = User.objects.create_user(username="focus", password="p")
    client.force_authenticate(user)
    focus = {
        "areas": ["graph neural networks", "protein folding"],
        "keywords": ["gnn"],
        "statement": "ML for structural biology",
        "clusters": [
            {"id": "c-ml", "label": "ML methods", "areas": ["graph neural networks"]},
            {"id": "c-bio", "label": "Biology", "areas": ["protein folding"]},
        ],
    }
    resp = client.post(
        "/api/projects/", {"name": "Structural ML", "focus": focus}, format="json"
    )
    assert resp.status_code == 201
    project = Project.objects.get(name="Structural ML")
    stored = project.goals["interests"]
    assert stored["areas"] == ["graph neural networks", "protein folding"]
    assert {c["id"] for c in stored["clusters"]} == {"c-ml", "c-bio"}


@pytest.mark.django_db
def test_create_rejects_bad_cluster_partition(client: APIClient) -> None:
    user = User.objects.create_user(username="bad", password="p")
    client.force_authenticate(user)
    focus = {
        "areas": ["a", "b"],
        "clusters": [{"id": "c-1", "label": "Only A", "areas": ["a"]}],  # b orphaned
    }
    resp = client.post(
        "/api/projects/", {"name": "Bad", "focus": focus}, format="json"
    )
    assert resp.status_code == 400


# --------------------------------------------------------------------------- #
# Archive / unarchive semantics
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_unarchive_rechecks_cap(client: APIClient) -> None:
    user = User.objects.create_user(username="free", password="p")
    client.force_authenticate(user)
    a = client.post("/api/projects/", {"name": "A"}, format="json").data
    client.post("/api/projects/", {"name": "B"}, format="json")
    client.post(f"/api/projects/{a['id']}/archive/")
    # Fill the freed slot.
    client.post("/api/projects/", {"name": "C"}, format="json")
    # Now at 2/2 active; reviving A must be refused.
    revive = client.delete(f"/api/projects/{a['id']}/archive/")
    assert revive.status_code == 403
    assert revive.data["code"] == "project_cap_reached"


@pytest.mark.django_db
def test_over_cap_flag_after_downgrade(client: APIClient) -> None:
    """A Spore user with 5 projects who lapses to Free reads 3 as over-cap."""
    user = User.objects.create_user(username="lapsed", password="p")
    sub = Subscription.objects.create(tier=Tier.SPORE, scope_user=user)
    for i in range(5):
        Project.objects.create(scope_user=user, name=f"P{i}")
    sub.status = Subscription.Status.CANCELED
    sub.save()

    client.force_authenticate(user)
    listing = client.get("/api/projects/").data
    over = [p for p in listing if p["is_over_cap"]]
    assert len(over) == 3  # Free cap 2, oldest two stay in budget
