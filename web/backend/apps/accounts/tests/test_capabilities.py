"""Role presets, the thin permission functions, and what ``/me`` tells the app.

``apps.accounts.capabilities`` is the one place a role turns into rights. These
pin the presets (a lead PI holds every admin capability; only the head or owner
may transfer; every member may see the roster), that the old permission
functions now agree with it exactly, that the head's membership row follows
``Department.owner``, and that the app receives each org's capabilities, the
roles it may grant, and which roster rows it may act on.
"""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts import capabilities as caps
from apps.accounts import permissions as perms
from apps.accounts.models import DeptMembership, LabMembership
from apps.billing.services import create_department_workspace, create_lab_workspace

from .conftest import verified

ADMIN_SET = set(caps.CAPABILITIES) - {caps.TRANSFER}


def _user(name: str) -> User:
    return verified(User.objects.create_user(username=name, password="p"))


@pytest.fixture
def lab_people():
    """A lab with an owner (the founder, also its lead) and one of each role."""
    owner = _user("owner")
    lab = create_lab_workspace(owner, "Soil Lab").lab
    people = {"owner": owner}
    for role in ("admin", "member", "viewer"):
        people[role] = _user(role)
        LabMembership.objects.create(lab=lab, user=people[role], role=role)
    # A second lead PI who holds only the member role.
    LabMembership.objects.filter(lab=lab, user=owner).update(is_lead=False)
    people["lead"] = _user("lead")
    LabMembership.objects.create(
        lab=lab, user=people["lead"], role="member", is_lead=True
    )
    people["stranger"] = _user("stranger")
    return lab, people


@pytest.fixture
def dept_people():
    """A department with its head, one of each direct role, and a lab affiliate."""
    head = _user("head")
    department = create_department_workspace(head, "Earth Sciences").department
    people = {"head": head}
    for role in ("admin", "member", "viewer"):
        people[role] = _user(f"d_{role}")
        DeptMembership.objects.create(
            department=department, user=people[role], role=role
        )
    # An OWNER row on someone who is not the head counts as admin only.
    people["stray"] = _user("stray")
    DeptMembership.objects.create(
        department=department, user=people["stray"], role="owner"
    )
    lab_pi = _user("lab_pi")
    lab = create_lab_workspace(lab_pi, "Rock Lab").lab
    lab.department = department
    lab.save(update_fields=["department"])
    people["affiliate"] = lab_pi
    people["stranger"] = _user("d_stranger")
    return department, people


# -- Presets ------------------------------------------------------------------


@pytest.mark.django_db
def test_lab_presets(lab_people) -> None:
    lab, people = lab_people
    expected = {
        "owner": set(caps.CAPABILITIES),
        "admin": ADMIN_SET,
        "lead": ADMIN_SET,
        "member": {caps.PEOPLE_VIEW},
        "viewer": {caps.PEOPLE_VIEW},
        "stranger": set(),
    }
    for who, want in expected.items():
        assert set(caps.lab_capabilities(people[who], lab)) == want, who


@pytest.mark.django_db
def test_a_lead_pi_holds_every_admin_capability(lab_people) -> None:
    lab, people = lab_people
    assert caps.lab_capabilities(people["lead"], lab) == caps.lab_capabilities(
        people["admin"], lab
    )


@pytest.mark.django_db
def test_department_presets(dept_people) -> None:
    department, people = dept_people
    expected = {
        "head": set(caps.CAPABILITIES),
        "admin": ADMIN_SET,
        "stray": ADMIN_SET,
        "member": {caps.PEOPLE_VIEW},
        "viewer": {caps.PEOPLE_VIEW},
        "affiliate": {caps.PEOPLE_VIEW},
        "stranger": set(),
    }
    for who, want in expected.items():
        assert set(caps.dept_capabilities(people[who], department)) == want, who


def test_presets_name_only_known_capabilities() -> None:
    for presets in (caps.LAB_PRESETS, caps.DEPT_PRESETS):
        for preset in presets.values():
            assert preset <= set(caps.CAPABILITIES)
            # Every preset is a member: membership reads as a non-empty set.
            assert caps.PEOPLE_VIEW in preset


@pytest.mark.django_db
def test_an_unknown_capability_is_an_error(lab_people) -> None:
    lab, people = lab_people
    with pytest.raises(ValueError):
        caps.has_capability(people["owner"], lab, "org.everything")


# -- The old names are thin calls that agree ------------------------------------


@pytest.mark.django_db
def test_lab_permission_functions_agree_with_capabilities(lab_people) -> None:
    lab, people = lab_people
    for who, user in people.items():
        held = caps.lab_capabilities(user, lab)
        assert perms.user_has_lab_access(user, lab) == bool(held), who
        assert perms.user_can_manage_lab(user, lab) == (caps.PEOPLE_MANAGE in held), who
        assert perms.user_can_edit_lab_profile(user, lab) == (
            caps.PROFILE_EDIT in held
        ), who
        assert perms.user_can_invite_to_lab(user, lab) == (
            caps.INVITES_ISSUE in held
        ), who


@pytest.mark.django_db
def test_department_permission_functions_agree_with_capabilities(
    dept_people,
) -> None:
    department, people = dept_people
    for who, user in people.items():
        held = caps.dept_capabilities(user, department)
        assert perms.user_has_department_access(user, department) == bool(held), who
        assert perms.user_can_manage_department(user, department) == (
            caps.PEOPLE_MANAGE in held
        ), who
        assert perms.user_can_edit_dept_profile(user, department) == (
            caps.PROFILE_EDIT in held
        ), who
        assert perms.user_can_invite_to_department(user, department) == (
            caps.INVITES_ISSUE in held
        ), who


@pytest.mark.django_db
def test_bulk_manager_query_agrees_with_capabilities(lab_people) -> None:
    lab, people = lab_people
    managers = set(
        LabMembership.objects.filter(lab=lab)
        .filter(perms.lab_manager_q())
        .values_list("user__username", flat=True)
    )
    expected = {
        user.username
        for user in people.values()
        if caps.has_capability(user, lab, caps.PEOPLE_MANAGE)
    }
    assert managers == expected == {"owner", "admin", "lead"}


@pytest.mark.django_db
def test_discord_gate_levels_are_capabilities(lab_people) -> None:
    from apps.integrations.services.gate import _has_lab_permission

    lab, people = lab_people
    for who, user in people.items():
        held = caps.lab_capabilities(user, lab)
        assert _has_lab_permission(user, lab, "manage") == (
            caps.SERVERS_MANAGE in held
        ), who
        assert _has_lab_permission(user, lab, "edit") == (caps.PROFILE_EDIT in held), (
            who
        )
        assert _has_lab_permission(user, lab, "access") == bool(held), who


# -- The head's row follows Department.owner --------------------------------------


@pytest.mark.django_db
def test_changing_the_head_moves_the_owner_row(dept_people) -> None:
    department, people = dept_people
    department.owner = people["member"]
    department.save()

    owners = DeptMembership.objects.filter(
        department=department, role=DeptMembership.Role.OWNER
    )
    assert list(owners.values_list("user__username", flat=True)) == ["d_member"]
    # The old head and the stray owner row are admins now, not heads.
    assert DeptMembership.objects.get(
        department=department, user=people["head"]
    ).role == ("admin")
    assert DeptMembership.objects.get(
        department=department, user=people["stray"]
    ).role == ("admin")
    assert caps.has_capability(people["member"], department, caps.TRANSFER)
    assert not caps.has_capability(people["head"], department, caps.TRANSFER)


@pytest.mark.django_db
def test_a_new_head_without_a_row_gets_one(dept_people) -> None:
    department, people = dept_people
    department.owner = people["stranger"]
    department.save()
    row = DeptMembership.objects.get(department=department, user=people["stranger"])
    assert row.role == DeptMembership.Role.OWNER


# -- What the app is told ---------------------------------------------------------


@pytest.mark.django_db
def test_me_carries_capabilities_per_org(lab_people, dept_people) -> None:
    lab, people = lab_people
    department, dpeople = dept_people
    DeptMembership.objects.create(
        department=department, user=people["lead"], role="viewer"
    )
    client = APIClient()
    client.force_authenticate(people["lead"])

    body = client.get("/api/auth/me/").json()

    assert set(body["capabilities"]["labs"][lab.slug]) == ADMIN_SET
    assert body["capabilities"]["departments"][str(department.id)] == [caps.PEOPLE_VIEW]
    # Lists follow the closed list's order.
    assert body["capabilities"]["labs"][lab.slug] == [
        c for c in caps.CAPABILITIES if c in ADMIN_SET
    ]


@pytest.mark.django_db
def test_me_leaves_out_departments_held_only_through_a_lab(dept_people) -> None:
    department, people = dept_people
    client = APIClient()
    client.force_authenticate(people["affiliate"])
    body = client.get("/api/auth/me/").json()
    assert str(department.id) not in body["capabilities"]["departments"]


@pytest.mark.django_db
def test_my_labs_rows_carry_capabilities_and_grantable_roles(lab_people) -> None:
    lab, people = lab_people
    client = APIClient()
    expected_roles = {
        "owner": ["admin", "member", "viewer"],
        "admin": ["member", "viewer"],
        "lead": ["member", "viewer"],
        # A member outranks a viewer but manages nobody: the API refuses
        # their grants, so the row must not offer any.
        "member": [],
        "viewer": [],
    }
    for who, roles in expected_roles.items():
        client.force_authenticate(people[who])
        rows = client.get("/api/auth/labs/").json()
        row = next(r for r in rows if r["slug"] == lab.slug)
        assert row["grantable_roles"] == roles, who
        assert set(row["capabilities"]) == set(
            caps.lab_capabilities(people[who], lab)
        ), who


@pytest.mark.django_db
def test_my_departments_rows_carry_capabilities_and_grantable_roles(
    dept_people,
) -> None:
    department, people = dept_people
    client = APIClient()
    expected_roles = {
        "head": ["admin", "member", "viewer"],
        "admin": ["member", "viewer"],
        "stray": ["member", "viewer"],
        "member": [],  # outranks a viewer, manages nobody
        "viewer": [],
    }
    for who, roles in expected_roles.items():
        client.force_authenticate(people[who])
        rows = client.get("/api/auth/departments/").json()
        row = next(r for r in rows if r["id"] == str(department.id))
        assert row["grantable_roles"] == roles, who
        assert set(row["capabilities"]) == set(
            caps.dept_capabilities(people[who], department)
        ), who


@pytest.mark.django_db
def test_lab_roster_says_which_rows_the_caller_may_act_on(lab_people) -> None:
    lab, people = lab_people
    client = APIClient()
    client.force_authenticate(people["admin"])

    rows = {
        r["username"]: r["can_act"]
        for r in client.get(f"/api/auth/labs/{lab.slug}/members/").json()
    }

    assert rows == {
        "owner": False,  # above them
        "admin": False,  # themselves
        "lead": False,  # a lead ranks as an admin
        "member": True,
        "viewer": True,
    }


@pytest.mark.django_db
def test_department_roster_says_which_rows_the_caller_may_act_on(
    dept_people,
) -> None:
    department, people = dept_people
    client = APIClient()
    client.force_authenticate(people["admin"])

    rows = {
        r["username"]: r["can_act"]
        for r in client.get(f"/api/auth/departments/{department.id}/members/").json()
    }

    assert rows == {
        "head": False,
        "d_admin": False,
        "stray": False,
        "d_member": True,
        "d_viewer": True,
        "lab_pi": False,  # folded in through a lab: no department role
    }


@pytest.mark.django_db
def test_a_member_may_act_on_nobody_though_they_outrank_a_viewer(
    lab_people, dept_people
) -> None:
    """``can_act`` follows what the API allows, not rank alone."""
    lab, people = lab_people
    client = APIClient()
    client.force_authenticate(people["member"])
    rows = client.get(f"/api/auth/labs/{lab.slug}/members/").json()
    assert not any(r["can_act"] for r in rows)
    refused = client.patch(
        f"/api/auth/labs/{lab.slug}/members/viewer/", {"role": "viewer"}, format="json"
    )
    assert refused.status_code == 403

    department, dpeople = dept_people
    client.force_authenticate(dpeople["member"])
    rows = client.get(f"/api/auth/departments/{department.id}/members/").json()
    assert not any(r["can_act"] for r in rows)
    refused = client.delete(f"/api/auth/departments/{department.id}/members/d_viewer/")
    assert refused.status_code == 403
