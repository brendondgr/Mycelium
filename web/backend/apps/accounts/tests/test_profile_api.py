"""Phase G — profile read/update endpoints with object-level permissions."""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts.models import Department, Lab, LabMembership


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.mark.django_db
def test_own_profile_requires_authentication(client: APIClient) -> None:
    assert client.get("/api/auth/profile/me/").status_code in (401, 403)


@pytest.mark.django_db
def test_user_reads_and_updates_own_profile(client: APIClient) -> None:
    user = User.objects.create_user(username="u", password="p")
    client.force_authenticate(user)

    assert client.get("/api/auth/profile/me/").status_code == 200

    resp = client.patch(
        "/api/auth/profile/me/",
        {"institution": "Cascadia", "interests": {"version": 1, "areas": ["genomics"]}},
        format="json",
    )
    assert resp.status_code == 200
    user.profile.refresh_from_db()
    assert user.profile.institution == "Cascadia"
    assert user.profile.interests["areas"] == ["genomics"]
    # The embedding hook ran on save.
    assert "Areas: genomics" in user.profile.embedding_text


@pytest.mark.django_db
def test_profile_update_rejects_invalid_contract(client: APIClient) -> None:
    user = User.objects.create_user(username="u", password="p")
    client.force_authenticate(user)
    resp = client.patch(
        "/api/auth/profile/me/", {"interests": {"bogus": 1}}, format="json"
    )
    assert resp.status_code == 400
    assert "interests" in resp.data


@pytest.mark.django_db
def test_embedding_text_is_read_only(client: APIClient) -> None:
    user = User.objects.create_user(username="u", password="p")
    client.force_authenticate(user)
    resp = client.patch(
        "/api/auth/profile/me/",
        {"embedding_text": "injected", "interests": {"version": 1, "areas": ["x"]}},
        format="json",
    )
    assert resp.status_code == 200
    user.profile.refresh_from_db()
    assert user.profile.embedding_text != "injected"


# -- lab profile permissions --------------------------------------------------


@pytest.mark.django_db
def test_lab_lead_edits_member_reads_only(client: APIClient) -> None:
    lead = User.objects.create_user(username="lead", password="p")
    member = User.objects.create_user(username="mem", password="p")
    lab = Lab.objects.create(name="Reed Lab", slug="reed-lab")
    LabMembership.objects.create(
        user=lead, lab=lab, role=LabMembership.Role.OWNER, is_lead=True
    )
    LabMembership.objects.create(user=member, lab=lab, role=LabMembership.Role.MEMBER)
    url = f"/api/auth/labs/{lab.slug}/profile/"

    client.force_authenticate(member)
    assert client.get(url).status_code == 200
    assert client.patch(url, {"statement": "x"}, format="json").status_code == 403

    client.force_authenticate(lead)
    resp = client.patch(url, {"statement": "modeling proteins"}, format="json")
    assert resp.status_code == 200
    lab.profile.refresh_from_db()
    assert lab.profile.statement == "modeling proteins"


@pytest.mark.django_db
def test_non_member_cannot_read_lab_profile(client: APIClient) -> None:
    outsider = User.objects.create_user(username="out", password="p")
    lab = Lab.objects.create(name="Reed Lab", slug="reed-lab")
    client.force_authenticate(outsider)
    assert client.get(f"/api/auth/labs/{lab.slug}/profile/").status_code == 403


# -- department profile permissions -------------------------------------------


@pytest.mark.django_db
def test_dept_owner_edits_outsider_blocked(client: APIClient) -> None:
    owner = User.objects.create_user(username="own", password="p")
    dept = Department.objects.create(owner=owner, name="Dept")
    url = f"/api/auth/departments/{dept.id}/profile/"

    client.force_authenticate(owner)
    resp = client.patch(url, {"areas": ["climate science"]}, format="json")
    assert resp.status_code == 200
    dept.profile.refresh_from_db()
    assert dept.profile.areas == ["climate science"]

    outsider = User.objects.create_user(username="out", password="p")
    client.force_authenticate(outsider)
    assert client.get(url).status_code == 403
