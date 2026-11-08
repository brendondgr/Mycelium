"""What each door returns, and what it can never return.

The load-bearing acceptance criterion of plan CN-01: ``discoverable_edges``
returns no conversational edge and no project edge under any input. Tested
exhaustively over every tier and status rather than by example, because the
rule is only worth anything if no combination slips through.
"""

import itertools

import pytest
from django.contrib.auth.models import User
from tools.retrieval import embeddings

from apps.accounts.models import Lab, LabMembership
from apps.knowledge import read, service
from apps.knowledge.linker import link
from apps.knowledge.models import (
    Concept,
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
def bo(db):
    return User.objects.create_user("bo", "bo@example.org", "pw")


@pytest.fixture
def lab(db):
    return Lab.objects.create(name="PULSE", slug="pulse-doors")


def _combinations(user):
    """Every legal (tier, status) edge for ``user``, each on its own concept."""
    rows = []
    for tier, status in itertools.product(Tier.values, EdgeStatus.values):
        if status == EdgeStatus.PENDING and tier != Tier.CONVERSATIONAL:
            continue
        concept = Concept.objects.create(label=f"{tier}-{status}", facet=Facet.AREA)
        rows.append(
            Edge.objects.create(
                user=user,
                concept=concept,
                relation=Relation.INTERESTED_IN,
                tier=tier,
                status=status,
            )
        )
    return rows


def _pairs(views):
    return {(view.tier, view.status) for view in views}


def test_discoverable_edges_never_hold_conversation_or_a_project(ada, bo, lab):
    _combinations(ada)
    _combinations(bo)
    project = Project.objects.create(name="Reef", scope_lab=lab)
    Edge.objects.create(
        project=project,
        concept=Concept.objects.create(label="secret", facet=Facet.METHOD),
        relation=Relation.USES_METHOD,
        tier=Tier.DECLARED,
    )
    for users in ([ada], [bo], [ada, bo], User.objects.all(), []):
        views = read.discoverable_edges(users)
        assert all(view.tier != Tier.CONVERSATIONAL for view in views)
        assert all(view.project_id is None for view in views)
        assert all(view.status == EdgeStatus.ACTIVE for view in views)
    assert _pairs(read.discoverable_edges([ada])) == {
        (Tier.DECLARED, EdgeStatus.ACTIVE),
        (Tier.DEMONSTRATED, EdgeStatus.ACTIVE),
    }


def test_own_edges_show_the_person_everything(ada, bo):
    rows = _combinations(ada)
    _combinations(bo)
    views = read.own_edges(ada)
    assert len(views) == len(rows)
    assert {view.user_id for view in views} == {ada.pk}


def test_ranking_edges_are_declared_and_confirmed_conversation_only(ada):
    _combinations(ada)
    assert _pairs(read.ranking_edges(ada)) == {
        (Tier.DECLARED, EdgeStatus.ACTIVE),
        (Tier.CONVERSATIONAL, EdgeStatus.ACTIVE),
    }


def test_a_lab_reads_only_what_its_members_declared(ada, bo):
    _combinations(ada)
    assert _pairs(read.lab_declared_edges([ada, bo])) == {
        (Tier.DECLARED, EdgeStatus.ACTIVE)
    }


def test_project_edges_need_a_viewer_who_can_see_the_project(ada, bo, lab):
    project = Project.objects.create(name="Reef", scope_lab=lab)
    Edge.objects.create(
        project=project,
        concept=Concept.objects.create(label="kelp", facet=Facet.AREA),
        relation=Relation.WORKS_ON,
        tier=Tier.DECLARED,
    )
    project.members.add(ada)
    assert [view.label for view in read.project_edges(project, ada)] == ["kelp"]
    # A member of the lab who is not on the project and does not head the lab
    # cannot see it, so cannot read its edges either.
    LabMembership.objects.create(user=bo, lab=lab)
    assert read.project_edges(project, bo) == []
    assert read.project_edges(project.pk, ada)


def test_views_are_not_models(ada):
    _combinations(ada)
    view = read.own_edges(ada)[0]
    assert isinstance(view, read.EdgeView)
    with pytest.raises(AttributeError):
        view.save()


# --- the write door ---------------------------------------------------------


def test_conversation_is_recorded_pending_and_private(ada, embedder):
    view = service.record_conversational(
        ada,
        surface="causal inference",
        relation=Relation.WANTS_TO_LEARN,
        evidence=[101],
        half_life_days=21,
    )
    assert (view.tier, view.status) == (Tier.CONVERSATIONAL, EdgeStatus.PENDING)
    concept = Concept.objects.get(pk=view.concept_id)
    assert (concept.scope, concept.scope_user) == (Scope.PERSONAL, ada)
    assert read.ranking_edges(ada) == []
    assert read.discoverable_edges([ada]) == []


def test_conversation_links_to_the_shared_vocabulary_when_it_exists(ada, embedder):
    shared = link("causal inference").concept
    view = service.record_conversational(
        ada, surface="Causal Inference", relation=Relation.INTERESTED_IN
    )
    assert view.concept_id == shared.pk


def test_reinforcing_grows_evidence_and_keeps_a_no(ada, embedder):
    first = service.record_conversational(
        ada, surface="causal inference", relation=Relation.INTERESTED_IN, evidence=[1]
    )
    assert service.reject(ada, first.concept_id, Relation.INTERESTED_IN)
    again = service.record_conversational(
        ada,
        surface="causal inference",
        relation=Relation.INTERESTED_IN,
        evidence=[1, 2],
    )
    assert again.evidence == (1, 2)
    assert again.status == EdgeStatus.REJECTED
    assert again.last_reinforced >= first.last_reinforced


def test_a_yes_reaches_ranking_and_nothing_else(ada, embedder):
    view = service.record_conversational(
        ada, surface="causal inference", relation=Relation.INTERESTED_IN
    )
    assert service.confirm(ada, view.concept_id, Relation.INTERESTED_IN)
    assert [v.concept_id for v in read.ranking_edges(ada)] == [view.concept_id]
    assert read.discoverable_edges([ada]) == []
    assert read.lab_declared_edges([ada]) == []
    assert service.fade(ada, view.concept_id, Relation.INTERESTED_IN)
    assert read.ranking_edges(ada) == []


def test_an_unlinkable_wording_is_not_recorded_yet(ada, embedder):
    embeddings.set_embedder(None)
    assert (
        service.record_conversational(
            ada, surface="something new", relation=Relation.INTERESTED_IN
        )
        is None
    )
    assert not Edge.objects.exists()


def test_an_unknown_relation_is_refused(ada, embedder):
    with pytest.raises(ValueError):
        service.record_conversational(ada, surface="x", relation="adores")


def test_forgetting_conversation_keeps_the_profile(ada, embedder):
    ada.profile.interests = {"areas": ["Kelp"]}
    ada.profile.save()
    service.project_declared(ada)
    service.record_conversational(
        ada, surface="causal inference", relation=Relation.INTERESTED_IN
    )
    assert service.forget_conversational(ada) == 1
    assert _pairs(read.own_edges(ada)) == {(Tier.DECLARED, EdgeStatus.ACTIVE)}
