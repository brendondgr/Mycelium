"""Go-public Phase 1: how people and labs get into labs and departments.

Each test is named after the abuse it prevents (plan
``20261112-go-public-readiness``, items 1.1–1.5, 1.8, 1.10, and the Phase 3 logo
item that lives in this app).
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient

from apps.accounts import invites
from apps.accounts.models import (
    AuditEvent,
    AuthorWork,
    DeptMembership,
    Lab,
    LabAttachRequest,
    LabInvitation,
    LabMembership,
    OrgInvite,
)
from apps.accounts.services import add_dept_member, add_lab_member
from apps.billing.services import create_lab_workspace, provision_workspace

from .conftest import verified


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def _user(name: str, email: str = "") -> User:
    return verified(
        User.objects.create_user(
            username=name, password="p", email=email or f"{name}@uni.edu"
        )
    )


def _lab(owner_name: str = "pi") -> tuple[User, Lab]:
    owner = _user(owner_name)
    return owner, create_lab_workspace(owner, f"{owner_name} lab").lab


def _member(lab: Lab, name: str, role=LabMembership.Role.MEMBER, **extra) -> User:
    user = _user(name)
    LabMembership.objects.create(user=user, lab=lab, role=role, **extra)
    return user


def _department(head_name: str = "head"):
    head = _user(head_name)
    return head, provision_workspace(head, "department", org_name="Systems").department


# -- 1.1 attaching a lab needs its owner -----------------------------------------


@pytest.mark.django_db
def test_dept_head_cannot_attach_foreign_lab(client: APIClient) -> None:
    """A stranger's new department cannot swallow someone else's lab."""
    _, lab = _lab("victim")
    attacker, dept = _department("attacker")

    client.force_authenticate(attacker)
    resp = client.post(
        f"/api/auth/departments/{dept.id}/labs/", {"slug": lab.slug}, format="json"
    )

    assert resp.status_code == 202
    assert resp.data["status"] == "requested"
    lab.refresh_from_db()
    assert lab.department_id is None
    assert LabAttachRequest.objects.filter(lab=lab, department=dept).count() == 1
    # Not attached, so the attacker reads neither the roster nor the labs list.
    assert client.get(f"/api/auth/departments/{dept.id}/labs/").data == []
    roster = client.get(f"/api/auth/departments/{dept.id}/members/").data
    assert {row["username"] for row in roster} == {"attacker"}
    assert AuditEvent.objects.filter(action="dept.lab.attach_requested").exists()


@pytest.mark.django_db
def test_lab_owner_attaches_own_lab_directly(client: APIClient) -> None:
    head, dept = _department()
    lab = create_lab_workspace(head, "Head's own lab").lab

    client.force_authenticate(head)
    resp = client.post(
        f"/api/auth/departments/{dept.id}/labs/", {"slug": lab.slug}, format="json"
    )

    assert resp.status_code == 201
    lab.refresh_from_db()
    assert lab.department_id == dept.id


@pytest.mark.django_db
def test_only_lab_owner_answers_attach_request(client: APIClient) -> None:
    owner, lab = _lab()
    admin = _member(lab, "adm", LabMembership.Role.ADMIN)
    head, dept = _department()
    client.force_authenticate(head)
    client.post(
        f"/api/auth/departments/{dept.id}/labs/", {"slug": lab.slug}, format="json"
    )
    request = LabAttachRequest.objects.get(lab=lab)

    # Neither the requesting head nor a lab admin may accept on the owner's behalf.
    for actor in (head, admin):
        client.force_authenticate(actor)
        url = f"/api/auth/labs/{lab.slug}/attach-requests/{request.id}/accept/"
        assert client.post(url).status_code == 403
        assert (
            client.get(f"/api/auth/labs/{lab.slug}/attach-requests/").status_code == 403
        )

    client.force_authenticate(owner)
    declined = client.post(
        f"/api/auth/labs/{lab.slug}/attach-requests/{request.id}/decline"
    )
    assert declined.status_code == 200
    assert declined.data["status"] == "declined"
    lab.refresh_from_db()
    assert lab.department_id is None
    assert AuditEvent.objects.filter(action="dept.lab.attach_declined").exists()


# -- 1.2 the role-rank rule on every grant ---------------------------------------


@pytest.mark.django_db
def test_admin_cannot_add_owner() -> None:
    owner, lab = _lab()
    admin = _member(lab, "adm", LabMembership.Role.ADMIN)
    target = _user("target")

    with pytest.raises(PermissionDenied):
        add_lab_member(lab, target, role=LabMembership.Role.OWNER, actor=admin)
    with pytest.raises(PermissionDenied):
        add_lab_member(lab, target, role=LabMembership.Role.ADMIN, actor=admin)
    # Not even the owner mints an owner this way — that is the transfer route.
    with pytest.raises(PermissionDenied):
        add_lab_member(lab, target, role=LabMembership.Role.OWNER, actor=owner)
    assert not LabMembership.objects.filter(lab=lab, user=target).exists()


@pytest.mark.django_db
def test_admin_cannot_issue_admin_link(client: APIClient) -> None:
    owner, lab = _lab()
    admin = _member(lab, "adm", LabMembership.Role.ADMIN)
    lead = _member(lab, "lead", LabMembership.Role.MEMBER, is_lead=True)

    for actor in (admin, lead):
        client.force_authenticate(actor)
        resp = client.post(
            f"/api/auth/labs/{lab.slug}/invites/",
            {"kind": "link", "role": "admin"},
            format="json",
        )
        assert resp.status_code == 403, actor.username
        batch = client.post(
            f"/api/auth/labs/{lab.slug}/invites/",
            {"emails": ["a@x.edu"], "role": "admin"},
            format="json",
        )
        assert batch.status_code == 403, actor.username
    assert not OrgInvite.objects.filter(role="admin").exists()

    # A lead PI with the member role still invites members.
    client.force_authenticate(lead)
    ok = client.post(
        f"/api/auth/labs/{lab.slug}/invites/",
        {"kind": "link", "role": "member"},
        format="json",
    )
    assert ok.status_code == 201

    client.force_authenticate(owner)
    owner_link = client.post(
        f"/api/auth/labs/{lab.slug}/invites/",
        {"kind": "link", "role": "admin"},
        format="json",
    )
    assert owner_link.status_code == 201


@pytest.mark.django_db
def test_admin_link_from_demoted_creator_grants_member() -> None:
    owner, lab = _lab()
    invite = invites.create_invite(
        creator=owner, lab=lab, kind="link", role=OrgInvite.Role.ADMIN
    )
    # The creator hands the lab over and is now an admin, who cannot make admins.
    successor = _member(lab, "successor")
    from apps.accounts.services import transfer_lab_ownership

    transfer_lab_ownership(lab, successor, actor=owner)

    joiner = _user("joiner")
    invites.redeem_token(invite.token, joiner)
    assert (
        LabMembership.objects.get(lab=lab, user=joiner).role
        == LabMembership.Role.MEMBER
    )


# -- 1.3 joining needs consent ----------------------------------------------------


@pytest.mark.django_db
def test_direct_add_requires_consent(client: APIClient) -> None:
    owner, lab = _lab()
    target = _user("target")

    client.force_authenticate(owner)
    resp = client.post(
        f"/api/auth/labs/{lab.slug}/members/", {"username": "target"}, format="json"
    )
    assert resp.status_code == 202
    assert not LabMembership.objects.filter(lab=lab, user=target).exists()
    # The roster shows members only — never an invited person or their email.
    roster = client.get(f"/api/auth/labs/{lab.slug}/members/").data
    assert "target" not in {row["username"] for row in roster}
    assert "target@uni.edu" not in str(roster)

    invitation = LabInvitation.objects.get(lab=lab, invitee=target)
    client.force_authenticate(target)
    client.post(
        f"/api/auth/invitations/{invitation.id}/respond/",
        {"action": "reject"},
        format="json",
    )
    assert not LabMembership.objects.filter(lab=lab, user=target).exists()


@pytest.mark.django_db
def test_direct_add_does_not_reveal_whether_username_exists(
    client: APIClient,
) -> None:
    owner, lab = _lab()
    _user("real")
    _member(lab, "already")
    client.force_authenticate(owner)

    answers = [
        client.post(
            f"/api/auth/labs/{lab.slug}/members/", {"username": name}, format="json"
        )
        for name in ("real", "ghost-nobody", "already")
    ]
    assert {r.status_code for r in answers} == {202}
    assert len({str(r.data) for r in answers}) == 1


@pytest.mark.django_db
def test_dept_direct_add_requires_consent(client: APIClient) -> None:
    head, dept = _department()
    target = _user("target")
    client.force_authenticate(head)

    real = client.post(
        f"/api/auth/departments/{dept.id}/members/",
        {"username": "target"},
        format="json",
    )
    ghost = client.post(
        f"/api/auth/departments/{dept.id}/members/",
        {"username": "nobody-at-all"},
        format="json",
    )
    assert real.status_code == ghost.status_code == 202
    assert real.data == ghost.data
    assert not DeptMembership.objects.filter(department=dept, user=target).exists()
    roster = client.get(f"/api/auth/departments/{dept.id}/members/").data
    assert "target" not in {row["username"] for row in roster}
    assert OrgInvite.objects.filter(department=dept, email="target@uni.edu").exists()


# -- 1.4 department role rank -----------------------------------------------------


@pytest.mark.django_db
def test_dept_admin_cannot_grant_admin_or_owner() -> None:
    head, dept = _department()
    admin = _user("dadmin")
    DeptMembership.objects.create(
        department=dept, user=admin, role=DeptMembership.Role.ADMIN
    )
    target = _user("target")

    for role in (DeptMembership.Role.ADMIN, DeptMembership.Role.OWNER):
        with pytest.raises(PermissionDenied):
            add_dept_member(dept, target, role=role, actor=admin)
        with pytest.raises(PermissionDenied):
            invites.create_invite(
                creator=admin, department=dept, kind="link", role=role
            )
    add_dept_member(dept, target, role=DeptMembership.Role.MEMBER, actor=admin)
    assert DeptMembership.objects.get(department=dept, user=target).role == "member"


@pytest.mark.django_db
def test_dept_admin_cannot_remove_dept_admin(client: APIClient) -> None:
    head, dept = _department()
    admin = _user("dadmin")
    peer = _user("peer")
    for user in (admin, peer):
        DeptMembership.objects.create(
            department=dept, user=user, role=DeptMembership.Role.ADMIN
        )

    client.force_authenticate(admin)
    resp = client.delete(f"/api/auth/departments/{dept.id}/members/peer/")
    assert resp.status_code == 403
    assert DeptMembership.objects.filter(department=dept, user=peer).exists()

    client.force_authenticate(head)
    assert (
        client.delete(f"/api/auth/departments/{dept.id}/members/peer/").status_code
        == 204
    )


# -- 1.8 invitation caps ----------------------------------------------------------


@pytest.mark.django_db
def test_invite_creation_capped_per_creator_per_day(
    client: APIClient, monkeypatch
) -> None:
    monkeypatch.setattr(invites, "MAX_INVITES_PER_CREATOR_PER_DAY", 2)
    owner, lab = _lab()
    client.force_authenticate(owner)

    url = f"/api/auth/labs/{lab.slug}/invites/"
    assert client.post(url, {"kind": "link"}, format="json").status_code == 201
    assert client.post(url, {"kind": "link"}, format="json").status_code == 201
    third = client.post(url, {"kind": "link"}, format="json")
    assert third.status_code == 429
    batch = client.post(url, {"emails": ["a@x.edu"]}, format="json")
    assert batch.status_code == 429
    assert OrgInvite.objects.count() == 2


@pytest.mark.django_db
def test_invite_creation_capped_per_org_per_day(client: APIClient, monkeypatch) -> None:
    monkeypatch.setattr(invites, "MAX_INVITES_PER_ORG_PER_DAY", 1)
    owner, lab = _lab()
    admin = _member(lab, "adm", LabMembership.Role.ADMIN)

    client.force_authenticate(owner)
    url = f"/api/auth/labs/{lab.slug}/invites/"
    assert client.post(url, {"kind": "link"}, format="json").status_code == 201
    client.force_authenticate(admin)  # a second inviter does not reset the org's cap
    assert client.post(url, {"kind": "link"}, format="json").status_code == 429


# -- Tokens are stored hashed (Phase 2, lives with the invite code) ---------------


@pytest.mark.django_db
def test_invite_token_stored_hashed(client: APIClient) -> None:
    owner, lab = _lab()
    client.force_authenticate(owner)
    created = client.post(
        f"/api/auth/labs/{lab.slug}/invites/", {"kind": "link"}, format="json"
    )
    assert created.status_code == 201
    token = created.data["url"].rsplit("/", 1)[-1]

    row = OrgInvite.objects.get(pk=created.data["id"])
    assert token not in row.token_hash
    assert row.token_hash == invites.hash_token(token)
    # The link works by presenting the token…
    assert client.get(f"/api/auth/invites/{token}/").status_code == 200
    # …but the stored digest is not itself a usable token.
    assert client.get(f"/api/auth/invites/{row.token_hash}/").status_code == 410

    # Listed later, the link cannot be shown again.
    listed = client.get(f"/api/auth/labs/{lab.slug}/invites/").data[0]
    assert listed["url"] is None and listed["url_available"] is False

    # Regenerating gives a new working link and retires the old one.
    fresh = client.post(f"/api/auth/labs/{lab.slug}/invites/{row.id}/regenerate/")
    assert fresh.status_code == 200
    new_token = fresh.data["url"].rsplit("/", 1)[-1]
    assert new_token != token
    assert client.get(f"/api/auth/invites/{new_token}/").status_code == 200
    assert client.get(f"/api/auth/invites/{token}/").status_code == 410


@pytest.mark.django_db
def test_member_cannot_regenerate_invite(client: APIClient) -> None:
    owner, lab = _lab()
    plain = _member(lab, "plain")
    invite = invites.create_invite(creator=owner, lab=lab, kind="link")
    client.force_authenticate(plain)
    resp = client.post(f"/api/auth/labs/{lab.slug}/invites/{invite.id}/regenerate/")
    assert resp.status_code == 403


# -- 1.10 a foreign author import is a claim -------------------------------------


@pytest.mark.django_db
def test_foreign_author_import_is_unverified_and_not_a_coauthorship(
    client: APIClient, monkeypatch
) -> None:
    from dataclasses import dataclass, field

    from apps.accounts import views
    from apps.knowledge import coauthorship

    @dataclass
    class Draft:
        evidence: list = field(default_factory=list)
        display_name: str = "Someone Famous"

        def to_interests(self) -> dict:
            return {}

    victim = _user("victim")
    victim.profile.openalex_id = "A123"
    victim.profile.save(update_fields=["openalex_id"])
    draft = Draft(
        evidence=[
            {
                "title": "A paper by the victim",
                "source_id": "W1",
                "coauthor_ids": ["A123"],
            }
        ]
    )
    monkeypatch.setattr(views, "import_author", lambda identifier, source: draft)
    monkeypatch.setattr(views, "_draft_payload", lambda user, d: {})

    impostor = _user("impostor")
    client.force_authenticate(impostor)
    resp = client.post(
        "/api/auth/intake/import/",
        {"identifier": "A123", "source": "openalex"},
        format="json",
    )
    assert resp.status_code == 200
    work = AuthorWork.objects.get(user=impostor)
    assert work.verified is False
    # It does not make the impostor the victim's co-author.
    assert coauthorship.derive() == {}

    work.verified = True  # what staff vouching looks like
    work.save(update_fields=["verified"])
    assert coauthorship.derive() == {tuple(sorted((victim.id, impostor.id))): (1, None)}


# -- Phase 3: lab logos are images, never documents -------------------------------


SVG_WITH_SCRIPT = (
    b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
)


@pytest.mark.django_db
def test_svg_logo_rejected(client: APIClient, settings, tmp_path) -> None:
    settings.MEDIA_ROOT = str(tmp_path)
    owner, lab = _lab()
    client.force_authenticate(owner)
    upload = SimpleUploadedFile(
        "logo.svg", SVG_WITH_SCRIPT, content_type="image/svg+xml"
    )
    resp = client.post(
        f"/api/auth/labs/{lab.slug}/logo/", {"file": upload}, format="multipart"
    )
    assert resp.status_code == 400
    lab.refresh_from_db()
    assert not lab.logo


@pytest.mark.django_db
def test_stored_svg_logo_served_as_sandboxed_attachment(
    client: APIClient, settings, tmp_path
) -> None:
    from django.core.files.base import ContentFile

    settings.MEDIA_ROOT = str(tmp_path)
    owner, lab = _lab()
    lab.logo.save("old.svg", ContentFile(SVG_WITH_SCRIPT), save=False)
    lab.logo_content_type = "image/svg+xml"
    lab.save(update_fields=["logo", "logo_content_type"])

    client.force_authenticate(owner)
    resp = client.get(f"/api/auth/labs/{lab.slug}/logo/")
    assert resp.status_code == 200
    assert resp["Content-Disposition"].startswith("attachment")
    assert "sandbox" in resp["Content-Security-Policy"]
    assert "default-src 'none'" in resp["Content-Security-Policy"]
    assert resp["X-Content-Type-Options"] == "nosniff"
