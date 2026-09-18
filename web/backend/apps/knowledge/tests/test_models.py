"""The schema's promises, checked against the database rather than the code.

Plan CN-01's first acceptance criterion — deleting a subject leaves no edge that
referenced it — and the structural rules the rest of the series leans on:
exactly one subject per edge, scopes that name exactly one owner, and
conversation that can only ever be about a person, and only ever pending until
that person says yes.
"""

import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction

from apps.accounts.models import AuthorWork, Department, Lab
from apps.knowledge.models import (
    Concept,
    ConceptAlias,
    Edge,
    EdgeStatus,
    Facet,
    Relation,
    Scope,
    Tier,
)
from apps.research.models import Project


@pytest.fixture
def ada(db):
    return User.objects.create_user("ada", "ada@example.org", "pw")


@pytest.fixture
def lab(db):
    return Lab.objects.create(name="PULSE", slug="pulse-knowledge")


@pytest.fixture
def concept(db):
    return Concept.objects.create(label="conformal prediction", facet=Facet.METHOD)


def _edge(concept, **subject):
    return Edge.objects.create(
        concept=concept,
        relation=Relation.USES_METHOD,
        tier=Tier.DECLARED,
        **subject,
    )


def _refused(**kwargs):
    with pytest.raises(IntegrityError), transaction.atomic():
        Edge.objects.create(**kwargs)


def test_an_edge_needs_exactly_one_subject(concept, ada, lab):
    base = {"concept": concept, "relation": Relation.USES_METHOD, "tier": Tier.DECLARED}
    _refused(**base)
    _refused(**base, user=ada, lab=lab)
    assert _edge(concept, user=ada).subject_label == f"user:{ada.pk}"


def test_one_edge_per_subject_relation_concept_and_tier(concept, ada):
    _edge(concept, user=ada)
    _refused(
        concept=concept, relation=Relation.USES_METHOD, tier=Tier.DECLARED, user=ada
    )
    # The same concept reached another way is a different edge, not a clash.
    Edge.objects.create(
        concept=concept,
        relation=Relation.USES_METHOD,
        tier=Tier.CONVERSATIONAL,
        status=EdgeStatus.PENDING,
        user=ada,
    )


def test_conversation_is_only_ever_about_a_person(concept, lab, ada):
    _refused(
        concept=concept,
        relation=Relation.INTERESTED_IN,
        tier=Tier.CONVERSATIONAL,
        status=EdgeStatus.PENDING,
        lab=lab,
    )
    project = Project.objects.create(name="Imaging", scope_lab=lab)
    _refused(
        concept=concept,
        relation=Relation.USES_METHOD,
        tier=Tier.CONVERSATIONAL,
        status=EdgeStatus.PENDING,
        project=project,
    )


def test_only_conversation_waits_for_confirmation(concept, ada):
    _refused(
        concept=concept,
        relation=Relation.INTERESTED_IN,
        tier=Tier.DECLARED,
        status=EdgeStatus.PENDING,
        user=ada,
    )


def test_a_scope_names_exactly_its_owner(ada, lab):
    def refused(**kwargs):
        with pytest.raises(IntegrityError), transaction.atomic():
            Concept.objects.create(label="x", facet=Facet.AREA, **kwargs)

    refused(scope=Scope.GLOBAL, scope_lab=lab)
    refused(scope=Scope.LAB)
    refused(scope=Scope.LAB, scope_lab=lab, scope_user=ada)
    refused(scope=Scope.PERSONAL, scope_lab=lab)
    Concept.objects.create(label="x", facet=Facet.AREA, scope=Scope.LAB, scope_lab=lab)
    Concept.objects.create(
        label="x", facet=Facet.AREA, scope=Scope.PERSONAL, scope_user=ada
    )


def test_an_alias_is_unique_within_its_scope_and_facet(concept, lab):
    ConceptAlias.objects.create(
        concept=concept, text="cp", facet=Facet.METHOD, scope=Scope.GLOBAL
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        ConceptAlias.objects.create(
            concept=concept, text="cp", facet=Facet.METHOD, scope=Scope.GLOBAL
        )
    # The same words mean something else as an area, or inside one lab.
    area = Concept.objects.create(label="cp", facet=Facet.AREA)
    ConceptAlias.objects.create(
        concept=area, text="cp", facet=Facet.AREA, scope=Scope.GLOBAL
    )
    ConceptAlias.objects.create(
        concept=concept,
        text="cp",
        facet=Facet.METHOD,
        scope=Scope.LAB,
        scope_lab=lab,
    )


def test_deleting_any_subject_deletes_its_edges(concept, ada, lab):
    project = Project.objects.create(name="Imaging", scope_lab=lab)
    work = AuthorWork.objects.create(user=ada, source="openalex", source_id="W1")
    edges = [
        _edge(concept, user=ada),
        _edge(concept, lab=lab),
        _edge(concept, project=project),
        _edge(concept, author_work=work),
    ]
    project.delete()
    work.delete()
    lab.delete()
    ada.delete()
    assert not Edge.objects.filter(pk__in=[edge.pk for edge in edges]).exists()
    # The idea itself outlives the people who held it: it was never theirs.
    assert Concept.objects.filter(pk=concept.pk).exists()


def test_a_scoped_concept_goes_with_its_owner(lab, ada):
    department = Department.objects.create(name="Scientific Computing", owner=ada)
    in_lab = Concept.objects.create(
        label="the falcon dataset", facet=Facet.SETTING, scope=Scope.LAB, scope_lab=lab
    )
    in_department = Concept.objects.create(
        label="x",
        facet=Facet.AREA,
        scope=Scope.DEPARTMENT,
        scope_department=department,
    )
    lab.delete()
    department.delete()
    assert not Concept.objects.filter(pk__in=[in_lab.pk, in_department.pk]).exists()
