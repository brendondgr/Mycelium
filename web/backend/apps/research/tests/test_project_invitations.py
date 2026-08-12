"""Project member management: direct add for a lab, invitations for everyone else.

Two paths onto a roster, deliberately different:

* a lab's owner/admin/PI **adds** one of that lab's own members straight on;
* anyone else — an outside collaborator, or anyone on a personal project — is
  **invited** and joins only once they accept.

Accepting grants a ``ProjectMember`` row and nothing else: an outside
collaborator sees the one project, never the rest of the lab.
"""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts.models import Lab, LabMembership
from apps.research.models import Project, ProjectInvitation, ProjectMember


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture
def lab(db) -> Lab:
    return Lab.objects.create(name="Reyes Lab", slug="reyes-lab")


@pytest.fixture
def pi(db, lab: Lab) -> User:
    user = User.objects.create_user(username="lena", password="p")
    LabMembership.objects.create(
        user=user, lab=lab, role=LabMembership.Role.MEMBER, is_lead=True
    )
    return user


@pytest.fixture
def labmate(db, lab: Lab) -> User:
    user = User.objects.create_user(username="jordan", password="p")
    LabMembership.objects.create(user=user, lab=lab, role=LabMembership.Role.MEMBER)
    return user


@pytest.fixture
def outsider(db) -> User:
    return User.objects.create_user(
        username="sam", password="p", email="Sam@Example.org"
    )


# -- Direct add (lab projects) -------------------------------------------------


@pytest.mark.django_db
def test_pi_adds_a_lab_member_directly(
    client: APIClient, lab: Lab, pi: User, labmate: User
) -> None:
    project = Project.objects.create(name="Reef", scope_lab=lab)

    client.force_authenticate(pi)
    resp = client.post(
        f"/api/projects/{project.id}/members/", {"username": "jordan"}, format="json"
    )
    assert resp.status_code == 201
    assert ProjectMember.objects.filter(project=project, user=labmate).exists()
    # No invitation was involved — that is the point of the direct path.
    assert not ProjectInvitation.objects.filter(project=project).exists()


@pytest.mark.django_db
def test_direct_add_refuses_someone_outside_the_lab(
    client: APIClient, lab: Lab, pi: User, outsider: User
) -> None:
    project = Project.objects.create(name="Reef", scope_lab=lab)

    client.force_authenticate(pi)
    resp = client.post(
        f"/api/projects/{project.id}/members/", {"username": "sam"}, format="json"
    )
    assert resp.status_code == 400
    assert "invite" in str(resp.data).lower()


@pytest.mark.django_db
def test_rank_and_file_member_cannot_add(
    client: APIClient, lab: Lab, labmate: User
) -> None:
    other = User.objects.create_user(username="kai", password="p")
    LabMembership.objects.create(user=other, lab=lab, role=LabMembership.Role.MEMBER)
    project = Project.objects.create(name="Reef", scope_lab=lab)
    ProjectMember.objects.create(project=project, user=labmate)

    client.force_authenticate(labmate)
    resp = client.post(
        f"/api/projects/{project.id}/members/", {"username": "kai"}, format="json"
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_roster_is_readable_and_a_member_is_removable(
    client: APIClient, lab: Lab, pi: User, labmate: User
) -> None:
    project = Project.objects.create(name="Reef", scope_lab=lab)
    ProjectMember.objects.create(project=project, user=labmate)

    client.force_authenticate(pi)
    roster = client.get(f"/api/projects/{project.id}/members/")
    assert roster.status_code == 200
    assert [m["username"] for m in roster.data["items"]] == ["jordan"]

    gone = client.delete(f"/api/projects/{project.id}/members/jordan/")
    assert gone.status_code == 204
    assert not ProjectMember.objects.filter(project=project, user=labmate).exists()


@pytest.mark.django_db
def test_personal_owner_cannot_be_removed(client: APIClient) -> None:
    owner = User.objects.create_user(username="own", password="p")
    project = Project.objects.create(name="Solo", scope_user=owner)
    ProjectMember.objects.create(project=project, user=owner)

    client.force_authenticate(owner)
    resp = client.delete(f"/api/projects/{project.id}/members/own/")
    assert resp.status_code == 400


# -- Invitations ---------------------------------------------------------------


@pytest.mark.django_db
def test_invite_and_accept_puts_someone_on_a_personal_project(
    client: APIClient, outsider: User
) -> None:
    owner = User.objects.create_user(username="own", password="p")
    project = Project.objects.create(name="Solo", scope_user=owner)

    client.force_authenticate(owner)
    sent = client.post(
        f"/api/projects/{project.id}/invitations/",
        {"identifier": "sam", "message": "Want to help with the survey?"},
        format="json",
    )
    assert sent.status_code == 201
    assert sent.data["invitee"]["username"] == "sam"
    assert sent.data["status"] == "pending"
    assert sent.data["scope_name"] == "Personal"

    # The invitee cannot see the project until they accept …
    client.force_authenticate(outsider)
    assert client.get(f"/api/projects/{project.id}/").status_code == 403

    mine = client.get("/api/project-invitations/")
    assert mine.status_code == 200
    assert mine.data["count"] == 1

    answered = client.post(
        f"/api/project-invitations/{sent.data['id']}/respond/",
        {"action": "accept"},
        format="json",
    )
    assert answered.status_code == 200
    assert answered.data["status"] == "accepted"

    # … and does once they have.
    assert client.get(f"/api/projects/{project.id}/").status_code == 200
    assert ProjectMember.objects.filter(project=project, user=outsider).exists()


@pytest.mark.django_db
def test_invite_by_email_is_case_insensitive(
    client: APIClient, outsider: User
) -> None:
    owner = User.objects.create_user(username="own", password="p")
    project = Project.objects.create(name="Solo", scope_user=owner)

    client.force_authenticate(owner)
    resp = client.post(
        f"/api/projects/{project.id}/invitations/",
        {"identifier": "sam@example.org"},
        format="json",
    )
    assert resp.status_code == 201
    assert resp.data["invitee"]["username"] == "sam"


@pytest.mark.django_db
def test_invite_needs_an_existing_account(client: APIClient) -> None:
    owner = User.objects.create_user(username="own", password="p")
    project = Project.objects.create(name="Solo", scope_user=owner)

    client.force_authenticate(owner)
    resp = client.post(
        f"/api/projects/{project.id}/invitations/",
        {"identifier": "nobody@example.org"},
        format="json",
    )
    assert resp.status_code == 400
    assert "sign up" in str(resp.data).lower()


@pytest.mark.django_db
def test_lab_project_invite_grants_the_project_but_not_the_lab(
    client: APIClient, lab: Lab, pi: User, outsider: User
) -> None:
    project = Project.objects.create(name="Reef", scope_lab=lab)
    other = Project.objects.create(name="Other lab work", scope_lab=lab)

    client.force_authenticate(pi)
    sent = client.post(
        f"/api/projects/{project.id}/invitations/",
        {"identifier": "sam"},
        format="json",
    )
    assert sent.status_code == 201
    assert sent.data["scope_name"] == "Reyes Lab"

    client.force_authenticate(outsider)
    client.post(
        f"/api/project-invitations/{sent.data['id']}/respond/",
        {"action": "accept"},
        format="json",
    )
    assert client.get(f"/api/projects/{project.id}/").status_code == 200
    # The lab's other work stays invisible — an invitation is per project.
    assert client.get(f"/api/projects/{other.id}/").status_code == 403
    assert not LabMembership.objects.filter(user=outsider, lab=lab).exists()


@pytest.mark.django_db
def test_reject_and_ignore_leave_the_roster_alone(
    client: APIClient, outsider: User
) -> None:
    owner = User.objects.create_user(username="own", password="p")
    project = Project.objects.create(name="Solo", scope_user=owner)

    for action, expected in (("reject", "rejected"), ("ignore", "ignored")):
        invitation = ProjectInvitation.objects.create(
            project=project, inviter=owner, invitee=outsider
        )
        client.force_authenticate(outsider)
        resp = client.post(
            f"/api/project-invitations/{invitation.id}/respond/",
            {"action": action},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.data["status"] == expected
    assert not ProjectMember.objects.filter(project=project, user=outsider).exists()


@pytest.mark.django_db
def test_answering_twice_conflicts(client: APIClient, outsider: User) -> None:
    owner = User.objects.create_user(username="own", password="p")
    project = Project.objects.create(name="Solo", scope_user=owner)
    invitation = ProjectInvitation.objects.create(
        project=project, inviter=owner, invitee=outsider
    )

    client.force_authenticate(outsider)
    url = f"/api/project-invitations/{invitation.id}/respond/"
    assert client.post(url, {"action": "accept"}, format="json").status_code == 200
    assert client.post(url, {"action": "accept"}, format="json").status_code == 409


@pytest.mark.django_db
def test_only_the_addressee_may_answer(client: APIClient, outsider: User) -> None:
    owner = User.objects.create_user(username="own", password="p")
    stranger = User.objects.create_user(username="nope", password="p")
    project = Project.objects.create(name="Solo", scope_user=owner)
    invitation = ProjectInvitation.objects.create(
        project=project, inviter=owner, invitee=outsider
    )

    client.force_authenticate(stranger)
    resp = client.post(
        f"/api/project-invitations/{invitation.id}/respond/",
        {"action": "accept"},
        format="json",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_duplicate_and_redundant_invites_are_refused(
    client: APIClient, lab: Lab, pi: User, labmate: User, outsider: User
) -> None:
    project = Project.objects.create(name="Reef", scope_lab=lab)
    ProjectMember.objects.create(project=project, user=labmate)

    client.force_authenticate(pi)
    url = f"/api/projects/{project.id}/invitations/"
    assert client.post(url, {"identifier": "jordan"}, format="json").status_code == 400
    assert client.post(url, {"identifier": "sam"}, format="json").status_code == 201
    assert client.post(url, {"identifier": "sam"}, format="json").status_code == 400


@pytest.mark.django_db
def test_editor_lists_and_cancels_a_pending_invite(
    client: APIClient, lab: Lab, pi: User, outsider: User
) -> None:
    project = Project.objects.create(name="Reef", scope_lab=lab)

    client.force_authenticate(pi)
    sent = client.post(
        f"/api/projects/{project.id}/invitations/",
        {"identifier": "sam"},
        format="json",
    )
    listing = client.get(f"/api/projects/{project.id}/invitations/")
    assert listing.data["count"] == 1

    cancelled = client.post(
        f"/api/projects/{project.id}/invitations/{sent.data['id']}/cancel/"
    )
    assert cancelled.status_code == 200
    assert cancelled.data["status"] == "cancelled"
    assert client.get(f"/api/projects/{project.id}/invitations/").data["count"] == 0

    # A cancelled invitation is gone from the invitee's feed too.
    client.force_authenticate(outsider)
    assert client.get("/api/project-invitations/").data["count"] == 0


@pytest.mark.django_db
def test_non_editor_cannot_invite_or_list(
    client: APIClient, lab: Lab, labmate: User, outsider: User
) -> None:
    project = Project.objects.create(name="Reef", scope_lab=lab)
    ProjectMember.objects.create(project=project, user=labmate)

    client.force_authenticate(labmate)
    url = f"/api/projects/{project.id}/invitations/"
    assert client.get(url).status_code == 403
    assert client.post(url, {"identifier": "sam"}, format="json").status_code == 403
