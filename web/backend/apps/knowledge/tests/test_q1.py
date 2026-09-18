"""Q1: which of a project's concepts does none of its people declare?

The first of the four cross-entity queries that prove the graph
(``docs/goals.md``, Next 1): project → concept ← member. A fixture lab whose
project states three things — one a member declares in other words, one
nobody declares, one only a non-member declares — and the query finds the two
the team does not cover.
"""

import pytest
from django.contrib.auth.models import User

from apps.accounts.models import Lab
from apps.knowledge import read, service
from apps.knowledge.models import Relation
from apps.research.models import Project, ProjectState


def _person(username, **interests):
    user = User.objects.create_user(username, f"{username}@example.org", "pw")
    user.profile.interests = interests
    user.profile.save()
    service.project_declared(user)
    return user


@pytest.fixture
def reef(db, embedder):
    embedder.near("semantic segmentation", "Semantic segmentation of imagery")
    lab = Lab.objects.create(name="Reef", slug="reef-q1")
    ada = _person("ada", areas=["Semantic segmentation of imagery"])
    bo = _person("bo", areas=["Oceanography"])
    outsider = _person("cy", areas=["Remote sensing"])
    project = Project.objects.create(
        name="Bleaching",
        scope_lab=lab,
        goals={"interests": {"areas": ["Oceanography"], "keywords": []}},
    )
    project.members.add(ada, bo)
    ProjectState.objects.create(
        project=project,
        slow={
            "method": ["semantic segmentation", "time-series change detection"],
        },
        fast={"needs": {"expertise": ["remote sensing"]}},
    )
    service.project_declared(project)
    return project, ada, outsider


def test_q1_finds_what_no_member_declares(reef):
    project, ada, _ = reef
    missing = read.undeclared_project_concepts(project, ada)
    assert {(view.relation, view.surface) for view in missing} == {
        (Relation.USES_METHOD, "time-series change detection"),
        # Someone declares remote sensing, but not anyone on this project.
        (Relation.NEEDS, "remote sensing"),
    }


def test_q1_is_answered_only_to_someone_who_can_see_the_project(reef):
    project, _, outsider = reef
    assert read.undeclared_project_concepts(project, outsider) == []


def test_q1_counts_the_owner_of_a_personal_project(db, embedder):
    owner = _person("dee", keywords=["kelp canopy mapping"])
    project = Project.objects.create(name="Side quest", scope_user=owner)
    ProjectState.objects.create(
        project=project, slow={"method": ["kelp canopy mapping", "lidar"]}
    )
    service.project_declared(project)
    missing = read.undeclared_project_concepts(project, owner)
    assert [view.surface for view in missing] == ["lidar"]
