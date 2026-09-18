"""Coverage: you, your lab, or a gap — and a lab-mate named only on what they state.

Plan CN-03's coverage acceptance, and Q3 (the third cross-entity query): for a
call, which slots the lab covers, by whom, and which are gaps.
"""

from apps.accounts.models import AuthorWork
from apps.collab import coverage
from apps.content.models import ContentItem
from apps.knowledge import demonstrated, service
from apps.knowledge.models import Relation, WorkFacets


def _by_text(fit):
    return {slot.text: slot for slot in fit.slots}


def test_q3_says_who_covers_what_and_what_is_missing(world):
    lab, ada, bo, call = world
    fit = coverage.for_call(lab, call)
    slots = _by_text(fit)
    assert slots["satellite remote sensing"].people == ("ada",)
    assert slots["coral reef ecology"].people == ("bo",)
    assert slots["environmental health"].is_gap
    assert slots["local marine park authority"].is_role
    assert (fit.covered, len(fit.matchable)) == (2, 3)
    assert fit.as_dict()["gaps"] == ["environmental health"]
    assert fit.as_dict()["roles"] == ["local marine park authority"]


def test_a_reader_covers_their_own_slots_and_sees_no_lab(world):
    _, ada, _, call = world
    fit = coverage.for_user(ada, [call])[str(call.pk)]
    slots = _by_text(fit)
    assert slots["satellite remote sensing"].covered_by == coverage.YOU
    assert slots["coral reef ecology"].is_gap  # bo's, but a reader sees no lab
    assert all(not slot.people for slot in fit.slots)


def test_a_lab_mate_is_never_named_on_papers_or_conversation(world, embedder):
    lab, ada, bo, call = world
    # bo's papers show environmental health, and Mylo understood it from
    # conversation too — neither is something bo's profile states.
    work = AuthorWork.objects.create(
        user=bo, source="openalex", source_id="W1", title="x"
    )
    WorkFacets.objects.create(
        author_work=work, terms={"method": ["environmental health"]}
    )
    demonstrated.record_person(bo)
    view = service.record_conversational(
        bo, surface="environmental health", relation=Relation.INTERESTED_IN
    )
    service.confirm(bo, view.concept_id, Relation.INTERESTED_IN)
    assert _by_text(coverage.for_call(lab, call))["environmental health"].is_gap
    # For bo's own card, their papers and confirmed conversation do count.
    own = coverage.for_user(bo, [call])[str(call.pk)]
    assert _by_text(own)["environmental health"].covered_by == coverage.YOU


def test_a_pending_suggestion_covers_nothing(world):
    _, ada, _, call = world
    service.record_conversational(
        ada, surface="environmental health", relation=Relation.INTERESTED_IN
    )
    fit = coverage.for_user(ada, [call])[str(call.pk)]
    assert _by_text(fit)["environmental health"].is_gap


def test_a_role_is_never_covered_even_by_the_same_words(world):
    lab, ada, _, call = world
    ada.profile.interests["areas"].append("local marine park authority")
    ada.profile.save()
    service.project_declared(ada)
    assert _by_text(coverage.for_call(lab, call))["local marine park authority"].is_role


def test_a_project_reads_its_labs_people(world):
    from apps.research.models import Project

    lab, ada, bo, call = world
    project = Project.objects.create(name="Bleaching", scope_lab=lab)
    fit = coverage.for_project(project, [call])[str(call.pk)]
    assert fit.covered == 2


def test_a_call_without_slots_has_no_fit(world, db):
    lab, *_ = world
    other = ContentItem.objects.create(type="grant", source="grants", external_id="G2")
    assert coverage.for_call(lab, other) is None


def test_the_threshold_decides(world, settings):
    lab, _, _, call = world
    settings.COLLAB_COVERAGE_COSINE = 0.9999
    slots = _by_text(coverage.for_call(lab, call))
    # The near wording no longer clears the bar; the exact words still do.
    assert slots["satellite remote sensing"].is_gap
    assert slots["coral reef ecology"].people == ("bo",)
