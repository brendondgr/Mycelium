"""What the Settings area relies on from the API (settings plan, Phase 2).

Two acceptance rules land here:

- A lab member who manages nothing can still open Settings, find their role
  and leave the lab — so leaving is its own route, open to any member, rather
  than the manager-only member DELETE.
- A page the app hides or shows read-only for a role is backed by an API that
  refuses that role's writes. The app's page list is drawn from the same
  capability presets these endpoints check; this pins the endpoints' half.
"""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts.models import AuditEvent, DeptMembership, LabMembership
from apps.billing.services import create_department_workspace, create_lab_workspace

from .conftest import verified


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def _user(name: str) -> User:
    return verified(User.objects.create_user(username=name, password="p"))


@pytest.fixture
def lab():
    """A lab owned by ``owner`` with one admin, one member and one viewer."""
    owner = _user("owner")
    lab = create_lab_workspace(owner, "Soil Lab").lab
    for name, role in (
        ("deputy", LabMembership.Role.ADMIN),
        ("student", LabMembership.Role.MEMBER),
        ("guest", LabMembership.Role.VIEWER),
    ):
        LabMembership.objects.create(lab=lab, user=_user(name), role=role)
    return lab


@pytest.fixture
def dept():
    """A department run by ``head`` with one admin and one member."""
    head = _user("head")
    department = create_department_workspace(head, "Earth Sciences").department
    DeptMembership.objects.create(
        department=department, user=_user("dadmin"), role=DeptMembership.Role.ADMIN
    )
    DeptMembership.objects.create(
        department=department, user=_user("dmember"), role=DeptMembership.Role.MEMBER
    )
    return department


# -- Your membership: a lab ---------------------------------------------------


@pytest.mark.django_db
def test_a_plain_member_sees_their_role_and_can_leave(client: APIClient, lab) -> None:
    client.force_authenticate(User.objects.get(username="student"))

    row = next(r for r in client.get("/api/auth/labs/").json() if r["slug"] == lab.slug)
    assert row["role"] == "member"
    assert row["capabilities"] == ["org.people.view"]

    resp = client.post(f"/api/auth/labs/{lab.slug}/leave/")

    assert resp.status_code == 204
    assert not LabMembership.objects.filter(lab=lab, user__username="student").exists()
    assert AuditEvent.objects.filter(action="lab.member.leave").exists()


@pytest.mark.django_db
def test_a_viewer_can_leave_through_the_no_slash_route(client: APIClient, lab) -> None:
    client.force_authenticate(User.objects.get(username="guest"))

    assert client.post(f"/api/auth/labs/{lab.slug}/leave").status_code == 204


@pytest.mark.django_db
def test_the_only_owner_cannot_leave(client: APIClient, lab) -> None:
    client.force_authenticate(User.objects.get(username="owner"))

    resp = client.post(f"/api/auth/labs/{lab.slug}/leave/")

    assert resp.status_code == 409
    assert LabMembership.objects.filter(lab=lab, user__username="owner").exists()


@pytest.mark.django_db
def test_a_stranger_cannot_leave_a_lab(client: APIClient, lab) -> None:
    client.force_authenticate(_user("stranger"))

    assert client.post(f"/api/auth/labs/{lab.slug}/leave/").status_code == 403


# -- Your membership: a department --------------------------------------------


@pytest.mark.django_db
def test_a_direct_department_member_can_leave(client: APIClient, dept) -> None:
    client.force_authenticate(User.objects.get(username="dmember"))

    resp = client.post(f"/api/auth/departments/{dept.id}/leave/")

    assert resp.status_code == 204
    assert not DeptMembership.objects.filter(
        department=dept, user__username="dmember"
    ).exists()


@pytest.mark.django_db
def test_the_head_cannot_leave(client: APIClient, dept) -> None:
    client.force_authenticate(User.objects.get(username="head"))

    assert client.post(f"/api/auth/departments/{dept.id}/leave").status_code == 409


@pytest.mark.django_db
def test_someone_in_through_a_lab_is_told_to_leave_the_lab(
    client: APIClient, dept
) -> None:
    founder = _user("founder")
    lab = create_lab_workspace(founder, "Rock Lab").lab
    lab.department = dept
    lab.save(update_fields=["department"])
    client.force_authenticate(founder)

    resp = client.post(f"/api/auth/departments/{dept.id}/leave/")

    assert resp.status_code == 409
    assert "lab" in resp.json()["detail"]


@pytest.mark.django_db
def test_a_stranger_cannot_leave_a_department(client: APIClient, dept) -> None:
    client.force_authenticate(_user("stranger"))

    assert client.post(f"/api/auth/departments/{dept.id}/leave/").status_code == 403


# -- Writes behind a hidden or read-only page are refused ----------------------


def _lab_writes(slug: str) -> list[tuple[str, str, dict]]:
    """The write behind each lab page a plain member sees read-only or not at all."""
    return [
        ("patch", f"/api/auth/labs/{slug}/profile/", {"statement": "x"}),  # General
        (
            "patch",
            f"/api/auth/labs/{slug}/members/owner/",
            {"role": "viewer"},
        ),  # People
        ("post", f"/api/auth/labs/{slug}/invites/", {"emails": ["a@b.edu"]}),
        ("post", f"/api/labs/{slug}/billing/activate/", {}),  # Plan
        ("post", f"/api/auth/labs/{slug}/transfer-ownership/", {"username": "deputy"}),
    ]


@pytest.mark.django_db
@pytest.mark.parametrize("who", ["student", "guest"])
def test_a_lab_reader_is_refused_every_settings_write(
    client: APIClient, lab, who: str
) -> None:
    client.force_authenticate(User.objects.get(username=who))

    for method, url, body in _lab_writes(lab.slug):
        resp = getattr(client, method)(url, body, format="json")
        assert resp.status_code == 403, (url, resp.status_code)


@pytest.mark.django_db
def test_a_lab_admin_is_refused_only_the_transfer(client: APIClient, lab) -> None:
    client.force_authenticate(User.objects.get(username="deputy"))

    resp = client.post(
        f"/api/auth/labs/{lab.slug}/transfer-ownership/",
        {"username": "student"},
        format="json",
    )
    assert resp.status_code == 403
    assert (
        client.patch(
            f"/api/auth/labs/{lab.slug}/profile/", {"statement": "x"}, format="json"
        ).status_code
        == 200
    )


@pytest.mark.django_db
def test_the_department_general_page_saves_through_the_profile_api(
    client: APIClient, dept
) -> None:
    payload = {
        "statement": "Earth systems across scales.",
        "areas": ["hydrology", "seismology"],
        "funding_needs": ["NSF EAR"],
    }
    client.force_authenticate(User.objects.get(username="dadmin"))
    resp = client.patch(
        f"/api/auth/departments/{dept.id}/profile/", payload, format="json"
    )
    assert resp.status_code == 200
    assert resp.json()["areas"] == ["hydrology", "seismology"]

    client.force_authenticate(User.objects.get(username="dmember"))
    assert client.get(f"/api/auth/departments/{dept.id}/profile/").status_code == 200
    assert (
        client.patch(
            f"/api/auth/departments/{dept.id}/profile",
            {"statement": "y"},
            format="json",
        ).status_code
        == 403
    )


@pytest.mark.django_db
def test_a_department_member_is_refused_every_settings_write(
    client: APIClient, dept
) -> None:
    client.force_authenticate(User.objects.get(username="dmember"))
    base = f"/api/auth/departments/{dept.id}"

    for method, url, body in [
        ("post", f"{base}/members/", {"username": "head", "role": "viewer"}),
        ("patch", f"{base}/members/dadmin/", {"role": "viewer"}),
        ("post", f"{base}/invites/", {"emails": ["a@b.edu"]}),
        ("post", f"{base}/labs/", {"name": "New Lab"}),
        ("post", f"/api/departments/{dept.id}/billing/activate/", {}),
        ("post", f"{base}/transfer-ownership/", {"username": "dadmin"}),
    ]:
        resp = getattr(client, method)(url, body, format="json")
        assert resp.status_code == 403, (url, resp.status_code)
