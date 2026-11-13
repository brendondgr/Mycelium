"""A project's one scope decides who sees it and where it may be mentioned.

Plan 20261112-project-scoping, Phase 1: ``Project.visibility``, the module that
reads it (``apps.research.visibility``), oversight kept in ``visible_to``, the
lab's *What the department sees* setting, and ``ProjectMember.role``.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts.models import Department, DeptMembership, Lab, LabMembership
from apps.research import visibility
from apps.research.models import Project, ProjectMember
from apps.research.permissions import user_can_edit_project

pytestmark = pytest.mark.django_db


def _user(name: str) -> User:
    return User.objects.create_user(username=name, password="p")


@pytest.fixture
def world():
    """A department with two labs, their people, and one project per scope."""

    class W:
        pass

    w = W()
    w.dept_head = _user("head")
    w.department = Department.objects.create(owner=w.dept_head, name="Biology")
    w.lab = Lab.objects.create(name="Reef", slug="reef", department=w.department)
    w.sibling = Lab.objects.create(name="Kelp", slug="kelp", department=w.department)
    w.outside_lab = Lab.objects.create(name="Desert", slug="desert")

    w.pi = _user("pi")
    LabMembership.objects.create(
        user=w.pi, lab=w.lab, role=LabMembership.Role.OWNER, is_lead=True
    )
    w.member = _user("member")
    LabMembership.objects.create(user=w.member, lab=w.lab)
    w.on_project = _user("on-project")
    LabMembership.objects.create(user=w.on_project, lab=w.lab)
    w.sibling_member = _user("sibling")
    LabMembership.objects.create(user=w.sibling_member, lab=w.sibling)
    w.dept_member = _user("dept-member")
    DeptMembership.objects.create(user=w.dept_member, department=w.department)
    w.stranger = _user("stranger")  # unverified until a test verifies it
    LabMembership.objects.create(user=w.stranger, lab=w.outside_lab)

    w.p = {}
    for scope in ("invite_only", "lab", "department", "public"):
        project = Project.objects.create(
            name=f"Reef {scope}", scope_lab=w.lab, visibility=scope
        )
        ProjectMember.objects.create(
            project=project, user=w.on_project, role=ProjectMember.Role.OWNER
        )
        w.p[scope] = project
    return w


def _seen(user) -> set[str]:
    """Projects ``user`` may know exist (a directory row)."""
    query = visibility.visible_q(user)
    return set(Project.objects.filter(query).values_list("name", flat=True))


def _opened(user) -> set[str]:
    """Projects ``user`` may open (the full row)."""
    return set(Project.objects.visible_to(user).values_list("name", flat=True))


# -- who sees what -------------------------------------------------------------


def test_each_scope_reaches_exactly_its_audience(world):
    w = world
    every = {f"Reef {s}" for s in ("invite_only", "lab", "department", "public")}
    assert _seen(w.on_project) == every
    assert _seen(w.member) == {"Reef lab", "Reef department", "Reef public"}
    assert _seen(w.sibling_member) == {"Reef department", "Reef public"}
    assert _seen(w.dept_member) == {"Reef department", "Reef public"}
    # ``public`` means any *verified* account on the instance.
    assert _seen(w.stranger) == set()
    profile = w.stranger.profile
    profile.is_verified = True
    profile.save(update_fields=["is_verified"])
    assert _seen(w.stranger) == {"Reef public"}


def test_being_inside_a_scope_does_not_open_the_project(world):
    """Seeing a project exists is a directory row; only members and overseers
    get the full row, so a public project never fills everyone's list."""
    w = world
    profile = w.stranger.profile
    profile.is_verified = True
    profile.save(update_fields=["is_verified"])
    for reader in (w.member, w.sibling_member, w.dept_member, w.stranger):
        assert _opened(reader) == set()
        assert not any(visibility.can_open(reader, p) for p in w.p.values())
    client = APIClient()
    client.force_authenticate(w.member)
    assert client.get("/api/projects/").json() == []
    assert client.get("/api/projects/lab/reef/").json() == []
    assert client.get(f"/api/projects/{w.p['lab'].id}/").status_code == 403
    client.force_authenticate(w.stranger)
    assert client.get("/api/projects/").json() == []
    assert client.get(f"/api/projects/{w.p['public'].id}/").status_code == 403


def test_an_ordinary_lab_member_finds_no_invite_only_project_by_any_route(world):
    w = world
    hidden = w.p["invite_only"]
    client = APIClient()
    client.force_authenticate(w.member)

    listed = {row["name"] for row in client.get("/api/projects/").json()}
    assert hidden.name not in listed
    lab_rows = {row["name"] for row in client.get("/api/projects/lab/reef/").json()}
    assert hidden.name not in lab_rows
    assert client.get(f"/api/projects/{hidden.id}/").status_code == 404
    assert client.post(f"/api/projects/{hidden.id}/leave/").status_code == 404
    assert not visibility.can_see(w.member, hidden)


def test_the_lab_pi_opens_every_project_but_none_is_theirs(world):
    w = world
    assert _opened(w.pi) == {p.name for p in w.p.values()}
    assert all(visibility.can_open(w.pi, p) for p in w.p.values())
    assert not any(visibility.is_participant(w.pi, p) for p in w.p.values())
    assert not Project.objects.filter(members=w.pi).exists()


def test_a_department_head_sees_everything_by_default(world):
    w = world
    assert w.lab.department_sees == Lab.DepartmentSees.EVERYTHING
    assert visibility.can_open(w.dept_head, w.p["invite_only"])
    assert not visibility.is_participant(w.dept_head, w.p["invite_only"])
    assert visibility.names_only_for(w.dept_head, w.department).count() == 0


def test_names_only_narrows_the_department_head_to_reduced_rows(world):
    w = world
    w.lab.department_sees = Lab.DepartmentSees.NAMES_ONLY
    w.lab.save()

    # Can no longer open what its scope keeps from the department...
    assert not visibility.can_open(w.dept_head, w.p["invite_only"])
    assert not visibility.can_open(w.dept_head, w.p["lab"])
    # ...a project scoped to the department is one they know of, as any
    # department member does; its full row waits on membership.
    assert visibility.can_see(w.dept_head, w.p["department"])
    assert not visibility.can_open(w.dept_head, w.p["department"])

    client = APIClient()
    client.force_authenticate(w.dept_head)
    assert client.get(f"/api/projects/{w.p['invite_only'].id}/").status_code == 404
    body = client.get(f"/api/projects/department/{w.department.id}/").json()
    assert body["projects"] == []
    reduced = {row["name"]: row for row in body["names_only"]}
    assert set(reduced) == {p.name for p in w.p.values()}
    row = reduced["Reef invite_only"]
    assert row["owner"]["username"] == "on-project"
    assert row["member_count"] == 1
    assert row["visibility"] == "invite_only"
    for leaked in ("goals", "members", "focus", "description", "state"):
        assert leaked not in row


def test_only_department_heads_get_reduced_rows(world):
    w = world
    w.lab.department_sees = Lab.DepartmentSees.NAMES_ONLY
    w.lab.save()
    client = APIClient()
    client.force_authenticate(w.dept_member)
    body = client.get(f"/api/projects/department/{w.department.id}/").json()
    assert body == {"projects": [], "names_only": []}
    ProjectMember.objects.create(project=w.p["department"], user=w.dept_member)
    body = client.get(f"/api/projects/department/{w.department.id}/").json()
    assert [row["name"] for row in body["projects"]] == ["Reef department"]
    client.force_authenticate(w.stranger)
    assert (
        client.get(f"/api/projects/department/{w.department.id}/").status_code == 403
    )


# -- the department-sees setting -----------------------------------------------


def test_the_lab_pi_sets_what_the_department_sees(world):
    w = world
    client = APIClient()
    url = "/api/auth/labs/reef/department-sees"

    client.force_authenticate(w.member)
    assert client.get(url).json()["department_sees"] == "everything"
    assert client.patch(url, {"department_sees": "names_only"}).status_code == 403

    # The department head cannot narrow or widen a lab's setting.
    client.force_authenticate(w.dept_head)
    assert client.patch(url, {"department_sees": "names_only"}).status_code == 403

    client.force_authenticate(w.pi)
    assert client.patch(url, {"department_sees": "nope"}).status_code == 400
    response = client.patch(url, {"department_sees": "names_only"}, format="json")
    assert response.status_code == 200
    assert response.json() == {"department_sees": "names_only", "department": "Biology"}
    w.lab.refresh_from_db()
    assert w.lab.department_sees == "names_only"

    mine = client.get("/api/auth/labs/").json()
    assert {row["slug"]: row["department_sees"] for row in mine}["reef"] == "names_only"


# -- surfaces -------------------------------------------------------------------


def test_audience_and_may_surface_follow_the_scope(world):
    w = world
    assert [visibility.audience(w.p[s]) for s in w.p] == [
        "member",
        "lab",
        "department",
        "public",
    ]
    assert not visibility.may_surface(w.p["invite_only"], "lab")
    assert visibility.may_surface(w.p["invite_only"], "member")
    assert visibility.may_surface(w.p["lab"], "lab")
    assert not visibility.may_surface(w.p["lab"], "department")
    assert visibility.may_surface(w.p["department"], "department")
    assert visibility.may_surface(w.p["public"], "public")
    assert not visibility.may_surface(w.p["public"], "nowhere")


def test_lab_surfaces_name_only_projects_scoped_to_the_lab_or_wider(world):
    w = world
    names = {p.name for p in visibility.lab_surface_projects(w.lab)}
    assert names == {"Reef lab", "Reef department", "Reef public"}
    assert visibility.lab_held_back(w.lab).count() == 1
    every = {p.name for p in visibility.lab_projects(w.lab)}
    assert "Reef invite_only" in every


def test_allowed_scopes_depend_on_where_the_project_lives(world):
    w = world
    personal = Project.objects.create(name="Mine", scope_user=w.member)
    alone = Project.objects.create(name="Alone", scope_lab=w.outside_lab)
    dept = Project.objects.create(name="Dept", scope_department=w.department)
    assert visibility.allowed_visibilities(personal) == ("invite_only", "public")
    assert "department" not in visibility.allowed_visibilities(alone)
    assert "lab" not in visibility.allowed_visibilities(dept)
    assert "department" in visibility.allowed_visibilities(w.p["lab"])


def test_agent_output_width_follows_the_scope(world):
    w = world
    widths = [visibility.output_width(w.p[s]) for s in w.p]
    assert widths == ["project", "lab", "department", "department"]
    personal = Project.objects.create(
        name="Mine", scope_user=w.member, visibility="public"
    )
    assert visibility.output_width(personal) == "person"


# -- roles and changing scope ---------------------------------------------------


def test_owner_and_editor_roles_edit_but_only_the_owner_rescopes(world):
    w = world
    project = w.p["invite_only"]
    editor = _user("editor")
    ProjectMember.objects.create(
        project=project, user=editor, role=ProjectMember.Role.EDITOR
    )
    plain = _user("plain")
    ProjectMember.objects.create(project=project, user=plain)
    assert user_can_edit_project(w.on_project, project)
    assert user_can_edit_project(editor, project)
    assert not user_can_edit_project(plain, project)

    client = APIClient()
    url = f"/api/projects/{project.id}/"
    client.force_authenticate(editor)
    assert client.patch(url, {"name": "Renamed"}, format="json").status_code == 200
    assert client.patch(url, {"visibility": "lab"}, format="json").status_code == 403

    client.force_authenticate(w.on_project)
    response = client.patch(url, {"visibility": "lab"}, format="json")
    assert response.status_code == 200
    assert response.json()["visibility"] == "lab"
    assert response.json()["my_role"] == "owner"
    project.refresh_from_db()
    assert project.visibility == "lab"

    # The lab's PI holds owner authority as the lab's admin.
    client.force_authenticate(w.pi)
    assert (
        client.patch(url, {"visibility": "invite_only"}, format="json").status_code
        == 200
    )


def test_a_scope_the_project_cannot_take_is_refused(world):
    w = world
    personal = Project.objects.create(name="Mine", scope_user=w.member)
    client = APIClient()
    client.force_authenticate(w.member)
    response = client.patch(
        f"/api/projects/{personal.id}/", {"visibility": "lab"}, format="json"
    )
    assert response.status_code == 400
    response = client.patch(
        f"/api/projects/{personal.id}/", {"visibility": "public"}, format="json"
    )
    assert response.status_code == 200


def test_scope_managers_see_can_edit_per_project_not_per_lab(world):
    """An editor on one lab project must not read as an editor of its siblings
    (the serializer memoizes per lab, which must hold managers only)."""
    w = world
    ProjectMember.objects.create(
        project=w.p["invite_only"], user=w.member, role=ProjectMember.Role.EDITOR
    )
    ProjectMember.objects.create(project=w.p["lab"], user=w.member)
    client = APIClient()
    client.force_authenticate(w.member)
    rows = {row["name"]: row for row in client.get("/api/projects/").json()}
    assert rows["Reef invite_only"]["can_edit"] is True
    assert rows["Reef lab"]["can_edit"] is False
    assert rows["Reef lab"]["my_role"] == "member"


def test_narrowing_drops_a_project_from_lab_surfaces_at_once(world):
    w = world
    project = w.p["lab"]
    assert project in visibility.lab_surface_projects(w.lab)
    project.visibility = "invite_only"
    project.save()
    assert project not in visibility.lab_surface_projects(w.lab)
    assert not visibility.can_see(w.member, project)
    assert not visibility.can_open(w.member, project)
