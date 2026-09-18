"""The linker: one idea, however it is worded, and private words stay private.

Covers plan CN-01's linker acceptance — with the embedder down, the linker
mints nothing an alias did not produce — and the scope rule the whole series
leans on: a concept minted from a private source is never global, and reaches
the shared vocabulary only by promotion under a shared source's wording.
"""

import pytest
from django.contrib.auth.models import User

from apps.accounts.models import Department, Lab
from apps.knowledge import linker, merging
from apps.knowledge.linker import LinkRequest, link, link_many, normalise
from apps.knowledge.models import (
    Concept,
    ConceptAlias,
    ConceptMerge,
    Edge,
    Facet,
    Relation,
    Scope,
    Tier,
)
from apps.research.models import Project


@pytest.fixture
def lab(db):
    return Lab.objects.create(name="PULSE", slug="pulse-linker")


@pytest.fixture
def other_lab(db):
    return Lab.objects.create(name="Reef", slug="reef-linker")


@pytest.fixture
def ada(db):
    return User.objects.create_user("ada", "ada@example.org", "pw")


def _lab(lab, surface, **kwargs):
    return link(surface, scope=Scope.LAB, owner=lab, **kwargs)


@pytest.mark.parametrize(
    ("raw", "key"),
    [
        ("Graph-Neural Networks", "graph neural networks"),
        ("  graph_neural   networks. ", "graph neural networks"),
        ("input/output", "input output"),
        ("C++", "c++"),
        ("(Bayesian) optimisation", "bayesian optimisation"),
    ],
)
def test_normalise(raw, key):
    assert normalise(raw) == key


def test_the_same_words_twice_are_one_concept(db, embedder):
    first = link("Conformal prediction")
    second = link("conformal-prediction")
    assert first.how == "minted"
    assert second.how == "alias"
    assert second.concept == first.concept
    # The alias answered it; nothing was embedded the second time.
    assert embedder.calls == [["Conformal prediction"]]


def test_near_wording_links_by_embedding_and_becomes_an_alias(db, embedder):
    embedder.near("conformal prediction", "conformal methods")
    first = link("conformal prediction")
    second = link("conformal methods")
    assert second.how == "embedding"
    assert second.concept == first.concept
    assert ConceptAlias.objects.filter(
        text="conformal methods", concept=first.concept
    ).exists()


def test_far_wording_mints_its_own_concept(db, embedder):
    first = link("conformal prediction")
    second = link("coral reef ecology")
    assert second.how == "minted"
    assert second.concept != first.concept


def test_a_known_facet_is_strict_and_an_unknown_one_accepts_any(db, embedder):
    method = link("graph neural networks", facet=Facet.METHOD)
    as_area = link("graph neural networks", facet=Facet.AREA)
    assert as_area.concept != method.concept
    assert as_area.concept.facet == Facet.AREA
    # A declared keyword has no facet of its own: it takes whatever it names.
    keyword = link("graph neural networks")
    assert keyword.concept in (method.concept, as_area.concept)


def test_an_unknown_facet_mints_as_the_default(db, embedder):
    assert link("PyTorch", default_facet=Facet.METHOD).concept.facet == Facet.METHOD


def test_prose_and_blanks_are_not_terms(db, embedder, settings):
    settings.KNOWLEDGE_MAX_SURFACE_CHARS = 40
    results = link_many(
        [
            LinkRequest(surface=""),
            LinkRequest(surface="   "),
            LinkRequest(surface="We detect coral bleaching from drone imagery early."),
        ]
    )
    assert [result.how for result in results] == ["skipped"] * 3
    assert not Concept.objects.exists()


def test_without_the_embedder_only_aliases_link(db, embedder):
    known = link("conformal prediction").concept
    from apps.content import embeddings

    embeddings.set_embedder(None)
    results = link_many(
        [LinkRequest(surface="Conformal Prediction"), LinkRequest(surface="new idea")]
    )
    assert results[0].how == "alias" and results[0].concept == known
    assert results[1].how == "deferred" and results[1].concept is None
    assert Concept.objects.count() == 1


def test_a_batch_embeds_once(db, embedder):
    link_many([LinkRequest(surface=s) for s in ("alpha", "beta", "gamma")])
    assert len(embedder.calls) == 1


def test_a_batch_that_names_one_idea_twice_mints_it_once(db, embedder):
    results = link_many([LinkRequest(surface="alpha"), LinkRequest(surface="Alpha")])
    assert results[0].concept == results[1].concept
    assert Concept.objects.count() == 1


# --- scope ------------------------------------------------------------------


@pytest.mark.parametrize("scope", [Scope.PERSONAL, Scope.LAB, Scope.DEPARTMENT])
def test_every_private_mint_stays_private(scope, db, embedder, ada, lab):
    owner = {
        Scope.PERSONAL: ada,
        Scope.LAB: lab,
        Scope.DEPARTMENT: Department.objects.create(name="SC", owner=ada),
    }[scope]
    result = link("the falcon dataset", scope=scope, owner=owner)
    assert result.how == "minted"
    assert result.concept.scope == scope
    assert not Concept.objects.filter(scope=Scope.GLOBAL).exists()
    assert not ConceptAlias.objects.filter(scope=Scope.GLOBAL).exists()


def test_a_private_source_needs_an_owner(db, embedder):
    with pytest.raises(ValueError):
        link("x", scope=Scope.LAB)


def test_a_lab_never_sees_another_labs_concepts(db, embedder, lab, other_lab):
    embedder.near("falcon segmentation", "falcon segmenter")
    mine = _lab(lab, "falcon segmentation")
    theirs_alias = _lab(other_lab, "falcon segmentation")
    theirs_near = _lab(other_lab, "falcon segmenter")
    assert theirs_alias.how == "minted"
    assert theirs_alias.concept != mine.concept
    # The other lab links to its own concept, not to the first lab's.
    assert theirs_near.concept == theirs_alias.concept


def test_a_private_source_links_to_the_shared_vocabulary(db, embedder, lab):
    embedder.near("graph neural networks", "GNNs for graphs")
    shared = link("graph neural networks").concept
    # The same words reach it through the shared alias, and nothing is minted.
    assert _lab(lab, "Graph Neural Networks").concept == shared
    # Other words reach it by embedding, and become the lab's alias, not a
    # shared one: the lab's phrasing stays the lab's.
    near = _lab(lab, "GNNs for graphs")
    assert (near.how, near.concept) == ("embedding", shared)
    alias = ConceptAlias.objects.get(text="gnns for graphs")
    assert (alias.scope, alias.scope_lab) == (Scope.LAB, lab)
    assert Concept.objects.count() == 1


def test_a_lab_alias_outranks_the_shared_one(db, embedder, lab):
    shared = link("segmentation").concept
    private = Concept.objects.create(
        label="segmentation",
        facet=Facet.AREA,
        scope=Scope.LAB,
        scope_lab=lab,
    )
    ConceptAlias.objects.create(
        concept=private,
        text="segmentation",
        facet=Facet.AREA,
        scope=Scope.LAB,
        scope_lab=lab,
    )
    assert _lab(lab, "segmentation").concept == private
    assert link("segmentation").concept == shared


# --- promotion --------------------------------------------------------------


def test_a_shared_source_promotes_the_private_concept_under_its_own_words(
    db, embedder, lab
):
    embedder.near("reef survey imagery", "Reef survey images")
    project = Project.objects.create(name="Reef", scope_lab=lab)
    private = _lab(lab, "reef survey imagery").concept
    Edge.objects.create(
        project=project,
        concept=private,
        relation=Relation.WORKS_IN_SETTING,
        tier=Tier.DECLARED,
        surface="reef survey imagery",
    )

    shared = link("Reef survey images")
    assert shared.how == "promoted"
    assert shared.concept.pk == private.pk
    shared.concept.refresh_from_db()
    assert shared.concept.scope == Scope.GLOBAL
    # The lab's phrasing is gone from the shared concept.
    assert shared.concept.label == "Reef survey images"
    # The project's edge now meets anyone who declares the same thing.
    assert Edge.objects.get(project=project).concept_id == shared.concept.pk
    # The lab still owns its alias for its own wording.
    assert ConceptAlias.objects.get(text="reef survey imagery").scope == Scope.LAB
    log = ConceptMerge.objects.get(kind=ConceptMerge.Kind.PROMOTE)
    assert log.source is None and log.collapsed_edges == []


def test_promotion_folds_every_private_duplicate_in(db, embedder, lab, other_lab):
    one = _lab(lab, "kelp forests").concept
    two = _lab(other_lab, "kelp forests").concept
    project = Project.objects.create(name="Kelp", scope_lab=other_lab)
    Edge.objects.create(
        project=project,
        concept=two,
        relation=Relation.WORKS_ON,
        tier=Tier.DECLARED,
    )
    shared = link("kelp forests")
    assert shared.how == "promoted"
    assert {one.pk, two.pk} & {shared.concept.pk}
    survivors = Concept.objects.filter(pk__in=[one.pk, two.pk])
    assert survivors.count() == 1 and survivors.get().scope == Scope.GLOBAL
    assert Edge.objects.get(project=project).concept == shared.concept


def test_a_private_source_never_promotes_anything(db, embedder, lab, other_lab):
    _lab(lab, "kelp forests")
    _lab(other_lab, "kelp forests")
    assert not Concept.objects.filter(scope=Scope.GLOBAL).exists()


# --- merge and unmerge ------------------------------------------------------


def test_a_staff_merge_reverses_exactly(db, embedder, ada, lab):
    target = link("uncertainty quantification").concept
    source = link("UQ methods").concept
    bob = User.objects.create_user("bob", "bob@example.org", "pw")
    moved = Edge.objects.create(
        user=ada,
        concept=source,
        relation=Relation.INTERESTED_IN,
        tier=Tier.DECLARED,
        surface="UQ methods",
        evidence=["interests.keywords"],
    )
    Edge.objects.create(
        user=bob,
        concept=target,
        relation=Relation.INTERESTED_IN,
        tier=Tier.DECLARED,
        evidence=["interests.areas"],
    )
    Edge.objects.create(
        user=bob,
        concept=source,
        relation=Relation.INTERESTED_IN,
        tier=Tier.DECLARED,
        evidence=["interests.keywords"],
    )

    record = merging.merge(source, target, actor=ada)
    source.refresh_from_db()
    assert source.status == Concept.Status.MERGED
    assert Edge.objects.get(pk=moved.pk).concept == target
    bobs = Edge.objects.get(user=bob)
    assert bobs.concept == target
    assert sorted(bobs.evidence) == ["interests.areas", "interests.keywords"]
    # Linking the merged wording now reaches the survivor.
    assert link("UQ methods").concept == target

    merging.unmerge(record, actor=ada)
    source.refresh_from_db()
    assert source.status == Concept.Status.ACTIVE
    assert Edge.objects.get(pk=moved.pk).concept == source
    assert Edge.objects.filter(user=bob, concept=source).exists()
    assert link("UQ methods").concept == source
    with pytest.raises(merging.MergeRefused):
        merging.unmerge(record)


def test_merges_that_would_cross_owners_are_refused(db, embedder, lab, other_lab):
    shared = link("segmentation").concept
    mine = _lab(lab, "falcon segmentation").concept
    theirs = _lab(other_lab, "reef segmentation").concept
    method = link("segmentation", facet=Facet.METHOD).concept
    for source, target in [
        (mine, theirs),  # two owners
        (shared, mine),  # shared into private
        (shared, method),  # two facets
        (shared, shared),
    ]:
        with pytest.raises(merging.MergeRefused):
            merging.merge(source, target)
    # Private into shared is how promotion works, and staff may do it too.
    merging.merge(mine, shared)


def test_the_module_states_how_links_go():
    assert set(linker.HOW) == {
        "alias",
        "embedding",
        "promoted",
        "minted",
        "deferred",
        "skipped",
    }


def test_a_specific_facet_may_name_an_unspecified_concept(db, embedder):
    keyword = link("conformal prediction").concept
    assert keyword.facet == Facet.AREA
    method = link("Conformal Prediction", facet=Facet.METHOD)
    assert (method.how, method.concept) == ("alias", keyword)
    # One source's view does not reclassify a concept everyone shares.
    keyword.refresh_from_db()
    assert keyword.facet == Facet.AREA


def test_two_specific_facets_never_meet(db, embedder):
    method = link("segmentation", facet=Facet.METHOD).concept
    problem = link("segmentation", facet=Facet.PROBLEM).concept
    assert problem != method and problem.facet == Facet.PROBLEM
    # Asked for a method, the method wins over the unspecified area concept.
    link("segmentation", facet=Facet.AREA)
    assert link("segmentation", facet=Facet.METHOD).concept == method
