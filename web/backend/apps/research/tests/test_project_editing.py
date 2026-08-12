"""A project's editable fundamentals and the permission flags the page reads.

The project page shows a name, a description, a status, and a progress figure,
and offers an Edit action to whoever may use it. None of those display fields are
model columns — they live in the free-form ``goals`` JSON — and the edit right is
reported on the row so the UI never has to infer it from the active workspace.
"""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts.models import Lab, LabMembership
from apps.research.models import Project, ProjectMember


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.mark.django_db
def test_description_prefers_explicit_goal_then_focus_statement(
    client: APIClient,
) -> None:
    user = User.objects.create_user(username="u", password="p")
    explicit = Project.objects.create(
        name="Explicit", scope_user=user, goals={"description": "  Reef survey  "}
    )
    # A wizard-created project has no `description`; its purpose lives in the
    # composed focus statement, and that is what the page should show.
    composed = Project.objects.create(
        name="Composed",
        scope_user=user,
        goals={
            "interests": {"areas": ["Robotics"], "statement": "Surgical VLA models"}
        },
    )
    blank = Project.objects.create(name="Blank", scope_user=user)

    client.force_authenticate(user)
    rows = {r["name"]: r for r in client.get("/api/projects/").data}
    assert rows["Explicit"]["description"] == "Reef survey"
    assert rows["Composed"]["description"] == "Surgical VLA models"
    assert rows["Blank"]["description"] is None
    assert {explicit.id, composed.id, blank.id}  # all three are visible


@pytest.mark.django_db
def test_owner_edits_the_display_fields(client: APIClient) -> None:
    user = User.objects.create_user(username="u", password="p")
    project = Project.objects.create(
        name="Reef", scope_user=user, goals={"interests": {"areas": ["Coral"]}}
    )

    client.force_authenticate(user)
    resp = client.patch(
        f"/api/projects/{project.id}/",
        {
            "name": "Reef mapping",
            "description": "Mapping bleaching events across the outer reef.",
            "status": "In review",
            "progress": 40,
        },
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["name"] == "Reef mapping"
    assert resp.data["description"] == "Mapping bleaching events across the outer reef."
    assert resp.data["status"] == "In review"
    assert resp.data["progress"] == 40

    project.refresh_from_db()
    # The focus is untouched by a display-field edit.
    assert project.goals["interests"]["areas"] == ["Coral"]


@pytest.mark.django_db
def test_blank_and_null_clear_rather_than_store_empty(client: APIClient) -> None:
    user = User.objects.create_user(username="u", password="p")
    project = Project.objects.create(
        name="Reef",
        scope_user=user,
        goals={"description": "old", "status": "Planning", "progress": 10},
    )

    client.force_authenticate(user)
    resp = client.patch(
        f"/api/projects/{project.id}/",
        {"description": "", "status": "  ", "progress": None},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["description"] is None
    assert resp.data["status"] is None
    assert resp.data["progress"] is None

    project.refresh_from_db()
    for key in ("description", "status", "progress"):
        assert key not in project.goals


@pytest.mark.django_db
def test_progress_is_bounded(client: APIClient) -> None:
    user = User.objects.create_user(username="u", password="p")
    project = Project.objects.create(name="Reef", scope_user=user)

    client.force_authenticate(user)
    resp = client.patch(
        f"/api/projects/{project.id}/", {"progress": 140}, format="json"
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_only_a_search_surface_change_re_seeds(
    client: APIClient, monkeypatch
) -> None:
    """Re-seeding is a whole-corpus pass — a rename must not buy one.

    The editor posts the whole form on every save, so keying the re-seed off
    "was `focus` in the request?" would refit the corpus for a typo fix.
    """
    user = User.objects.create_user(username="u", password="p")
    project = Project.objects.create(
        name="Reef",
        scope_user=user,
        goals={"interests": {"areas": ["Coral"], "keywords": [], "statement": ""}},
    )

    seeded: list[str] = []
    monkeypatch.setattr(
        "apps.research.views._seed_project",
        lambda p: seeded.append(str(p.id)),
    )

    client.force_authenticate(user)
    url = f"/api/projects/{project.id}/"

    # Same focus, new name and description → no re-seed.
    client.patch(
        url,
        {
            "name": "Reef mapping",
            "description": "Now with a description.",
            "focus": {"areas": ["Coral"], "keywords": [], "statement": ""},
            "watch_categories": ["papers", "grants", "fellowships", "conferences"],
        },
        format="json",
    )
    assert seeded == []

    # A genuinely different focus → one re-seed.
    client.patch(
        url,
        {"focus": {"areas": ["Coral", "Bleaching"], "keywords": [], "statement": ""}},
        format="json",
    )
    assert seeded == [str(project.id)]

    # Narrowing the tracked areas is also a search-surface change.
    client.patch(url, {"watch_categories": ["papers"]}, format="json")
    assert len(seeded) == 2


@pytest.mark.django_db
def test_lab_pi_may_edit_a_lab_project(client: APIClient) -> None:
    """A lead PI creates lab projects, so a lead PI edits them.

    The edit gate used to be owner/admin only while creation allowed the PI, which
    left a PI holding controls the API refused.
    """
    pi = User.objects.create_user(username="lena", password="p")
    lab = Lab.objects.create(name="Reyes Lab", slug="reyes-lab")
    LabMembership.objects.create(
        user=pi, lab=lab, role=LabMembership.Role.MEMBER, is_lead=True
    )
    project = Project.objects.create(name="Reef", scope_lab=lab)

    client.force_authenticate(pi)
    resp = client.patch(
        f"/api/projects/{project.id}/", {"status": "Active"}, format="json"
    )
    assert resp.status_code == 200
    assert resp.data["can_edit"] is True
    assert resp.data["can_manage_members"] is True


@pytest.mark.django_db
def test_permission_flags_and_scope_slug_on_the_row(client: APIClient) -> None:
    owner = User.objects.create_user(username="own", password="p")
    member = User.objects.create_user(username="mbr", password="p")
    lab = Lab.objects.create(name="Reyes Lab", slug="reyes-lab")
    LabMembership.objects.create(user=owner, lab=lab, role=LabMembership.Role.OWNER)
    LabMembership.objects.create(user=member, lab=lab, role=LabMembership.Role.MEMBER)
    project = Project.objects.create(name="Reef", scope_lab=lab)
    ProjectMember.objects.create(project=project, user=member)

    client.force_authenticate(member)
    row = client.get(f"/api/projects/{project.id}/").data
    assert row["scope"] == "lab"
    assert row["scope_slug"] == "reyes-lab"
    assert row["scope_name"] == "Reyes Lab"
    assert row["can_edit"] is False

    client.force_authenticate(owner)
    row = client.get(f"/api/projects/{project.id}/").data
    assert row["can_edit"] is True


@pytest.mark.django_db
def test_personal_project_row_has_no_lab_slug(client: APIClient) -> None:
    user = User.objects.create_user(username="u", password="p")
    project = Project.objects.create(name="Solo", scope_user=user)

    client.force_authenticate(user)
    row = client.get(f"/api/projects/{project.id}/").data
    assert row["scope"] == "user"
    assert row["scope_slug"] is None
    assert row["scope_name"] == "Personal"
    assert row["can_edit"] is True
