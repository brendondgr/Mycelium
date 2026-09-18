"""Declared edges: the profile says it, the graph mirrors it, and nothing flows back.

Plan CN-01's projection acceptance: re-running on an unchanged profile writes
nothing; removing a keyword removes its edge; the profile JSON is byte-identical
before and after; a project's concepts stay in its owner's scope; and a run
that could not link everything never deletes.
"""

import json
from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.utils import timezone

from apps.accounts.models import Lab, LabProfile
from apps.content import embeddings
from apps.knowledge import projection, signals, tasks
from apps.knowledge.models import Concept, Edge, Facet, Relation, Scope, Tier
from apps.research.models import Project, ProjectState


@pytest.fixture
def ada(db):
    user = User.objects.create_user("ada", "ada@example.org", "pw")
    user.profile.interests = {
        "areas": ["Machine learning", "Coral reef ecology"],
        "keywords": ["conformal prediction", "drone imagery"],
        "skills": ["PyTorch"],
    }
    user.profile.save()
    return user


@pytest.fixture
def lab(db):
    return Lab.objects.create(name="PULSE", slug="pulse-projection")


def _edges(**subject):
    return {
        (edge.relation, edge.concept.label, edge.concept.facet)
        for edge in Edge.objects.filter(tier=Tier.DECLARED, **subject).select_related(
            "concept"
        )
    }


def test_a_profile_becomes_declared_edges(ada, embedder):
    result = projection.project_declared(ada)
    assert (result.created, result.deferred) == (5, 0)
    assert _edges(user=ada) == {
        (Relation.INTERESTED_IN, "Machine learning", Facet.AREA),
        (Relation.INTERESTED_IN, "Coral reef ecology", Facet.AREA),
        (Relation.INTERESTED_IN, "conformal prediction", Facet.AREA),
        (Relation.INTERESTED_IN, "drone imagery", Facet.AREA),
        (Relation.CAN_DO, "PyTorch", Facet.METHOD),
    }
    edge = Edge.objects.get(user=ada, surface="PyTorch")
    assert edge.evidence == ["interests.skills"]
    assert edge.status == "active" and edge.half_life_days is None
    # A profile is a shared source: its concepts are shared vocabulary.
    assert not Concept.objects.exclude(scope=Scope.GLOBAL).exists()


def test_projecting_twice_writes_nothing(ada, embedder):
    projection.project_declared(ada)
    concepts = Concept.objects.count()
    stamps = list(Edge.objects.values_list("pk", "updated_at"))
    again = projection.project_declared(ada)
    assert not again.wrote
    assert Concept.objects.count() == concepts
    assert list(Edge.objects.values_list("pk", "updated_at")) == stamps


def test_removing_a_keyword_removes_its_edge_and_never_touches_the_profile(
    ada, embedder
):
    projection.project_declared(ada)
    ada.profile.interests["keywords"] = ["conformal prediction"]
    ada.profile.save()
    before = json.dumps(ada.profile.interests, sort_keys=True)

    result = projection.project_declared(ada)
    assert result.deleted == 1
    assert not Edge.objects.filter(user=ada, surface="drone imagery").exists()
    ada.profile.refresh_from_db()
    assert json.dumps(ada.profile.interests, sort_keys=True) == before


def test_one_concept_named_twice_is_one_edge_with_both_paths(db, embedder):
    user = User.objects.create_user("bo", "bo@example.org", "pw")
    user.profile.interests = {"areas": ["Robotics"], "keywords": ["robotics"]}
    user.profile.save()
    projection.project_declared(user)
    edge = Edge.objects.get(user=user)
    assert edge.evidence == ["interests.areas", "interests.keywords"]


def test_without_the_embedder_a_run_adds_but_never_deletes(ada, embedder):
    projection.project_declared(ada)
    ada.profile.interests["keywords"] = ["conformal prediction", "a brand new idea"]
    ada.profile.save()
    embeddings.set_embedder(None)

    result = projection.project_declared(ada)
    assert result.deferred == 1
    assert result.deleted == 0
    # "drone imagery" is gone from the profile, but this run could not see
    # everything, so its edge waits for a complete run.
    assert Edge.objects.filter(user=ada, surface="drone imagery").exists()

    embeddings.set_embedder(embedder)
    result = projection.project_declared(ada)
    assert (result.created, result.deleted) == (1, 1)


def test_a_lab_mirrors_its_column_and_its_contract(lab, embedder):
    lab_profile = LabProfile.objects.get(lab=lab)
    lab_profile.areas = ["Marine science"]
    lab_profile.interests = {"areas": ["Marine science"], "skills": ["field surveys"]}
    lab_profile.save()
    projection.project_declared(lab)
    assert _edges(lab=lab) == {
        (Relation.INTERESTED_IN, "Marine science", Facet.AREA),
        (Relation.CAN_DO, "field surveys", Facet.METHOD),
    }
    assert Edge.objects.get(lab=lab, surface="Marine science").evidence == [
        "interests.areas",
        "lab.areas",
    ]


def _state(project, **kwargs):
    return ProjectState.objects.create(project=project, **kwargs)


def test_a_projects_stated_state_is_mirrored_in_its_labs_scope(lab, embedder):
    project = Project.objects.create(
        name="Reef",
        scope_lab=lab,
        goals={"interests": {"areas": ["Coral reef ecology"], "keywords": []}},
    )
    _state(
        project,
        slow={
            "problem": "Detect coral bleaching early",
            "method": ["semantic segmentation"],
            "data": ["drone survey imagery"],
        },
        fast={"needs": {"expertise": ["remote sensing"]}},
        provenance={"problem": "stated", "method": "stated", "data": "inferred"},
    )
    projection.project_declared(project)
    assert _edges(project=project) == {
        (Relation.WORKS_ON, "Coral reef ecology", Facet.AREA),
        (Relation.WORKS_ON, "Detect coral bleaching early", Facet.PROBLEM),
        (Relation.USES_METHOD, "semantic segmentation", Facet.METHOD),
        (Relation.NEEDS, "remote sensing", Facet.AREA),
    }
    # The inferred data field is Mylo's proposal, not the project's word.
    assert not Edge.objects.filter(project=project, surface__contains="drone").exists()
    scopes = set(
        Concept.objects.filter(edges__project=project).values_list("scope", "scope_lab")
    )
    assert scopes == {(Scope.LAB, lab.pk)}


def test_a_long_problem_statement_is_prose_not_a_concept(lab, embedder):
    project = Project.objects.create(name="Reef", scope_lab=lab)
    _state(project, slow={"problem": "We want to detect bleaching " * 10})
    result = projection.project_declared(project)
    assert result.skipped == 1
    assert not Edge.objects.filter(project=project).exists()


def test_a_personal_project_stays_personal(ada, embedder):
    project = Project.objects.create(name="Side quest", scope_user=ada)
    _state(project, slow={"method": ["an unpublished trick"]})
    projection.project_declared(project)
    concept = Edge.objects.get(project=project).concept
    assert (concept.scope, concept.scope_user) == (Scope.PERSONAL, ada)


def test_a_project_meets_its_members_on_the_shared_concept(ada, lab, embedder):
    projection.project_declared(ada)
    project = Project.objects.create(name="Reef", scope_lab=lab)
    _state(project, slow={"method": ["Conformal Prediction"]})
    projection.project_declared(project)
    assert (
        Edge.objects.get(project=project).concept
        == Edge.objects.get(user=ada, surface="conformal prediction").concept
    )


def test_a_members_declaration_promotes_the_projects_private_concept(lab, embedder):
    project = Project.objects.create(name="Reef", scope_lab=lab)
    _state(project, slow={"method": ["kelp canopy mapping"]})
    projection.project_declared(project)
    private = Edge.objects.get(project=project).concept
    assert private.scope == Scope.LAB

    bo = User.objects.create_user("bo", "bo@example.org", "pw")
    bo.profile.interests = {"areas": ["Kelp canopy mapping"]}
    bo.profile.save()
    projection.project_declared(bo)
    shared = Edge.objects.get(user=bo).concept
    assert shared.scope == Scope.GLOBAL
    assert Edge.objects.get(project=project).concept == shared


def test_orphaned_private_concepts_are_pruned_and_shared_ones_kept(ada, lab, embedder):
    projection.project_declared(ada)
    project = Project.objects.create(name="Reef", scope_lab=lab)
    _state(project, slow={"method": ["the falcon trick"]})
    projection.project_declared(project)
    private = Edge.objects.get(project=project).concept_id
    project.delete()

    assert projection.prune_orphans() == 0  # still inside the grace period
    later = timezone.now() + projection.ORPHAN_GRACE + timedelta(minutes=1)
    assert projection.prune_orphans(now=later) == 1
    assert not Concept.objects.filter(pk=private).exists()
    assert Concept.objects.filter(scope=Scope.GLOBAL).count() == 5


def test_the_sweep_projects_everyone_and_survives_a_bad_row(
    ada, lab, embedder, monkeypatch
):
    Project.objects.create(name="Reef", scope_lab=lab, goals={"areas": ["Kelp"]})
    real = projection.project_declared

    def flaky(subject):
        if isinstance(subject, Lab):
            raise RuntimeError("boom")
        return real(subject)

    monkeypatch.setattr(projection, "project_declared", flaky)
    result = projection.sweep()
    assert result.failures == [f"lab:{lab.pk}"]
    assert Edge.objects.filter(user=ada).count() == 5
    assert Edge.objects.filter(project__name="Reef").count() == 1


def test_the_command_projects_one_subject_or_sweeps(ada, embedder, capsys):
    call_command("project_declared_edges", "--user", str(ada.pk))
    assert json.loads(capsys.readouterr().out)["created"] == 5
    call_command("project_declared_edges")
    assert json.loads(capsys.readouterr().out)["created"] == 0


# --- the save hook ----------------------------------------------------------


@pytest.fixture
def queued(settings, monkeypatch):
    settings.KNOWLEDGE_PROJECT_ON_SAVE = True
    calls = []
    monkeypatch.setattr(
        tasks.project_subject, "delay", lambda kind, pk: calls.append((kind, pk))
    )
    return calls


def test_saving_a_profile_queues_its_projection(
    ada, queued, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        ada.profile.save()
    with django_capture_on_commit_callbacks(execute=True):
        ada.profile.save(update_fields=["institution"])
    assert queued == [("user", str(ada.pk))]


def test_saving_a_project_or_its_state_queues_the_project(
    lab, queued, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        project = Project.objects.create(name="Reef", scope_lab=lab)
        _state(project, slow={"method": ["x"]})
    assert queued == [("project", str(project.pk))] * 2


def test_the_hook_is_silent_when_switched_off(ada, settings, monkeypatch):
    settings.KNOWLEDGE_PROJECT_ON_SAVE = False
    monkeypatch.setattr(
        signals, "_queue", lambda *a: pytest.fail("queued with the hook off")
    )
    ada.profile.save()


def test_a_broker_outage_never_fails_a_save(
    ada, settings, monkeypatch, django_capture_on_commit_callbacks
):
    settings.KNOWLEDGE_PROJECT_ON_SAVE = True

    def down(*args):
        raise ConnectionError("broker down")

    monkeypatch.setattr(tasks.project_subject, "delay", down)
    with django_capture_on_commit_callbacks(execute=True):
        ada.profile.save()


def test_the_queued_task_projects_by_key(ada, embedder):
    assert tasks.project_subject("user", str(ada.pk))["created"] == 5
    assert tasks.project_subject("project", "00000000-0000-0000-0000-000000000000") == (
        projection.Projected().as_dict()
    )
