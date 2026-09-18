"""Demonstrated edges: a person's papers, as edges, per work and rolled up.

Plan CN-02's edge acceptance: a thin work produces no demonstrated edge; no
person has a single averaged expertise vector; the neutral phrasing reaches the
method's concept without merging other methods into it; and demonstrated edges
reach the person's own view and collaboration search, never their ranking.
"""

import pytest
from django.contrib.auth.models import User

from apps.accounts.models import AuthorWork
from apps.knowledge import demonstrated, read, service
from apps.knowledge.models import (
    Concept,
    ConceptAlias,
    Edge,
    Facet,
    Relation,
    Scope,
    Tier,
    WorkFacets,
)


@pytest.fixture
def ada(db):
    return User.objects.create_user("ada", "ada@example.org", "pw")


def _work(user, source_id, *, year=2022, field="23", thin=False, **terms):
    work = AuthorWork.objects.create(
        user=user, source="openalex", source_id=source_id, title=source_id, year=year
    )
    WorkFacets.objects.create(
        author_work=work,
        thin=thin,
        openalex_field_id=field,
        terms={
            "problem": terms.get("problem", []),
            "method": terms.get("method", []),
            "setting": terms.get("setting", []),
            "reusable": terms.get("reusable", []),
        },
        method_neutral=terms.get("neutral", ""),
    )
    return AuthorWork.objects.select_related("facets").get(pk=work.pk)


def _work_edges(work):
    return {
        (edge.relation, edge.concept.label, edge.concept.facet)
        for edge in Edge.objects.filter(author_work=work).select_related("concept")
    }


def test_a_works_terms_become_demonstrated_edges_on_the_work(ada, embedder):
    work = _work(
        ada,
        "W1",
        problem=["coral bleaching detection"],
        method=["semantic segmentation", "Kalman filter"],
        setting=["drone survey mosaics"],
        reusable=["labelled reef mosaics"],
    )
    result = demonstrated.record_work(work)
    assert result.created == 5
    assert _work_edges(work) == {
        (Relation.WORKS_ON, "coral bleaching detection", Facet.PROBLEM),
        (Relation.USES_METHOD, "semantic segmentation", Facet.METHOD),
        (Relation.USES_METHOD, "Kalman filter", Facet.METHOD),
        (Relation.WORKS_IN_SETTING, "drone survey mosaics", Facet.SETTING),
        (Relation.OFFERS, "labelled reef mosaics", Facet.AREA),
    }
    assert set(Edge.objects.values_list("tier", flat=True)) == {Tier.DEMONSTRATED}
    # A published work is public: its concepts are shared vocabulary.
    assert not Concept.objects.exclude(scope=Scope.GLOBAL).exists()
    assert not demonstrated.record_work(work).wrote


def test_a_thin_work_has_no_edges_and_becoming_thin_removes_them(ada, embedder):
    work = _work(ada, "W1", method=["kriging"])
    demonstrated.record_work(work)
    assert Edge.objects.filter(author_work=work).exists()
    work.facets.thin = True
    work.facets.save()
    demonstrated.record_work(work)
    assert not Edge.objects.filter(author_work=work).exists()
    assert not demonstrated.record_work(_work(ada, "W2", thin=True, method=["x"])).wrote


def test_the_neutral_phrasing_names_the_operation_and_is_not_an_alias(ada, embedder):
    first = _work(
        ada, "W1", method=["Kalman filter"], neutral="tracking a hidden state"
    )
    second = _work(
        ada,
        "W2",
        method=["data assimilation"],
        neutral="tracking a hidden state",
    )
    demonstrated.record_work(first)
    demonstrated.record_work(second)
    kalman = Concept.objects.get(label="Kalman filter")
    assimilation = Concept.objects.get(label="data assimilation")
    assert (
        kalman.neutral_label == assimilation.neutral_label == "tracking a hidden state"
    )
    # Two methods sharing an abstraction stay two concepts.
    assert kalman != assimilation
    assert not ConceptAlias.objects.filter(text="tracking a hidden state").exists()


def test_a_neutral_phrase_is_never_overwritten(ada, embedder):
    demonstrated.record_work(
        _work(ada, "W1", method=["kriging"], neutral="first words")
    )
    demonstrated.record_work(
        _work(ada, "W2", method=["kriging"], neutral="later words")
    )
    assert Concept.objects.get(label="kriging").neutral_label == "first words"


def test_the_rollup_counts_works_and_dates_them(ada, embedder):
    for source_id, year in (("W1", 2019), ("W2", 2023), ("W3", 2021)):
        demonstrated.record_work(_work(ada, source_id, year=year, method=["kriging"]))
    demonstrated.rollup(ada)
    edge = Edge.objects.get(user=ada, tier=Tier.DEMONSTRATED)
    assert edge.weight == 3.0
    assert (edge.first_seen.year, edge.last_reinforced.year) == (2019, 2023)
    assert len(edge.evidence) == 3
    assert not demonstrated.rollup(ada).wrote

    AuthorWork.objects.filter(source_id__in=["W1", "W2", "W3"]).delete()
    assert demonstrated.rollup(ada).deleted == 1
    assert not Edge.objects.filter(user=ada).exists()


def test_the_field_ruler_is_set_only_where_works_agree(ada, embedder):
    bo = User.objects.create_user("bo", "bo@example.org", "pw")
    demonstrated.record_work(_work(ada, "W1", field="23", method=["kriging"]))
    demonstrated.record_work(_work(bo, "W2", field="23", method=["kriging"]))
    demonstrated.record_work(_work(ada, "W3", field="23", method=["U-Net"]))
    demonstrated.record_work(_work(bo, "W4", field="27", method=["U-Net"]))
    demonstrated.set_fields(Concept.objects.values_list("pk", flat=True))
    assert Concept.objects.get(label="kriging").openalex_field_id == "23"
    assert Concept.objects.get(label="U-Net").openalex_field_id == ""


def test_record_person_does_every_work_then_the_rollup(ada, embedder):
    _work(ada, "W1", method=["kriging"], field="23")
    _work(ada, "W2", method=["kriging", "U-Net"], field="23")
    demonstrated.record_person(ada)
    assert Edge.objects.filter(user=ada, tier=Tier.DEMONSTRATED).count() == 2
    assert Concept.objects.get(label="kriging").openalex_field_id == "23"


def test_a_paper_and_a_profile_meet_on_one_concept(ada, embedder):
    ada.profile.interests = {"areas": ["Semantic segmentation"]}
    ada.profile.save()
    service.project_declared(ada)
    work = _work(ada, "W1", method=["semantic segmentation"])
    demonstrated.record_work(work)
    assert (
        Edge.objects.get(author_work=work).concept
        == Edge.objects.get(user=ada, tier=Tier.DECLARED).concept
    )


def test_papers_reach_the_person_and_search_but_never_ranking(ada, embedder):
    demonstrated.record_work(_work(ada, "W1", method=["kriging"]))
    demonstrated.rollup(ada)
    assert [view.tier for view in read.own_edges(ada)] == [Tier.DEMONSTRATED]
    assert [view.tier for view in read.discoverable_edges([ada])] == [Tier.DEMONSTRATED]
    assert read.ranking_edges(ada) == []
    assert read.lab_declared_edges([ada]) == []


def test_no_person_is_ever_one_averaged_vector():
    """Per-work vectors only: nothing in the schema holds a person's expertise
    as a single vector (design §5.3)."""
    from django.apps import apps as registry

    for model in registry.get_app_config("knowledge").get_models():
        vectors = [
            f.name for f in model._meta.fields if f.get_internal_type() == "VectorField"
        ]
        if model is WorkFacets:
            assert vectors  # per work, per facet
        elif model is Concept:
            assert vectors == ["embedding"]  # an idea's, not a person's
        else:
            assert vectors == [], model.__name__
