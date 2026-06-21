import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.accounts.models import Department, DeptMembership, Lab, LabMembership


@pytest.fixture
def owner(db: None) -> User:
    return User.objects.create_user(username="dept-owner", password="pass-123")


@pytest.fixture
def department(owner: User) -> Department:
    return Department.objects.create(
        owner=owner,
        name="Neuroscience",
        institution="Example University",
    )


def make_lab(department: Department | None = None) -> Lab:
    return Lab.objects.create(
        name="Forest Lab",
        slug="forest-lab",
        department=department,
    )


@pytest.mark.django_db
def test_lab_belongs_to_department(department: Department) -> None:
    lab = make_lab(department)

    assert lab.department == department
    assert list(department.labs.all()) == [lab]


@pytest.mark.django_db
def test_lab_survives_department_deletion(department: Department) -> None:
    lab = make_lab(department)

    department.delete()
    lab.refresh_from_db()

    assert lab.department_id is None


@pytest.mark.django_db
def test_department_owner_is_protected(owner: User, department: Department) -> None:
    with pytest.raises(ProtectedError):
        owner.delete()


@pytest.mark.django_db
def test_dept_membership_is_unique_per_user(department: Department) -> None:
    member = User.objects.create_user(username="member", password="pass-123")
    DeptMembership.objects.create(
        user=member,
        department=department,
        role=DeptMembership.Role.MEMBER,
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        DeptMembership.objects.create(user=member, department=department)


@pytest.mark.django_db
def test_lab_lead_flag_defaults_false(department: Department) -> None:
    lab = make_lab(department)
    pi = User.objects.create_user(username="pi", password="pass-123")

    membership = LabMembership.objects.create(
        user=pi,
        lab=lab,
        role=LabMembership.Role.OWNER,
        is_lead=True,
    )
    plain = LabMembership.objects.create(
        user=User.objects.create_user(username="ra", password="pass-123"),
        lab=lab,
    )

    assert membership.is_lead is True
    assert plain.is_lead is False
