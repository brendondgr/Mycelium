import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.accounts.models import Department, Lab
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
