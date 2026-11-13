"""Phase 2 of the scoping plan: joining by request, the directory, who may
create a project, roles on the roster, and outside collaborators.

Plan 20261112-project-scoping, "Membership", "Outside collaborators" and
Phase 2. The world is one department, two labs, a project per scope.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts.models import (
    Department,
    DeptMembership,
    Lab,
    LabMembership,
    ProjectCreation,
)
from apps.billing.models import Subscription, Tier
from apps.research.models import Project, ProjectJoinRequest, ProjectMember

pytestmark = pytest.mark.django_db

#: Fields a directory row may carry — nothing about goals, state or roster.
DIRECTORY_FIELDS = {
    "id",
    "name",
    "visibility",
    "scope",
    "scope_name",
    "scope_slug",
    "focus",
    "owner",
    "member_count",
    "can_open",
    "can_request",
    "request_status",
}


def _user(name: str, *, verified: bool = False) -> User:
    user = User.objects.create_user(username=name, password="p")
    if verified:
        user.profile.is_verified = True
        user.profile.save(update_fields=["is_verified"])
    return user


@pytest.fixture
def world():
    class W:
        pass

    w = W()
    w.dept_head = _user("head")
    w.department = Department.objects.create(owner=w.dept_head, name="Biology")
    w.lab = Lab.objects.create(name="Reef", slug="reef", department=w.department)
    w.sibling = Lab.objects.create(name="Kelp", slug="kelp", department=w.department)
    Subscription.objects.create(tier=Tier.LAB, scope_lab=w.lab)

    w.pi = _user("pi")
    LabMembership.objects.create(
        user=w.pi, lab=w.lab, role=LabMembership.Role.OWNER, is_lead=True
    )
    w.owner = _user("owner")
    LabMembership.objects.create(user=w.owner, lab=w.lab)
    w.editor = _user("editor")
    LabMembership.objects.create(user=w.editor, lab=w.lab)
    w.member = _user("member")
    LabMembership.objects.create(user=w.member, lab=w.lab)
    w.viewer = _user("viewer")
    LabMembership.objects.create(
        user=w.viewer, lab=w.lab, role=LabMembership.Role.VIEWER
    )
    w.sibling_member = _user("sibling")
    LabMembership.objects.create(user=w.sibling_member, lab=w.sibling)
    w.outsider = _user("outsider", verified=True)

    w.p = {}
    for scope in ("invite_only", "lab", "department", "public"):
        project = Project.objects.create(
            name=f"Reef {scope}",
            scope_lab=w.lab,
            visibility=scope,
            goals={"description": f"Coral {scope} work", "secret": "plans"},
        )
        ProjectMember.objects.create(
            project=project, user=w.owner, role=ProjectMember.Role.OWNER
        )
        ProjectMember.objects.create(
            project=project, user=w.editor, role=ProjectMember.Role.EDITOR
        )
        w.p[scope] = project
    return w


def _as(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


def _names(response) -> set[str]:
    return {row["name"] for row in response.json()["items"]}


# -- the directory -------------------------------------------------------------


def test_the_lab_directory_lists_scoped_projects_as_reduced_rows(world):
    w = world
    resp = _as(w.member).get("/api/projects/lab/reef/directory/")
    assert resp.status_code == 200
    assert _names(resp) == {"Reef lab", "Reef department", "Reef public"}
    for row in resp.json()["items"]:
        assert set(row) == DIRECTORY_FIELDS
        assert row["owner"]["username"] == "owner"
        assert row["member_count"] == 2
        assert row["can_open"] is False
        assert row["can_request"] is True
        assert row["focus"].startswith("Coral")
    # The no-slash form answers too (the Next proxy strips the slash).
    assert _as(w.member).get("/api/projects/lab/reef/directory").status_code == 200


def test_an_invite_only_project_is_in_no_ordinary_members_directory(world):
    w = world
    hidden = w.p["invite_only"].name
    member = _as(w.member)
    for path in (
        "/api/projects/directory/",
        "/api/projects/lab/reef/directory/",
        f"/api/projects/department/{w.department.id}/directory/",
    ):
        assert hidden not in _names(member.get(path))
    # An id guess says nothing either: the same 404 as an id naming nothing.
    assert member.get(f"/api/projects/{w.p['invite_only'].id}/").status_code == 404
    assert (
        member.post(f"/api/projects/{w.p['invite_only'].id}/join-requests/").status_code
        == 404
    )
    # A scoped project they can see but not open is a 403: they know of it.
    assert member.get(f"/api/projects/{w.p['lab'].id}/").status_code == 403


def test_the_pi_finds_every_project_in_the_directory_none_as_theirs(world):
    w = world
    resp = _as(w.pi).get("/api/projects/lab/reef/directory/")
    assert _names(resp) == {p.name for p in w.p.values()}
    assert all(row["can_open"] for row in resp.json()["items"])
    invite_only = next(
        r for r in resp.json()["items"] if r["visibility"] == "invite_only"
    )
    assert invite_only["can_request"] is False
    # Seeing is not belonging: the list marks none of them as the PI's.
    listed = _as(w.pi).get("/api/projects/").json()
    assert listed and not any(row["is_participant"] for row in listed)


def test_projects_the_caller_is_on_are_not_in_their_directory(world):
    w = world
    assert _names(_as(w.owner).get("/api/projects/lab/reef/directory/")) == set()
    mine = _as(w.owner).get("/api/projects/").json()
    assert all(row["is_participant"] for row in mine)


def test_the_department_directory_reaches_the_departments_people(world):
    w = world
    resp = _as(w.sibling_member).get(
        f"/api/projects/department/{w.department.id}/directory/"
    )
    assert resp.status_code == 200
    assert _names(resp) == {"Reef department", "Reef public"}
    # A sibling-lab member has no lab directory of Reef.
    assert (
        _as(w.sibling_member).get("/api/projects/lab/reef/directory/").status_code
        == 403
    )
    assert (
        _as(w.outsider)
        .get(f"/api/projects/department/{w.department.id}/directory/")
        .status_code
        == 403
    )


def test_public_projects_are_in_the_instance_directory_for_verified_accounts(world):
    w = world
    assert _names(_as(w.outsider).get("/api/projects/directory/")) == {"Reef public"}
    unverified = _user("unverified")
    assert _names(_as(unverified).get("/api/projects/directory/")) == set()


def test_archived_projects_leave_the_directory(world):
    w = world
    w.p["lab"].is_archived = True
    w.p["lab"].save()
    assert "Reef lab" not in _names(
        _as(w.member).get("/api/projects/lab/reef/directory/")
    )


# -- join requests -------------------------------------------------------------


def test_request_then_approve_makes_a_member(world):
    w = world
    project = w.p["lab"]
    member = _as(w.member)
    asked = member.post(
        f"/api/projects/{project.id}/join-requests/",
        {"note": "I can help"},
        format="json",
    )
    assert asked.status_code == 201
    assert asked.json()["state"] == "pending"

    # One open request per person per project.
    again = member.post(f"/api/projects/{project.id}/join-requests")
    assert again.status_code == 400
    row = _as(w.member).get("/api/projects/lab/reef/directory/").json()["items"]
    lab_row = next(r for r in row if r["name"] == "Reef lab")
    assert lab_row["request_status"] == "pending"
    assert lab_row["can_request"] is False

    # The owner sees it, on the project and on their bell.
    owner = _as(w.owner)
    listed = owner.get(f"/api/projects/{project.id}/join-requests/").json()
    assert [r["user"]["username"] for r in listed["items"]] == ["member"]
    bell = owner.get("/api/project-join-requests/").json()
    assert [r["user"]["username"] for r in bell["to_decide"]] == ["member"]
    assert [
        r["project_name"]
        for r in member.get("/api/project-join-requests").json()["mine"]
    ] == ["Reef lab"]

    decided = owner.post(
        f"/api/projects/{project.id}/join-requests/{asked.json()['id']}/decide",
        {"action": "approve"},
        format="json",
    )
    assert decided.status_code == 200
    assert decided.json()["state"] == "approved"
    row = ProjectMember.objects.get(project=project, user=w.member)
    assert row.role == ProjectMember.Role.MEMBER
    assert member.get(f"/api/projects/{project.id}/").status_code == 200

    # Told to the requester, on their own bell.
    notes = member.get("/api/notifications/").json()["items"]
    assert any("Reef lab" in n["title"] for n in notes)

    # A second decision on the same request is refused.
    replay = owner.post(
        f"/api/projects/{project.id}/join-requests/{asked.json()['id']}/decide/",
        {"action": "refuse"},
        format="json",
    )
    assert replay.status_code == 409


def test_a_refusal_reaches_the_requester_alone(world):
    w = world
    project = w.p["department"]
    asked = _as(w.sibling_member).post(f"/api/projects/{project.id}/join-requests/")
    assert asked.status_code == 201
    refused = _as(w.editor).post(
        f"/api/projects/{project.id}/join-requests/{asked.json()['id']}/decide/",
        {"action": "refuse"},
        format="json",
    )
    assert refused.status_code == 200
    assert not ProjectMember.objects.filter(
        project=project, user=w.sibling_member
    ).exists()
    # Nobody but the requester was told.
    for other in (w.owner, w.editor, w.pi, w.member):
        titles = [
            n["title"] for n in _as(other).get("/api/notifications/").json()["items"]
        ]
        assert not any("declined" in t for t in titles)
    titles = [
        n["title"]
        for n in _as(w.sibling_member).get("/api/notifications/").json()["items"]
    ]
    assert any("declined" in t for t in titles)


def test_only_the_owner_and_editors_decide(world):
    w = world
    project = w.p["lab"]
    ProjectMember.objects.create(project=project, user=w.viewer)
    asked = _as(w.member).post(f"/api/projects/{project.id}/join-requests/")
    rid = asked.json()["id"]
    # A plain project member may not decide.
    resp = _as(w.viewer).post(
        f"/api/projects/{project.id}/join-requests/{rid}/decide/",
        {"action": "approve"},
        format="json",
    )
    assert resp.status_code == 403
    assert _as(w.viewer).get("/api/project-join-requests/").json()["to_decide"] == []
    assert ProjectJoinRequest.objects.get(pk=rid).state == "pending"


def test_a_request_needs_the_scope(world):
    w = world
    # The sibling lab is outside a lab-scoped project: it is not even seen.
    resp = _as(w.sibling_member).post(f"/api/projects/{w.p['lab'].id}/join-requests/")
    assert resp.status_code == 404
    # An overseer can see an invite-only project but still cannot ask.
    resp = _as(w.pi).post(f"/api/projects/{w.p['invite_only'].id}/join-requests/")
    assert resp.status_code == 403
    # Someone already on it cannot ask.
    resp = _as(w.owner).post(f"/api/projects/{w.p['lab'].id}/join-requests/")
    assert resp.status_code == 400


def test_the_requester_withdraws(world):
    w = world
    asked = _as(w.member).post(f"/api/projects/{w.p['public'].id}/join-requests/")
    rid = asked.json()["id"]
    assert (
        _as(w.owner).post(f"/api/project-join-requests/{rid}/withdraw/").status_code
        == 404
    )
    resp = _as(w.member).post(f"/api/project-join-requests/{rid}/withdraw")
    assert resp.status_code == 200
    assert resp.json()["state"] == "withdrawn"
    # Free to ask again.
    assert (
        _as(w.member)
        .post(f"/api/projects/{w.p['public'].id}/join-requests/")
        .status_code
        == 201
    )


def test_the_project_row_says_whether_the_caller_may_request(world):
    w = world
    # The PI can open the lab-scoped project and is not on it.
    row = _as(w.pi).get(f"/api/projects/{w.p['lab'].id}/").json()
    assert row["can_request"] is True
    assert row["is_participant"] is False
    row = _as(w.pi).get(f"/api/projects/{w.p['invite_only'].id}/").json()
    assert row["can_request"] is False


# -- who can create ------------------------------------------------------------


def test_any_lab_member_creates_by_default_and_becomes_owner(world):
    w = world
    resp = _as(w.member).post(
        "/api/projects/",
        {"name": "Member idea", "lab": "reef", "visibility": "lab"},
        format="json",
    )
    assert resp.status_code == 201
    project = Project.objects.get(name="Member idea")
    assert project.visibility == "lab"
    owner = ProjectMember.objects.get(project=project)
    assert (owner.user, owner.role) == (w.member, ProjectMember.Role.OWNER)
    listed = {r["name"]: r for r in _as(w.member).get("/api/projects/").json()}
    assert listed["Member idea"]["my_role"] == "owner"
    assert listed["Member idea"]["can_change_visibility"] is True


def test_viewers_and_managers_only_labs_refuse_plain_members(world):
    w = world
    body = {"name": "Nope", "lab": "reef"}
    assert _as(w.viewer).post("/api/projects/", body, format="json").status_code == 403
    w.lab.project_creation = ProjectCreation.MANAGERS
    w.lab.save()
    assert _as(w.member).post("/api/projects/", body, format="json").status_code == 403
    assert _as(w.pi).post("/api/projects/", body, format="json").status_code == 201


def test_a_new_project_takes_only_a_scope_its_home_allows(world):
    w = world
    solo = Lab.objects.create(name="Solo", slug="solo")
    Subscription.objects.create(tier=Tier.LAB, scope_lab=solo)
    LabMembership.objects.create(user=w.member, lab=solo)
    resp = _as(w.member).post(
        "/api/projects/",
        {"name": "Too wide", "lab": "solo", "visibility": "department"},
        format="json",
    )
    assert resp.status_code == 400
    assert not Project.objects.filter(name="Too wide").exists()
    resp = _as(w.member).post(
        "/api/projects/", {"name": "Default", "lab": "solo"}, format="json"
    )
    assert Project.objects.get(name="Default").visibility == "invite_only"
    assert resp.status_code == 201


def test_the_lab_setting_is_the_pis(world):
    w = world
    path = "/api/auth/labs/reef/project-creation/"
    got = _as(w.member).get(path).json()
    assert got == {"project_creation": "members", "can_create": True}
    assert _as(w.viewer).get(path).json()["can_create"] is False
    assert (
        _as(w.member)
        .patch(path, {"project_creation": "managers"}, format="json")
        .status_code
        == 403
    )
    resp = _as(w.pi).patch(
        "/api/auth/labs/reef/project-creation",
        {"project_creation": "managers"},
        format="json",
    )
    assert resp.status_code == 200
    w.lab.refresh_from_db()
    assert w.lab.project_creation == "managers"
    assert _as(w.member).get(path).json()["can_create"] is False
    assert (
        _as(w.pi).patch(path, {"project_creation": "anyone"}, format="json").status_code
        == 400
    )
    # The workspace switcher carries it.
    labs = {row["slug"]: row for row in _as(w.member).get("/api/auth/labs/").json()}
    assert labs["reef"]["project_creation"] == "managers"
    assert labs["reef"]["can_create_projects"] is False


def test_departments_have_the_same_setting(world):
    w = world
    Subscription.objects.create(tier=Tier.CANOPY, scope_department=w.department)
    dept_member = _user("dept-member")
    DeptMembership.objects.create(user=dept_member, department=w.department)
    body = {"name": "Dept idea", "department": str(w.department.id)}
    resp = _as(dept_member).post("/api/projects/", body, format="json")
    assert resp.status_code == 201
    project = Project.objects.get(name="Dept idea")
    assert ProjectMember.objects.get(project=project).role == "owner"

    path = f"/api/auth/departments/{w.department.id}/project-creation/"
    assert (
        _as(dept_member)
        .patch(path, {"project_creation": "managers"}, format="json")
        .status_code
        == 403
    )
    assert (
        _as(w.dept_head)
        .patch(path, {"project_creation": "managers"}, format="json")
        .status_code
        == 200
    )
    body["name"] = "Second"
    assert (
        _as(dept_member).post("/api/projects/", body, format="json").status_code == 403
    )


# -- roles on the roster -------------------------------------------------------


def test_the_owner_sets_roles_and_cannot_be_removed(world):
    w = world
    project = w.p["lab"]
    ProjectMember.objects.create(project=project, user=w.member)
    path = f"/api/projects/{project.id}/members/member/"
    # An editor does not hand out roles.
    assert (
        _as(w.editor).patch(path, {"role": "editor"}, format="json").status_code == 403
    )
    resp = _as(w.owner).patch(path, {"role": "editor"}, format="json")
    assert resp.status_code == 200
    roles = {m["username"]: m["role"] for m in resp.json()["members"]}
    assert roles == {"editor": "editor", "member": "editor", "owner": "owner"}
    # The owner row stays.
    resp = _as(w.editor).delete(f"/api/projects/{project.id}/members/owner/")
    assert resp.status_code == 400
    assert (
        _as(w.owner)
        .patch(
            f"/api/projects/{project.id}/members/owner/",
            {"role": "member"},
            format="json",
        )
        .status_code
        == 400
    )


# -- outside collaborators -----------------------------------------------------


def test_only_the_owner_invites_from_outside_the_lab(world):
    w = world
    project = w.p["invite_only"]
    path = f"/api/projects/{project.id}/invitations/"
    resp = _as(w.editor).post(path, {"identifier": "outsider"}, format="json")
    assert resp.status_code == 403
    # An editor may still invite someone in the lab.
    assert (
        _as(w.editor).post(path, {"identifier": "member"}, format="json").status_code
        == 201
    )
    resp = _as(w.owner).post(path, {"identifier": "outsider"}, format="json")
    assert resp.status_code == 201


def test_an_outside_collaborator_sees_that_project_and_nothing_else(world):
    w = world
    project = w.p["invite_only"]
    sent = _as(w.owner).post(
        f"/api/projects/{project.id}/invitations/",
        {"identifier": "outsider"},
        format="json",
    )
    outsider = _as(w.outsider)
    outsider.post(
        f"/api/project-invitations/{sent.json()['id']}/respond/",
        {"action": "accept"},
        format="json",
    )
    row = outsider.get(f"/api/projects/{project.id}/")
    assert row.status_code == 200
    members = {m["username"]: m for m in row.json()["members"]}
    assert members["outsider"]["outside"] is True
    assert members["owner"]["outside"] is False
    # The team card's roster route says the same.
    roster = outsider.get(f"/api/projects/{project.id}/members/").json()["items"]
    assert {m["username"]: m["outside"] for m in roster}["outsider"] is True

    # Nothing else of the lab: no lab list, directory or roster, no other project.
    assert outsider.get("/api/projects/lab/reef/").status_code == 403
    assert outsider.get("/api/projects/lab/reef/directory/").status_code == 403
    assert outsider.get("/api/auth/labs/reef/members/").status_code == 403
    assert outsider.get(f"/api/projects/{w.p['lab'].id}/").status_code == 404
    assert _names(outsider.get("/api/projects/directory/")) == {"Reef public"}
    assert not LabMembership.objects.filter(user=w.outsider, lab=w.lab).exists()
