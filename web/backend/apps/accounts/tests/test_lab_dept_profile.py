"""Phase D — lab & department interest surfaces."""

import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction

from apps.accounts.aggregates import (
    dept_profile_sources,
    derive_dept_vector,
    derive_lab_vector,
    lab_profile_sources,
)
from apps.accounts.models import (
    Department,
    DeptMembership,
    DeptProfile,
    Lab,
    LabMembership,
    LabProfile,
    Profile,
)
from apps.research.models import Project


@pytest.fixture
def owner(db) -> User:
    return User.objects.create_user(username="owner", password="pass-123")


@pytest.mark.django_db
def test_lab_profile_auto_created() -> None:
    lab = Lab.objects.create(name="Reed Lab", slug="reed-lab")
    assert LabProfile.objects.filter(lab=lab).exists()
    assert lab.profile.interests == {}


@pytest.mark.django_db
def test_dept_profile_auto_created(owner: User) -> None:
    dept = Department.objects.create(owner=owner, name="Dept of X")
    assert DeptProfile.objects.filter(department=dept).exists()
    assert dept.profile.areas == []


@pytest.mark.django_db
def test_lab_profile_is_one_to_one() -> None:
    lab = Lab.objects.create(name="Reed Lab", slug="reed-lab")
    with pytest.raises(IntegrityError), transaction.atomic():
        LabProfile.objects.create(lab=lab)


@pytest.mark.django_db
def test_lab_profile_removed_with_lab() -> None:
    lab = Lab.objects.create(name="Reed Lab", slug="reed-lab")
    profile_id = lab.profile.id
    lab.delete()
    assert not LabProfile.objects.filter(id=profile_id).exists()


@pytest.mark.django_db
def test_lab_sources_gather_members_and_projects(owner: User) -> None:
    lab = Lab.objects.create(name="Reed Lab", slug="reed-lab")
    member = User.objects.create_user(username="m1", password="pass-123")
    LabMembership.objects.create(user=member, lab=lab)
    project = Project.objects.create(name="P", scope_lab=lab)
    # An unrelated lab + project must not leak in.
    other = Lab.objects.create(name="Other", slug="other-lab")
    Project.objects.create(name="Q", scope_lab=other)

    sources = lab_profile_sources(lab)
    assert Profile.objects.get(user=member).id in sources["profiles"]
    assert sources["projects"] == [project.id]


@pytest.mark.django_db
def test_dept_sources_use_effective_membership(owner: User) -> None:
    dept = Department.objects.create(owner=owner, name="Dept")
    lab = Lab.objects.create(name="Lab", slug="lab-x", department=dept)
    lab_member = User.objects.create_user(username="lm", password="pass-123")
    LabMembership.objects.create(user=lab_member, lab=lab)
    direct = User.objects.create_user(username="dm", password="pass-123")
    DeptMembership.objects.create(user=direct, department=dept)
    dept_project = Project.objects.create(name="DP", scope_department=dept)
    lab_project = Project.objects.create(name="LP", scope_lab=lab)

    sources = dept_profile_sources(dept)
    profile_ids = set(sources["profiles"])
    assert Profile.objects.get(user=lab_member).id in profile_ids
    assert Profile.objects.get(user=direct).id in profile_ids
    assert set(sources["projects"]) == {dept_project.id, lab_project.id}


@pytest.mark.django_db
def test_derived_vectors_none_until_embeddings_exist(owner: User) -> None:
    # Embedding dimension is deferred, so no contributing vectors yet.
    lab = Lab.objects.create(name="Reed Lab", slug="reed-lab")
    dept = Department.objects.create(owner=owner, name="Dept")
    assert derive_lab_vector(lab) is None
    assert derive_dept_vector(dept) is None
