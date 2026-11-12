"""A lead PI can do everything an admin can (settings plan, decision 13).

Before, ``user_can_manage_lab`` read owner/admin only while the profile and
invitation checks also read ``is_lead`` — so a PI who was not also an admin
could edit the profile but was refused the roster, Discord and announcement
endpoints the app showed them.
"""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts.models import LabMembership
from apps.accounts.permissions import (
    lab_role_rank,
    user_can_grant_lab_role,
    user_can_manage_lab,
    user_outranks_lab_member,
)
from apps.billing.services import create_lab_workspace

from .conftest import verified


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def _user(name: str) -> User:
    return verified(User.objects.create_user(username=name, password="p"))


@pytest.fixture
def lab_with_pi():
    """A lab whose founder owns it, and whose PI is a lead with the member role."""
    founder = _user("founder")
    lab = create_lab_workspace(founder, "Rivera Lab").lab
    # The founder's own lead badge would collide with the cap on PIs; the case
    # here is a lab whose owner is an account manager and whose PI is a member.
    LabMembership.objects.filter(lab=lab, user=founder).update(is_lead=False)
    pi = _user("pi")
    LabMembership.objects.create(
        lab=lab, user=pi, role=LabMembership.Role.MEMBER, is_lead=True
    )
    LabMembership.objects.create(
        lab=lab, user=_user("student"), role=LabMembership.Role.MEMBER
    )
    LabMembership.objects.create(
        lab=lab, user=_user("deputy"), role=LabMembership.Role.ADMIN
    )
    return lab, pi


@pytest.mark.django_db
def test_a_lead_pi_manages_the_lab(lab_with_pi) -> None:
    lab, pi = lab_with_pi
    assert user_can_manage_lab(pi, lab)
    assert lab_role_rank(pi, lab) == lab_role_rank(
        User.objects.get(username="deputy"), lab
    )


@pytest.mark.django_db
def test_a_lead_pi_grants_what_an_admin_grants(lab_with_pi) -> None:
    lab, pi = lab_with_pi
    assert user_can_grant_lab_role(pi, lab, LabMembership.Role.MEMBER)
    assert user_can_grant_lab_role(pi, lab, LabMembership.Role.VIEWER)
    assert not user_can_grant_lab_role(pi, lab, LabMembership.Role.ADMIN)
    assert not user_can_grant_lab_role(pi, lab, LabMembership.Role.OWNER)


@pytest.mark.django_db
def test_a_lead_pi_acts_on_members_but_not_on_admins(lab_with_pi) -> None:
    lab, pi = lab_with_pi
    assert user_outranks_lab_member(pi, lab, User.objects.get(username="student"))
    assert not user_outranks_lab_member(pi, lab, User.objects.get(username="deputy"))


@pytest.mark.django_db
def test_an_admin_cannot_remove_the_lead_pi(client, lab_with_pi) -> None:
    lab, _pi = lab_with_pi
    client.force_authenticate(User.objects.get(username="deputy"))

    response = client.delete(f"/api/auth/labs/{lab.slug}/members/pi/")
    assert response.status_code == 403


@pytest.mark.django_db
def test_a_lead_pi_adds_a_member_over_the_api(client, lab_with_pi) -> None:
    lab, pi = lab_with_pi
    _user("newcomer")
    client.force_authenticate(pi)

    response = client.post(
        f"/api/auth/labs/{lab.slug}/members/",
        {"username": "newcomer", "role": "member"},
        format="json",
    )
    assert response.status_code == 201, response.data


@pytest.mark.django_db
def test_a_lead_pi_re_roles_a_member_over_the_api(client, lab_with_pi) -> None:
    lab, pi = lab_with_pi
    client.force_authenticate(pi)

    response = client.patch(
        f"/api/auth/labs/{lab.slug}/members/student/",
        {"role": "viewer"},
        format="json",
    )
    assert response.status_code == 200, response.data


@pytest.mark.django_db
def test_a_lead_pi_reads_the_discord_health(client, lab_with_pi) -> None:
    """One of the endpoints that used to refuse a PI the app showed the card to."""
    lab, pi = lab_with_pi
    client.force_authenticate(pi)
    health = client.get(f"/api/integrations/discord/health/?lab={lab.slug}")
    assert health.status_code != 403

    client.force_authenticate(User.objects.get(username="student"))
    refused = client.get(f"/api/integrations/discord/health/?lab={lab.slug}")
    assert refused.status_code == 403


@pytest.mark.django_db
def test_a_lab_admin_cannot_add_someone_as_admin(client, lab_with_pi) -> None:
    """Adding a member at a role is granting it; the downward rule applies."""
    lab, _pi = lab_with_pi
    _user("newcomer")
    client.force_authenticate(User.objects.get(username="deputy"))

    response = client.post(
        f"/api/auth/labs/{lab.slug}/members/",
        {"username": "newcomer", "role": "admin"},
        format="json",
    )
    assert response.status_code == 403
    assert not LabMembership.objects.filter(lab=lab, user__username="newcomer").exists()


@pytest.mark.django_db
def test_a_lab_admin_cannot_invite_an_admin_by_link(client, lab_with_pi) -> None:
    lab, _pi = lab_with_pi
    client.force_authenticate(User.objects.get(username="deputy"))

    response = client.post(
        f"/api/auth/labs/{lab.slug}/invites/",
        {"kind": "link", "role": "admin"},
        format="json",
    )
    assert response.status_code == 403
