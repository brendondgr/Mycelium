import pytest
from django.contrib.auth.models import User

from apps.accounts.models import Department, DeptMembership, Lab, LabMembership
from apps.accounts.services import (
    effective_member_count,
    effective_member_ids,
    effective_members,
    lab_lead_count,
)


@pytest.fixture
def owner(db: None) -> User:
    return User.objects.create_user(username="owner", password="pass-123")


@pytest.fixture
def department(owner: User) -> Department:
    return Department.objects.create(owner=owner, name="Neuroscience")


def add_user(username: str) -> User:
    return User.objects.create_user(username=username, password="pass-123")


@pytest.mark.django_db
def test_effective_membership_unions_direct_and_lab_members(
    department: Department,
) -> None:
    lab = Lab.objects.create(name="Forest Lab", slug="forest", department=department)
    direct = add_user("direct")
    lab_member = add_user("lab-member")

    DeptMembership.objects.create(user=direct, department=department)
    LabMembership.objects.create(user=lab_member, lab=lab)

    ids = effective_member_ids(department)
    assert ids == {direct.id, lab_member.id}
    assert set(effective_members(department)) == {direct, lab_member}


@pytest.mark.django_db
def test_effective_membership_deduplicates_users(department: Department) -> None:
    lab1 = Lab.objects.create(name="Lab One", slug="lab-one", department=department)
    lab2 = Lab.objects.create(name="Lab Two", slug="lab-two", department=department)
    person = add_user("person")

    # Same user in two labs of the department, and also a direct member.
    LabMembership.objects.create(user=person, lab=lab1)
    LabMembership.objects.create(user=person, lab=lab2)
    DeptMembership.objects.create(user=person, department=department)

    assert effective_member_ids(department) == {person.id}
    assert effective_member_count(department) == 1


@pytest.mark.django_db
def test_lab_members_outside_department_are_excluded(department: Department) -> None:
    inside = Lab.objects.create(name="Inside", slug="inside", department=department)
    outside = Lab.objects.create(name="Outside", slug="outside")
    LabMembership.objects.create(user=add_user("a"), lab=inside)
    stray = add_user("stray")
    LabMembership.objects.create(user=stray, lab=outside)

    assert stray.id not in effective_member_ids(department)


@pytest.mark.django_db
def test_lab_lead_count(department: Department) -> None:
    lab = Lab.objects.create(name="Forest Lab", slug="forest", department=department)
    LabMembership.objects.create(user=add_user("pi1"), lab=lab, is_lead=True)
    LabMembership.objects.create(user=add_user("pi2"), lab=lab, is_lead=True)
    LabMembership.objects.create(user=add_user("ra"), lab=lab, is_lead=False)

    assert lab_lead_count(lab) == 2
