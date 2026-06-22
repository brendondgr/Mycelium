import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.accounts.models import (
    Department,
    DeptMembership,
    Lab,
    LabMembership,
)
from apps.research.models import Project, ProjectMember


@pytest.fixture
def user(db: None) -> User:
    return User.objects.create_user(username="researcher", password="pass-123")


@pytest.fixture
def lab(db: None) -> Lab:
    return Lab.objects.create(name="Forest Lab", slug="forest-lab")


@pytest.fixture
def department(user: User) -> Department:
    return Department.objects.create(owner=user, name="Neuroscience")


@pytest.mark.django_db
def test_user_scoped_project(user: User) -> None:
    project = Project.objects.create(scope_user=user, name="Personal review")

    assert project.scope == "user"
    assert project.scope_target == user
    assert list(user.personal_projects.all()) == [project]


@pytest.mark.django_db
def test_lab_scoped_project(lab: Lab) -> None:
    project = Project.objects.create(scope_lab=lab, name="Lab roadmap")

    assert project.scope == "lab"
    assert project.scope_target == lab
    assert list(lab.projects.all()) == [project]


@pytest.mark.django_db
def test_department_scoped_project(department: Department) -> None:
    project = Project.objects.create(scope_department=department, name="Dept review")

    assert project.scope == "department"
    assert project.scope_target == department


@pytest.mark.django_db
def test_project_rejects_multiple_scopes(user: User, lab: Lab) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        Project.objects.create(scope_user=user, scope_lab=lab, name="Bad")


@pytest.mark.django_db
def test_project_rejects_no_scope() -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        Project.objects.create(name="Orphan")


@pytest.mark.django_db
def test_project_clean_requires_exactly_one_scope(user: User, lab: Lab) -> None:
    with pytest.raises(ValidationError):
        Project(name="None").clean()
    with pytest.raises(ValidationError):
        Project(scope_user=user, scope_lab=lab, name="Two").clean()
    # Exactly one set is valid.
    Project(scope_user=user, name="Ok").clean()


@pytest.mark.django_db
def test_project_member_is_unique(user: User, lab: Lab) -> None:
    project = Project.objects.create(scope_lab=lab, name="Lab roadmap")
    ProjectMember.objects.create(project=project, user=user)

    with pytest.raises(IntegrityError), transaction.atomic():
        ProjectMember.objects.create(project=project, user=user)

    assert list(project.members.all()) == [user]


# --- Visibility cascade (Project.objects.visible_to) -----------------------


def make_user(name: str) -> User:
    return User.objects.create_user(username=name, password="pass-123")


def make_lab(department: Department | None = None) -> Lab:
    return Lab.objects.create(
        name="Forest Lab", slug="forest-lab", department=department
    )


@pytest.mark.django_db
def test_member_sees_project(lab: Lab) -> None:
    member = make_user("member")
    project = Project.objects.create(scope_lab=lab, name="Roadmap")
    ProjectMember.objects.create(project=project, user=member)

    assert project.is_visible_to(member)
    assert list(Project.objects.visible_to(member)) == [project]


@pytest.mark.django_db
def test_personal_owner_sees_own_project() -> None:
    owner = make_user("owner")
    project = Project.objects.create(scope_user=owner, name="Personal")

    assert project.is_visible_to(owner)


@pytest.mark.django_db
def test_lab_head_sees_lab_project_but_plain_member_does_not(lab: Lab) -> None:
    head = make_user("pi")
    grunt = make_user("grunt")
    LabMembership.objects.create(user=head, lab=lab, is_lead=True)
    LabMembership.objects.create(
        user=grunt, lab=lab, role=LabMembership.Role.MEMBER
    )
    project = Project.objects.create(scope_lab=lab, name="Lab roadmap")

    assert project.is_visible_to(head)
    # A rank-and-file lab member is NOT a head and is not a project member.
    assert not project.is_visible_to(grunt)


@pytest.mark.django_db
def test_department_owner_sees_lab_project(department: Department) -> None:
    # department.owner is the `user` fixture.
    lab = make_lab(department)
    project = Project.objects.create(scope_lab=lab, name="Lab roadmap")

    assert project.is_visible_to(department.owner)


@pytest.mark.django_db
def test_department_admin_sees_lab_project(department: Department) -> None:
    admin = make_user("dept-admin")
    DeptMembership.objects.create(
        user=admin, department=department, role=DeptMembership.Role.ADMIN
    )
    lab = make_lab(department)
    project = Project.objects.create(scope_lab=lab, name="Lab roadmap")

    assert project.is_visible_to(admin)


@pytest.mark.django_db
def test_department_head_sees_department_project(department: Department) -> None:
    project = Project.objects.create(scope_department=department, name="Dept review")

    assert project.is_visible_to(department.owner)


@pytest.mark.django_db
def test_unrelated_user_sees_nothing(department: Department) -> None:
    outsider = make_user("outsider")
    lab = make_lab(department)
    Project.objects.create(scope_lab=lab, name="Lab roadmap")
    Project.objects.create(scope_department=department, name="Dept review")

    assert list(Project.objects.visible_to(outsider)) == []


@pytest.mark.django_db
def test_other_department_head_does_not_see_unrelated_lab(
    department: Department,
) -> None:
    other_head = make_user("other-head")
    other_dept = Department.objects.create(owner=other_head, name="Chemistry")
    lab = make_lab(department)
    project = Project.objects.create(scope_lab=lab, name="Lab roadmap")

    # other_head heads a different department, so the lab project is invisible.
    assert not project.is_visible_to(other_head)
    assert other_dept.owner == other_head
