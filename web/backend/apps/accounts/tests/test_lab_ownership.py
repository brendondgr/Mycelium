"""Handing a lab to the person who actually runs it (plan phase 4).

The case: whoever creates the account and stands the lab up is often not its PI.
Transfer moves both marks of authority at once — ``role=OWNER``, which the
permission checks read, and ``is_lead``, the PI badge the roster reads — and is
irreversible from the outgoing side, because an admin cannot grant ownership.
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
    lab = create_lab_workspace(owner, "Rivera Lab").lab
    for name, role in roles.items():
        LabMembership.objects.create(lab=lab, user=_user(name), role=role)
    return lab


def _transfer(client: APIClient, lab, username: str):
    return client.post(
        f"/api/auth/labs/{lab.slug}/transfer-ownership/",
        {"username": username},
        format="json",
    )


@pytest.mark.django_db
def test_transfer_moves_both_the_role_and_the_pi_badge(client: APIClient) -> None:
    founder = _user("founder")
    lab = _lab_with(founder, professor="member")
    professor = User.objects.get(username="professor")
    client.force_authenticate(founder)

    assert _transfer(client, lab, "professor").status_code == 200

    incoming = LabMembership.objects.get(lab=lab, user=professor)
    assert incoming.role == LabMembership.Role.OWNER
    assert incoming.is_lead is True


@pytest.mark.django_db
def test_the_outgoing_owner_becomes_an_admin_not_a_stranger(client) -> None:
    """Handing a lab over is not leaving it."""
    founder = _user("founder")
    lab = _lab_with(founder, professor="member")
    client.force_authenticate(founder)

    _transfer(client, lab, "professor")

    outgoing = LabMembership.objects.get(lab=lab, user=founder)
    assert outgoing.role == LabMembership.Role.ADMIN
    assert outgoing.is_lead is False


@pytest.mark.django_db
def test_a_lab_keeps_exactly_one_owner_and_one_lead(client: APIClient) -> None:
    founder = _user("founder")
    lab = _lab_with(founder, professor="member", deputy="admin")
    client.force_authenticate(founder)

    _transfer(client, lab, "professor")

    assert (
        LabMembership.objects.filter(lab=lab, role=LabMembership.Role.OWNER).count()
        == 1
    )
    assert LabMembership.objects.filter(lab=lab, is_lead=True).count() == 1


@pytest.mark.django_db
def test_the_transfer_cannot_be_undone_from_the_old_owners_side(client) -> None:
    """The irreversibility the product asked for, enforced by the rank rule."""
    founder = _user("founder")
    lab = _lab_with(founder, professor="member")
    client.force_authenticate(founder)
    _transfer(client, lab, "professor")

    # As an admin now: neither a transfer back...
    assert _transfer(client, lab, "founder").status_code == 403
    # ...nor a plain role edit will do it.
    back = client.patch(
        f"/api/auth/labs/{lab.slug}/members/founder/",
        {"role": "owner"},
        format="json",
    )
    assert back.status_code == 403
    assert (
        LabMembership.objects.get(lab=lab, user__username="professor").role
        == LabMembership.Role.OWNER
    )


@pytest.mark.django_db
def test_only_the_new_owner_can_hand_it_back(client: APIClient) -> None:
    founder = _user("founder")
    lab = _lab_with(founder, professor="member")
    client.force_authenticate(founder)
    _transfer(client, lab, "professor")

    client.force_authenticate(User.objects.get(username="professor"))
    assert _transfer(client, lab, "founder").status_code == 200
    assert (
        LabMembership.objects.get(lab=lab, user=founder).role
        == LabMembership.Role.OWNER
    )


@pytest.mark.django_db
def test_an_admin_may_not_transfer_the_lab(client: APIClient) -> None:
    founder = _user("founder")
    lab = _lab_with(founder, deputy="admin", professor="member")
    client.force_authenticate(User.objects.get(username="deputy"))

    assert _transfer(client, lab, "professor").status_code == 403


@pytest.mark.django_db
def test_a_non_member_may_not_transfer_the_lab(client: APIClient) -> None:
    founder = _user("founder")
    lab = _lab_with(founder, professor="member")
    client.force_authenticate(_user("outsider"))

    assert _transfer(client, lab, "professor").status_code == 403


@pytest.mark.django_db
def test_the_target_must_already_be_a_member(client: APIClient) -> None:
    founder = _user("founder")
    lab = _lab_with(founder)
    _user("stranger")
    client.force_authenticate(founder)

    resp = _transfer(client, lab, "stranger")

    assert resp.status_code == 400
    assert "Add them to the lab" in str(resp.data)


@pytest.mark.django_db
def test_the_target_must_have_verified_their_email(client: APIClient) -> None:
    """They are about to hold the lab."""
    founder = _user("founder")
    lab = _lab_with(founder)
    unverified = User.objects.create_user(username="unproved", password="p")
    LabMembership.objects.create(
        lab=lab, user=unverified, role=LabMembership.Role.MEMBER
    )
    client.force_authenticate(founder)

    resp = _transfer(client, lab, "unproved")

    assert resp.status_code == 400
    assert "verify their email" in str(resp.data)


@pytest.mark.django_db
def test_transferring_to_yourself_is_refused(client: APIClient) -> None:
    founder = _user("founder")
    lab = _lab_with(founder)
    client.force_authenticate(founder)

    assert _transfer(client, lab, "founder").status_code == 400


@pytest.mark.django_db
def test_a_missing_username_is_a_plain_field_error(client: APIClient) -> None:
    founder = _user("founder")
    lab = _lab_with(founder)
    client.force_authenticate(founder)

    resp = client.post(
        f"/api/auth/labs/{lab.slug}/transfer-ownership/", {}, format="json"
    )

    assert resp.status_code == 400
    assert "username" in resp.data


@pytest.mark.django_db
def test_the_transfer_is_audited_with_both_parties(client: APIClient) -> None:
    founder = _user("founder")
    lab = _lab_with(founder, professor="member")
    professor = User.objects.get(username="professor")
    client.force_authenticate(founder)

    _transfer(client, lab, "professor")

    event = AuditEvent.objects.filter(action="lab.ownership.transfer").latest(
        "created_at"
    )
    assert event.metadata["from_user_id"] == founder.id
    assert event.metadata["to_user_id"] == professor.id


@pytest.mark.django_db
def test_the_no_slash_route_works_too(client: APIClient) -> None:
    """The Next proxy strips it, and APPEND_SLASH cannot redirect a POST."""
    founder = _user("founder")
    lab = _lab_with(founder, professor="member")
    client.force_authenticate(founder)

    resp = client.post(
        f"/api/auth/labs/{lab.slug}/transfer-ownership",
        {"username": "professor"},
        format="json",
    )

    assert resp.status_code == 200
