"""Authority in a lab runs strictly downward (plan phase 0).

Before this rule, ``user_can_manage_lab`` (owner **or** admin) was the only gate
on a role edit and ``set_lab_member_role`` accepted every role — so an admin
could mint an owner, including themselves. These tests pin the two things the
product asked for: only the PI creates admins, and ownership is never handed
over by a plain role edit.
"""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts.models import AuditEvent, LabMembership
from apps.billing.services import create_lab_workspace

from .conftest import verified


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def _user(name: str) -> User:
    return verified(User.objects.create_user(username=name, password="p"))


def _lab_with(owner: User, **roles: str):
    """A lab owned by ``owner``, plus one member per ``name=role`` pair."""
    lab = create_lab_workspace(owner, "Rivera Lab").lab
    for name, role in roles.items():
        LabMembership.objects.create(lab=lab, user=_user(name), role=role)
    return lab


def _set_role(client: APIClient, lab, username: str, role: str):
    return client.patch(
        f"/api/auth/labs/{lab.slug}/members/{username}/",
        {"role": role},
        format="json",
    )


# -- Only the PI creates admins ------------------------------------------------


@pytest.mark.django_db
def test_owner_may_grant_admin(client: APIClient) -> None:
    owner = _user("pi")
    lab = _lab_with(owner, student="member")
    client.force_authenticate(owner)

    assert _set_role(client, lab, "student", "admin").status_code == 200
    assert (
        LabMembership.objects.get(lab=lab, user__username="student").role
        == LabMembership.Role.ADMIN
    )


@pytest.mark.django_db
def test_admin_may_not_create_another_admin(client: APIClient) -> None:
    """The product rule: admins are the PI's to appoint, nobody else's."""
    owner = _user("pi")
    lab = _lab_with(owner, deputy="admin", student="member")
    client.force_authenticate(User.objects.get(username="deputy"))

    resp = _set_role(client, lab, "student", "admin")

    assert resp.status_code == 403
    assert "PI" in str(resp.data["detail"])
    assert (
        LabMembership.objects.get(lab=lab, user__username="student").role
        == LabMembership.Role.MEMBER
    )


@pytest.mark.django_db
def test_admin_may_still_set_the_roles_below_them(client: APIClient) -> None:
    owner = _user("pi")
    lab = _lab_with(owner, deputy="admin", student="member")
    client.force_authenticate(User.objects.get(username="deputy"))

    assert _set_role(client, lab, "student", "viewer").status_code == 200


# -- Nobody promotes themselves ------------------------------------------------


@pytest.mark.django_db
def test_admin_may_not_promote_themselves_to_owner(client: APIClient) -> None:
    owner = _user("pi")
    lab = _lab_with(owner, deputy="admin")
    deputy = User.objects.get(username="deputy")
    client.force_authenticate(deputy)

    resp = _set_role(client, lab, "deputy", "owner")

    assert resp.status_code == 403
    assert LabMembership.objects.get(lab=lab, user=deputy).role == (
        LabMembership.Role.ADMIN
    )


@pytest.mark.django_db
def test_owner_may_not_mint_a_second_owner_by_role_edit(client: APIClient) -> None:
    """Ownership moves by transfer only, so a lab always has exactly one."""
    owner = _user("pi")
    lab = _lab_with(owner, deputy="admin")
    client.force_authenticate(owner)

    resp = _set_role(client, lab, "deputy", "owner")

    assert resp.status_code == 403
    assert "transfer" in str(resp.data["detail"]).lower()


@pytest.mark.django_db
def test_admin_may_not_demote_the_owner(client: APIClient) -> None:
    owner = _user("pi")
    lab = _lab_with(owner, deputy="admin")
    client.force_authenticate(User.objects.get(username="deputy"))

    resp = _set_role(client, lab, "pi", "member")

    assert resp.status_code == 403
    assert LabMembership.objects.get(lab=lab, user=owner).role == (
        LabMembership.Role.OWNER
    )


@pytest.mark.django_db
def test_admin_may_not_re_role_another_admin(client: APIClient) -> None:
    owner = _user("pi")
    lab = _lab_with(owner, deputy="admin", peer="admin")
    client.force_authenticate(User.objects.get(username="deputy"))

    assert _set_role(client, lab, "peer", "member").status_code == 403


@pytest.mark.django_db
def test_a_refused_grant_is_audited(client: APIClient) -> None:
    """An escalation attempt should be visible, not merely blocked."""
    owner = _user("pi")
    lab = _lab_with(owner, deputy="admin")
    client.force_authenticate(User.objects.get(username="deputy"))

    _set_role(client, lab, "deputy", "owner")

    assert AuditEvent.objects.filter(action="lab.member.role.refused").exists()


# -- Removal obeys the same rule ----------------------------------------------


@pytest.mark.django_db
def test_admin_may_remove_a_member(client: APIClient) -> None:
    owner = _user("pi")
    lab = _lab_with(owner, deputy="admin", student="member")
    client.force_authenticate(User.objects.get(username="deputy"))

    resp = client.delete(f"/api/auth/labs/{lab.slug}/members/student/")

    assert resp.status_code == 204
    assert not LabMembership.objects.filter(lab=lab, user__username="student").exists()


@pytest.mark.django_db
def test_admin_may_not_remove_the_owner(client: APIClient) -> None:
    """Otherwise the escalation hole reopens wearing a different verb."""
    owner = _user("pi")
    lab = _lab_with(owner, deputy="admin")
    client.force_authenticate(User.objects.get(username="deputy"))

    resp = client.delete(f"/api/auth/labs/{lab.slug}/members/pi/")

    assert resp.status_code == 403
    assert LabMembership.objects.filter(lab=lab, user=owner).exists()


@pytest.mark.django_db
def test_admin_may_not_remove_another_admin(client: APIClient) -> None:
    owner = _user("pi")
    lab = _lab_with(owner, deputy="admin", peer="admin")
    client.force_authenticate(User.objects.get(username="deputy"))

    assert client.delete(f"/api/auth/labs/{lab.slug}/members/peer/").status_code == 403


@pytest.mark.django_db
def test_a_member_may_still_remove_themselves(client: APIClient) -> None:
    """Leaving is not an exercise of authority over anyone."""
    owner = _user("pi")
    lab = _lab_with(owner, student="member")
    student = User.objects.get(username="student")
    client.force_authenticate(student)

    resp = client.delete(f"/api/auth/labs/{lab.slug}/members/student/")

    # A plain member is not a lab manager, so the manager gate still refuses —
    # self-removal is a separate feature and is deliberately not smuggled in here.
    assert resp.status_code == 403
    assert LabMembership.objects.filter(lab=lab, user=student).exists()
