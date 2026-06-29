"""Lab membership reads: the workspace switcher and a lab's member roster."""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts.models import Department, Lab, LabMembership


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.mark.django_db
def test_my_labs_requires_authentication(client: APIClient) -> None:
    assert client.get("/api/auth/labs/").status_code in (401, 403)


@pytest.mark.django_db
def test_my_labs_lists_only_callers_memberships(client: APIClient) -> None:
    user = User.objects.create_user(username="u", password="p")
    owner = User.objects.create_user(username="o", password="p")
    dept = Department.objects.create(owner=owner, name="Biology")
    mine = Lab.objects.create(name="Reyes Lab", slug="reyes-lab", department=dept)
    LabMembership.objects.create(
        user=user, lab=mine, role=LabMembership.Role.OWNER, is_lead=True
    )
    theirs = Lab.objects.create(name="Other Lab", slug="other-lab")
    LabMembership.objects.create(user=owner, lab=theirs)

    client.force_authenticate(user)
    resp = client.get("/api/auth/labs/")
    assert resp.status_code == 200
    assert len(resp.data) == 1
    row = resp.data[0]
    assert row["slug"] == "reyes-lab"
    assert row["name"] == "Reyes Lab"
    assert row["role"] == "owner"
    assert row["is_lead"] is True
    assert row["department"] == "Biology"


@pytest.mark.django_db
def test_lab_members_roster_visible_to_members(client: APIClient) -> None:
    lead = User.objects.create_user(
        username="lena", password="p", first_name="Lena", last_name="Reyes"
    )
    member = User.objects.create_user(username="jordan", password="p")
    lab = Lab.objects.create(name="Reyes Lab", slug="reyes-lab")
    LabMembership.objects.create(
        user=lead, lab=lab, role=LabMembership.Role.OWNER, is_lead=True
    )
    LabMembership.objects.create(
        user=member, lab=lab, role=LabMembership.Role.MEMBER
    )

    client.force_authenticate(member)
    resp = client.get(f"/api/auth/labs/{lab.slug}/members/")
    assert resp.status_code == 200
    assert len(resp.data) == 2
    # Lead is ordered first (-is_lead).
    assert resp.data[0]["username"] == "lena"
    assert resp.data[0]["is_lead"] is True
    assert resp.data[0]["initials"] == "LR"
    assert resp.data[0]["name"] == "Lena Reyes"


@pytest.mark.django_db
def test_non_member_cannot_read_roster(client: APIClient) -> None:
    outsider = User.objects.create_user(username="out", password="p")
    lab = Lab.objects.create(name="Reyes Lab", slug="reyes-lab")
    client.force_authenticate(outsider)
    assert client.get(f"/api/auth/labs/{lab.slug}/members/").status_code == 403


@pytest.mark.django_db
def test_missing_lab_roster_is_404(client: APIClient) -> None:
    user = User.objects.create_user(username="u", password="p")
    client.force_authenticate(user)
    assert client.get("/api/auth/labs/nope/members/").status_code == 404
