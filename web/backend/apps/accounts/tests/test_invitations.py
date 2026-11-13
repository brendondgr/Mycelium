"""Lab invitations: invite by email/username, pending-email claim, and responses."""

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts.models import Lab, LabInvitation, LabMembership

from .conftest import verified


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def _lab_with_pi() -> tuple[User, Lab]:
    pi = verified(
        User.objects.create_user(username="pi", password="p", email="pi@lab.edu")
    )
    lab = Lab.objects.create(name="Reyes Lab", slug="reyes-lab")
    LabMembership.objects.create(
        user=pi, lab=lab, role=LabMembership.Role.OWNER, is_lead=True
    )
    return pi, lab


def _invite(client: APIClient, lab: Lab, identifier: str):
    return client.post(
        f"/api/auth/labs/{lab.slug}/invitations/",
        {"identifier": identifier},
        format="json",
    )


@pytest.mark.django_db
def test_pi_invites_existing_user_by_username(client: APIClient) -> None:
    pi, lab = _lab_with_pi()
    invitee = User.objects.create_user(username="jordan", password="p", email="j@x.edu")

    client.force_authenticate(pi)
    resp = _invite(client, lab, "jordan")
    assert resp.status_code == 201

    inv = LabInvitation.objects.get(lab=lab)
    assert inv.invitee == invitee
    assert inv.status == LabInvitation.Status.PENDING
    assert inv.role == LabMembership.Role.MEMBER

    # The invitee sees it in their notifications feed.
    client.force_authenticate(invitee)
    feed = client.get("/api/auth/invitations/")
    assert feed.status_code == 200
    assert len(feed.data) == 1
    assert feed.data[0]["lab_slug"] == lab.slug
    assert feed.data[0]["inviter"]  # inviter display name present


@pytest.mark.django_db
def test_invite_by_email_matches_existing_user_case_insensitively(
    client: APIClient,
) -> None:
    pi, lab = _lab_with_pi()
    invitee = verified(
        User.objects.create_user(username="k", password="p", email="Kai@X.edu")
    )

    client.force_authenticate(pi)
    resp = _invite(client, lab, "kai@x.edu")
    assert resp.status_code == 201

    inv = LabInvitation.objects.get(lab=lab)
    assert inv.invitee == invitee
    assert inv.invited_email == "kai@x.edu"


@pytest.mark.django_db
def test_email_invite_not_bound_to_unverified_account(client: APIClient) -> None:
    """An account that only *typed* an address does not receive its invitations."""
    pi, lab = _lab_with_pi()
    squatter = User.objects.create_user(
        username="squat", password="p", email="victim@x.edu"
    )

    client.force_authenticate(pi)
    assert _invite(client, lab, "victim@x.edu").status_code == 201
    inv = LabInvitation.objects.get(lab=lab)
    assert inv.invitee is None

    client.force_authenticate(squatter)
    assert client.get("/api/auth/invitations/").data == []
    resp = client.post(
        f"/api/auth/invitations/{inv.id}/respond/", {"action": "accept"}, format="json"
    )
    assert resp.status_code == 403
    assert not LabMembership.objects.filter(lab=lab, user=squatter).exists()


@pytest.mark.django_db
def test_unverified_account_cannot_accept_email_bound_invitation(
    client: APIClient,
) -> None:
    """A row bound by email before the rule existed still needs a proved address."""
    pi, lab = _lab_with_pi()
    squatter = User.objects.create_user(
        username="squat", password="p", email="victim@x.edu"
    )
    inv = LabInvitation.objects.create(
        lab=lab, inviter=pi, invitee=squatter, invited_email="victim@x.edu"
    )
    client.force_authenticate(squatter)
    resp = client.post(
        f"/api/auth/invitations/{inv.id}/respond/", {"action": "accept"}, format="json"
    )
    assert resp.status_code == 403
    assert not LabMembership.objects.filter(lab=lab, user=squatter).exists()

    verified(squatter)  # proving the mailbox is what makes it theirs
    resp = client.post(
        f"/api/auth/invitations/{inv.id}/respond/", {"action": "accept"}, format="json"
    )
    assert resp.status_code == 200
    assert LabMembership.objects.filter(lab=lab, user=squatter).exists()


@pytest.mark.django_db
def test_admin_cannot_invite_admin_or_owner(client: APIClient) -> None:
    pi, lab = _lab_with_pi()
    admin = verified(User.objects.create_user(username="adm", password="p"))
    LabMembership.objects.create(user=admin, lab=lab, role=LabMembership.Role.ADMIN)
    User.objects.create_user(username="target", password="p")

    client.force_authenticate(admin)
    for role in ("admin", "owner"):
        resp = client.post(
            f"/api/auth/labs/{lab.slug}/invitations/",
            {"identifier": "target", "role": role},
            format="json",
        )
        assert resp.status_code == 403, role
    assert not LabInvitation.objects.exists()

    # The owner may invite an admin, never an owner.
    client.force_authenticate(pi)
    owner_try = client.post(
        f"/api/auth/labs/{lab.slug}/invitations/",
        {"identifier": "target", "role": "owner"},
        format="json",
    )
    assert owner_try.status_code == 403
    ok = client.post(
        f"/api/auth/labs/{lab.slug}/invitations/",
        {"identifier": "target", "role": "admin"},
        format="json",
    )
    assert ok.status_code == 201


@pytest.mark.django_db
def test_legacy_owner_invitation_grants_member(client: APIClient) -> None:
    pi, lab = _lab_with_pi()
    invitee = User.objects.create_user(username="j", password="p")
    inv = LabInvitation.objects.create(
        lab=lab, inviter=pi, invitee=invitee, role=LabMembership.Role.OWNER
    )
    client.force_authenticate(invitee)
    resp = client.post(
        f"/api/auth/invitations/{inv.id}/respond/", {"action": "accept"}, format="json"
    )
    assert resp.status_code == 200
    assert (
        LabMembership.objects.get(lab=lab, user=invitee).role
        == LabMembership.Role.MEMBER
    )


@pytest.mark.django_db
def test_invite_unknown_username_errors(client: APIClient) -> None:
    pi, lab = _lab_with_pi()
    client.force_authenticate(pi)
    resp = _invite(client, lab, "ghost")
    assert resp.status_code == 400
    assert not LabInvitation.objects.exists()


@pytest.mark.django_db
def test_pending_email_invite_claimed_on_signup(client: APIClient) -> None:
    pi, lab = _lab_with_pi()
    client.force_authenticate(pi)
    resp = _invite(client, lab, "new@person.edu")
    assert resp.status_code == 201

    inv = LabInvitation.objects.get(lab=lab)
    assert inv.invitee is None
    assert inv.invited_email == "new@person.edu"

    # The invited person registers with that email.
    client.force_authenticate(user=None)
    reg = client.post(
        "/api/auth/register/",
        {
            "username": "newbie",
            "email": "new@person.edu",
            "password": "Str0ng-P4ssw0rd!",
            "password_confirm": "Str0ng-P4ssw0rd!",
            "account_type": "personal",
            "access_code": settings.SIGNUP_ACCESS_CODE,
        },
        format="json",
    )
    assert reg.status_code == 201

    newbie = User.objects.get(username="newbie")
    inv.refresh_from_db()
    # Not yet: typing the address at sign-up is a claim, not proof.
    assert inv.invitee is None

    # Proving the mailbox claims it — surfaced, not auto-accepted.
    from apps.accounts.services import claim_pending_invitations

    verified(newbie)
    claim_pending_invitations(newbie)
    inv.refresh_from_db()
    assert inv.invitee == newbie
    assert inv.status == LabInvitation.Status.PENDING

    client.force_authenticate(newbie)
    feed = client.get("/api/auth/invitations/")
    assert len(feed.data) == 1


@pytest.mark.django_db
def test_only_managers_can_invite(client: APIClient) -> None:
    pi, lab = _lab_with_pi()
    plain = User.objects.create_user(username="plain", password="p")
    LabMembership.objects.create(user=plain, lab=lab, role=LabMembership.Role.MEMBER)

    client.force_authenticate(plain)
    resp = _invite(client, lab, "someone@x.edu")
    assert resp.status_code == 403
    assert not LabInvitation.objects.exists()


@pytest.mark.django_db
def test_accept_invitation_adds_membership(client: APIClient) -> None:
    pi, lab = _lab_with_pi()
    invitee = User.objects.create_user(username="j", password="p", email="j@x.edu")

    client.force_authenticate(pi)
    inv_id = _invite(client, lab, "j").data["id"]

    client.force_authenticate(invitee)
    resp = client.post(
        f"/api/auth/invitations/{inv_id}/respond/",
        {"action": "accept"},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["status"] == "accepted"
    assert LabMembership.objects.filter(user=invitee, lab=lab).exists()
    # No longer pending in the feed.
    assert client.get("/api/auth/invitations/").data == []


@pytest.mark.django_db
@pytest.mark.parametrize(
    "action,expected",
    [("reject", "rejected"), ("ignore", "ignored")],
)
def test_reject_and_ignore_add_no_membership(
    client: APIClient, action: str, expected: str
) -> None:
    pi, lab = _lab_with_pi()
    invitee = User.objects.create_user(username="j", password="p", email="j@x.edu")

    client.force_authenticate(pi)
    inv_id = _invite(client, lab, "j").data["id"]

    client.force_authenticate(invitee)
    resp = client.post(
        f"/api/auth/invitations/{inv_id}/respond/",
        {"action": action},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["status"] == expected
    assert not LabMembership.objects.filter(user=invitee, lab=lab).exists()
    assert client.get("/api/auth/invitations/").data == []  # dismissed from feed


@pytest.mark.django_db
def test_only_invitee_can_respond(client: APIClient) -> None:
    pi, lab = _lab_with_pi()
    User.objects.create_user(username="j", password="p", email="j@x.edu")
    other = User.objects.create_user(username="other", password="p")

    client.force_authenticate(pi)
    inv_id = _invite(client, lab, "j").data["id"]

    client.force_authenticate(other)
    resp = client.post(
        f"/api/auth/invitations/{inv_id}/respond/",
        {"action": "accept"},
        format="json",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_duplicate_pending_invite_rejected(client: APIClient) -> None:
    pi, lab = _lab_with_pi()
    User.objects.create_user(username="j", password="p", email="j@x.edu")

    client.force_authenticate(pi)
    assert _invite(client, lab, "j").status_code == 201
    assert _invite(client, lab, "j").status_code == 400


@pytest.mark.django_db
def test_cannot_invite_existing_member(client: APIClient) -> None:
    pi, lab = _lab_with_pi()
    member = User.objects.create_user(username="m", password="p", email="m@x.edu")
    LabMembership.objects.create(user=member, lab=lab, role=LabMembership.Role.MEMBER)

    client.force_authenticate(pi)
    resp = _invite(client, lab, "m")
    assert resp.status_code == 400
