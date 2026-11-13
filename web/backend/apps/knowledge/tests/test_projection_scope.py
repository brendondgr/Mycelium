"""A project's concepts take the project's scope (scoping plan, Phase 4).

An ``invite_only`` lab project's words used to be minted in the lab's scope, so
they fed the lab's vocabulary whether or not the lab could see the project.
Now the scope decides: personal (the owner's) for ``invite_only``, the lab for
``lab``, the department for ``department``, the shared vocabulary for
``public`` — and a change of scope re-projects.
"""

import pytest
from django.contrib.auth.models import User

from apps.accounts.models import Department, Lab, LabMembership
from apps.knowledge import projection, signals
from apps.knowledge.models import Concept, Scope
from apps.research.models import Project, ProjectMember, ProjectState


@pytest.fixture
def org(db):
    head = User.objects.create_user("head", "head@example.org", "pw")
    owner = User.objects.create_user("own", "own@example.org", "pw")
    pi = User.objects.create_user("pi", "pi@example.org", "pw")
    dept = Department.objects.create(owner=head, name="Biology")
    lab = Lab.objects.create(name="Reef", slug="reef-scope", department=dept)
    LabMembership.objects.create(
        user=pi, lab=lab, role=LabMembership.Role.OWNER, is_lead=True
    )
    return {"owner": owner, "pi": pi, "lab": lab, "dept": dept}


def _project(org, visibility, *, owner=True):
    project = Project.objects.create(
        name=f"P {visibility}", scope_lab=org["lab"], visibility=visibility
    )
    if owner:
        ProjectMember.objects.create(
            project=project, user=org["owner"], role=ProjectMember.Role.OWNER
        )
    ProjectState.objects.create(
        project=project, slow={"method": [f"secret method {visibility}"]}
    )
    return project


def _scopes(project):
    return set(
        Concept.objects.filter(edges__project=project).values_list(
            "scope", "scope_user", "scope_lab", "scope_department"
        )
    )


@pytest.mark.parametrize(
    ("visibility", "expected"),
    [
        ("invite_only", lambda o: (Scope.PERSONAL, o["owner"].pk, None, None)),
        ("lab", lambda o: (Scope.LAB, None, o["lab"].pk, None)),
        ("department", lambda o: (Scope.DEPARTMENT, None, None, o["dept"].pk)),
        ("public", lambda o: (Scope.GLOBAL, None, None, None)),
    ],
)
def test_a_projects_concepts_take_its_scope(org, embedder, visibility, expected):
    project = _project(org, visibility)
    projection.project_declared(project)
    assert _scopes(project) == {expected(org)}


def test_an_invite_only_project_without_an_owner_row_falls_to_the_pi(org, embedder):
    project = _project(org, "invite_only", owner=False)
    projection.project_declared(project)
    assert _scopes(project) == {(Scope.PERSONAL, org["pi"].pk, None, None)}


def test_nothing_of_an_invite_only_project_reaches_the_labs_vocabulary(org, embedder):
    project = _project(org, "invite_only")
    projection.project_declared(project)
    assert not Concept.objects.filter(
        scope=Scope.LAB, scope_lab=org["lab"], label__icontains="secret"
    ).exists()


def test_a_change_of_scope_re_projects(org, embedder):
    project = _project(org, "lab")
    projection.project_declared(project)
    assert {s[0] for s in _scopes(project)} == {Scope.LAB}

    project.visibility = "invite_only"
    project.save(update_fields=["visibility"])
    projection.project_declared(project)
    assert _scopes(project) == {(Scope.PERSONAL, org["owner"].pk, None, None)}


def test_saving_a_new_scope_queues_the_projection(
    org, settings, monkeypatch, django_capture_on_commit_callbacks
):
    from apps.knowledge import tasks

    settings.KNOWLEDGE_PROJECT_ON_SAVE = True
    calls = []
    monkeypatch.setattr(
        tasks.project_subject, "delay", lambda kind, pk: calls.append((kind, pk))
    )
    project = Project.objects.create(name="Reef", scope_lab=org["lab"])
    with django_capture_on_commit_callbacks(execute=True):
        project.visibility = "lab"
        project.save(update_fields=["visibility"])
    assert calls == [("project", str(project.pk))]
    assert signals  # the receivers are connected by importing the module
