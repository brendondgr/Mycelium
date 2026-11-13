"""Changing scope, handing over, and leaving (scoping plan, Phase 5)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts.models import Department, Lab, LabMembership
from apps.accounts.services import detach_lab_from_department, remove_lab_member
from apps.research import visibility
from apps.research.models import Project, ProjectMember, ProjectTransfer

pytestmark = pytest.mark.django_db


def _verified(*users):
    from apps.accounts.models import Profile

    for user in users:
        Profile.objects.filter(user=user).update(is_verified=True)


@pytest.fixture
def org(db):
    head = User.objects.create_user("head", "head@example.org", "pw")
    pi = User.objects.create_user("pi", "pi@example.org", "pw")
    own = User.objects.create_user("own", "own@example.org", "pw")
    ed = User.objects.create_user("ed", "ed@example.org", "pw")
    mem = User.objects.create_user("mem", "mem@example.org", "pw")
    _verified(head, pi, own, ed, mem)
    dept = Department.objects.create(owner=head, name="Biology")
    lab = Lab.objects.create(name="Reef", slug="reef-life", department=dept)
    LabMembership.objects.create(
        user=pi, lab=lab, role=LabMembership.Role.OWNER, is_lead=True
    )
    for user in (own, ed, mem):
        LabMembership.objects.create(user=user, lab=lab)
    project = Project.objects.create(name="Kelp", scope_lab=lab, visibility="lab")
    ProjectMember.objects.create(
        project=project, user=own, role=ProjectMember.Role.OWNER
    )
    ProjectMember.objects.create(
        project=project, user=ed, role=ProjectMember.Role.EDITOR
    )
    ProjectMember.objects.create(project=project, user=mem)
    return SimpleNamespace(
        head=head, pi=pi, own=own, ed=ed, mem=mem, dept=dept, lab=lab, project=project
    )


def _client(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def _bell(user):
    from tools.delivery.models import Notification

    return list(
        Notification.objects.filter(
            user=user, kind=Notification.Kind.PROJECT_SCOPE
        ).values_list("title", flat=True)
    )


# --------------------------------------------------------------------------- #
# Leaving
# --------------------------------------------------------------------------- #
def test_leaving_a_lab_ends_membership_in_its_projects(org):
    remove_lab_member(org.lab, org.mem)
    assert not ProjectMember.objects.filter(project=org.project, user=org.mem).exists()


def test_an_owner_who_leaves_hands_the_project_to_an_editor(org):
    remove_lab_member(org.lab, org.own)
    assert visibility.owner_of(org.project) == org.ed
    assert _bell(org.mem)  # the members are told


def test_without_an_editor_ownership_falls_to_the_labs_pi(org):
    ProjectMember.objects.filter(user=org.ed).delete()
    remove_lab_member(org.lab, org.own)
    assert visibility.owner_of(org.project) == org.pi


def test_an_owner_deleting_their_account_hands_over_first(org):
    org.own.delete()
    assert visibility.owner_of(org.project) == org.ed


def test_the_owner_may_invite_a_leaver_back_as_an_outside_collaborator(org):
    remove_lab_member(org.lab, org.mem)
    response = _client(org.own).post(
        f"/api/projects/{org.project.pk}/invitations/",
        {"identifier": "mem"},
        format="json",
    )
    assert response.status_code in (200, 201), response.content


# --------------------------------------------------------------------------- #
# Ownership
# --------------------------------------------------------------------------- #
def test_the_owner_hands_over_to_a_member(org):
    response = _client(org.own).post(
        f"/api/projects/{org.project.pk}/ownership/", {"username": "mem"}, format="json"
    )
    assert response.status_code == 200, response.content
    assert visibility.owner_of(org.project) == org.mem
    assert ProjectMember.objects.get(project=org.project, user=org.own).role == "editor"


def test_an_editor_cannot_hand_over(org):
    response = _client(org.ed).post(
        f"/api/projects/{org.project.pk}/ownership/", {"username": "ed"}, format="json"
    )
    assert response.status_code == 403


def test_the_labs_pi_may_take_ownership(org):
    response = _client(org.pi).post(
        f"/api/projects/{org.project.pk}/ownership/", {"username": "pi"}, format="json"
    )
    assert response.status_code == 200, response.content
    assert visibility.owner_of(org.project) == org.pi
    assert _bell(org.own)


def test_ownership_goes_only_to_a_member_unless_taken(org):
    stranger = User.objects.create_user("x", "x@example.org", "pw")
    response = _client(org.own).post(
        f"/api/projects/{org.project.pk}/ownership/",
        {"username": stranger.username},
        format="json",
    )
    assert response.status_code == 400


# --------------------------------------------------------------------------- #
# Widening and narrowing
# --------------------------------------------------------------------------- #
def test_widening_tells_every_member_and_says_who_newly_sees_it(org):
    response = _client(org.own).patch(
        f"/api/projects/{org.project.pk}/", {"visibility": "department"}, format="json"
    )
    assert response.status_code == 200, response.content
    assert response.json()["scope_change"]["widened"] is True
    assert "Biology" in response.json()["scope_change"]["newly_visible_to"]
    assert _bell(org.mem) and _bell(org.ed)
    assert not _bell(org.own)  # the owner made the change


# --------------------------------------------------------------------------- #
# A lab leaving its department
# --------------------------------------------------------------------------- #
def test_department_projects_fall_back_to_lab_when_the_lab_leaves(org):
    org.project.visibility = "department"
    org.project.save(update_fields=["visibility"])
    assert visibility.can_open(org.head, org.project)

    detach_lab_from_department(org.dept, org.lab, actor=org.head)
    org.project.refresh_from_db()
    assert org.project.visibility == "lab"
    assert not visibility.can_open(org.head, org.project)
    assert _bell(org.own)


def test_a_project_is_transferred_to_the_department_before_the_lab_leaves(org):
    offered = _client(org.own).post(f"/api/projects/{org.project.pk}/transfer/")
    assert offered.status_code == 201, offered.content
    # Only a department head accepts.
    assert (
        _client(org.pi)
        .post(f"/api/projects/{org.project.pk}/transfer/accept/")
        .status_code
        == 403
    )
    accepted = _client(org.head).post(
        f"/api/projects/{org.project.pk}/transfer/accept/"
    )
    assert accepted.status_code == 200, accepted.content

    org.project.refresh_from_db()
    assert org.project.scope_lab_id is None
    assert org.project.scope_department_id == org.dept.pk
    assert org.project.visibility == "invite_only"  # never wider than chosen
    assert set(org.project.members.values_list("username", flat=True)) == {
        "own",
        "ed",
        "mem",
    }
    assert ProjectTransfer.objects.get().state == "accepted"

    detach_lab_from_department(org.dept, org.lab, actor=org.head)
    assert visibility.can_open(org.head, Project.objects.get(pk=org.project.pk))


def test_only_the_owner_offers_a_transfer(org):
    assert (
        _client(org.ed).post(f"/api/projects/{org.project.pk}/transfer/").status_code
        == 403
    )


def test_an_open_offer_lapses_when_the_lab_leaves(org):
    _client(org.own).post(f"/api/projects/{org.project.pk}/transfer/")
    detach_lab_from_department(org.dept, org.lab, actor=org.head)
    assert ProjectTransfer.objects.get().state == "lapsed"


def test_the_ownership_state_says_who_may_do_what(org):
    url = f"/api/projects/{org.project.pk}/transfer/"

    owner = _client(org.own).get(url).json()
    assert owner["can_hand_over"] is True
    assert owner["can_offer"] is True
    assert owner["can_take"] is False
    assert owner["department"] == "Biology"
    assert owner["transfer"] is None

    # The lab's PI is not the owner but may take the project.
    pi = _client(org.pi).get(url).json()
    assert pi["can_take"] is True
    assert pi["can_hand_over"] is True  # a manager holds the owner's authority

    # An ordinary member can do none of it.
    member = _client(org.mem).get(url).json()
    assert member["can_hand_over"] is False
    assert member["can_take"] is False
    assert member["can_offer"] is False

    assert _client(org.own).post(url).status_code == 201
    owner = _client(org.own).get(url).json()
    assert owner["can_offer"] is False
    assert owner["transfer"] == {
        "department": "Biology",
        "can_accept": False,
        "can_withdraw": True,
    }
    assert _client(org.head).get(url).json()["transfer"]["can_accept"] is True
