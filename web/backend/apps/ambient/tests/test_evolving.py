"""Plan 05 — the evolving profile layer.

Pending understanding that ranks nothing until confirmed; developments told
and seen; supersession, fading and retraction; exploration themes that never
crowd a declared one; attention ordering; developments reaching the alerts;
the context version; and the stated profile byte-identical throughout.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from apps.accounts.models import Lab, Profile
from apps.ambient import deliberate, evolve, reconcile
from apps.ambient.models import (
    Finding,
    Observation,
    ProjectDevelopment,
    Source,
    Visibility,
)
from apps.billing.models import Subscription, Tier
from apps.knowledge.models import Concept, Edge, EdgeStatus, Facet, Relation, Scope
from apps.knowledge.read import confirmed_explorations, ranking_edges
from apps.knowledge.service import confirm
from apps.knowledge.tests.conftest import embedder  # noqa: F401 - the fake embedder
from apps.knowledge.tests.fakes import FakeEmbedder
from apps.research.models import Project, ProjectMember


@pytest.fixture(autouse=True)
def _on(settings, embedder):  # noqa: F811
    settings.AMBIENT_ENABLED = True
    settings.AMBIENT_CONSISTENT_DAYS = 2
    settings.AMBIENT_CONSISTENT_SPAN_DAYS = 5
    settings.AMBIENT_CONSISTENT_CONVERSATIONS = 2
    settings.AMBIENT_HALF_LIFE_DAYS = 21
    settings.AMBIENT_DRIFT_ENABLED = False
    settings.AMBIENT_DRIFT_WEIGHT = 0.15


def _person(name):
    user = User.objects.create_user(name, f"{name}@example.org", "pw")
    Subscription.objects.create(tier=Tier.SPORE, scope_user=user)
    return user


@pytest.fixture
def ada(db):
    user = _person("ada")
    profile, _ = Profile.objects.get_or_create(user=user)
    profile.interests = {
        "version": 2,
        "areas": ["medical imaging"],
        "keywords": ["mri"],
    }
    profile.save()
    return user


@pytest.fixture
def lab(db):
    return Lab.objects.create(name="PULSE", slug="pulse")


@pytest.fixture
def imaging(lab, ada):
    project = Project.objects.create(name="Imaging pipeline", scope_lab=lab)
    ProjectMember.objects.create(project=project, user=ada)
    return project


def _concept(label, facet=Facet.METHOD):
    return Concept.objects.create(
        label=label,
        facet=facet,
        scope=Scope.GLOBAL,
        embedding=FakeEmbedder().vector(label),
    )


def _source():
    return Source.objects.get_or_create(
        kind=Source.Kind.DISCORD_DM,
        external_id="dm",
        defaults={"consent_state": Source.Consent.ACTIVE},
    )[0]


def _noted(
    person,
    concept,
    *,
    days_ago,
    kind="current_curiosity",
    force="preference",
    subject="self",
    conversation=None,
    explicit=False,
    project=None,
    visibility=Visibility.PERSONAL,
    change="",
):
    return Observation.objects.create(
        source=_source(),
        external_message_ids=[f"m{days_ago}{force}"],
        observed_at=timezone.now() - timedelta(days=days_ago),
        speaker=person,
        text="Said they want to look into this further.",
        subject=subject,
        understanding_kind=kind,
        force=force,
        place_kind="dm",
        visibility=visibility,
        facet=concept.facet,
        topic=concept.label,
        concept=concept,
        explicit=explicit,
        project=project,
        change=change,
        conversation_key=conversation or f"c{days_ago}{force}",
    )


def _consistent(person, concept, **kwargs):
    _noted(person, concept, days_ago=15, conversation="a", **kwargs)
    _noted(person, concept, days_ago=1, conversation="b", **kwargs)


def _night():
    deliberate.deliberate()
    return evolve.evolve()


# -- understanding: pending, then confirmed -------------------------------------------


def test_a_suggestion_becomes_a_pending_edge_that_ranks_nothing(ada):
    cp = _concept("conformal prediction")
    _consistent(ada, cp)
    run = _night()
    assert run.edges == 1
    edge = Edge.objects.get(user=ada, tier="conversational")
    assert edge.status == EdgeStatus.PENDING
    assert edge.qualifier == "current_curiosity"
    assert edge.half_life_days == 21
    assert all(item.startswith("obs:") for item in edge.evidence)
    assert not [e for e in ranking_edges(ada) if e.tier == "conversational"]
    assert confirmed_explorations(ada) == []
    finding = Finding.objects.get(user=ada, concept=cp)
    assert finding.handled_outcome == Finding.Outcome.SUGGEST


def test_a_yes_makes_it_an_exploration_with_a_review_date(ada):
    cp = _concept("conformal prediction")
    _consistent(ada, cp)
    _night()
    review = timezone.localdate() + timedelta(days=30)
    assert confirm(ada, cp.pk, "interested_in", review_on=review)
    [exploration] = confirmed_explorations(ada)
    assert exploration.concept_id == cp.pk and exploration.review_on == review


def test_rerunning_the_night_changes_nothing(ada):
    cp = _concept("conformal prediction")
    _consistent(ada, cp)
    _night()
    edge = Edge.objects.get(user=ada, tier="conversational")
    before = (edge.last_reinforced, list(edge.evidence))
    _night()
    edge.refresh_from_db()
    assert Edge.objects.filter(user=ada, tier="conversational").count() == 1
    assert (edge.last_reinforced, list(edge.evidence)) == before


def test_new_evidence_reinforces(ada):
    cp = _concept("conformal prediction")
    _consistent(ada, cp)
    _night()
    first = Edge.objects.get(user=ada, tier="conversational").last_reinforced
    _noted(ada, cp, days_ago=0, conversation="c")
    _night()
    edge = Edge.objects.get(user=ada, tier="conversational")
    assert edge.last_reinforced > first and len(edge.evidence) == 3


def test_a_capability_is_a_can_do_edge(ada):
    kriging = _concept("kriging")
    _consistent(ada, kriging, kind="capability", force="fact")
    _night()
    edge = Edge.objects.get(user=ada, tier="conversational")
    assert edge.relation == Relation.CAN_DO and edge.qualifier == "capability"
    assert edge.half_life_days is None  # slow: it does not decay


def test_a_rejected_edge_stays_rejected_when_the_topic_returns(ada, settings):
    cp = _concept("conformal prediction")
    _consistent(ada, cp)
    _night()
    Edge.objects.filter(user=ada).update(
        status=EdgeStatus.REJECTED, updated_at=timezone.now() - timedelta(days=40)
    )
    _noted(ada, cp, days_ago=0, conversation="c")
    _night()
    assert (
        Edge.objects.get(user=ada, tier="conversational").status == EdgeStatus.REJECTED
    )


def test_the_stated_profile_is_byte_identical_after_a_confirmed_change(ada):
    """Acceptance: a stated field is untouched by anything automatic."""
    before = dict(Profile.objects.get(user=ada).interests)
    cp = _concept("conformal prediction")
    _consistent(ada, cp)
    _night()
    confirm(ada, cp.pk, "interested_in")
    _night()
    assert Profile.objects.get(user=ada).interests == before


# -- fading ---------------------------------------------------------------------------


def test_a_curiosity_unreinforced_for_two_half_lives_fades(ada):
    """Acceptance."""
    cp = _concept("conformal prediction")
    _consistent(ada, cp)
    _night()
    confirm(ada, cp.pk, "interested_in")
    Edge.objects.filter(user=ada).update(
        last_reinforced=timezone.now() - timedelta(days=43)
    )
    run = evolve.evolve()
    assert run.faded == 1
    assert Edge.objects.get(user=ada, tier="conversational").status == EdgeStatus.FADED
    assert confirmed_explorations(ada) == []


def test_one_half_life_is_not_enough_to_fade(ada):
    cp = _concept("conformal prediction")
    _consistent(ada, cp)
    _night()
    confirm(ada, cp.pk, "interested_in")
    Edge.objects.filter(user=ada).update(
        last_reinforced=timezone.now() - timedelta(days=25)
    )
    assert evolve.evolve().faded == 0


def test_a_capability_never_fades(ada):
    kriging = _concept("kriging")
    _consistent(ada, kriging, kind="capability", force="fact")
    _night()
    confirm(ada, kriging.pk, "can_do")
    Edge.objects.filter(user=ada).update(
        last_reinforced=timezone.now() - timedelta(days=400)
    )
    assert evolve.evolve().faded == 0


# -- developments ---------------------------------------------------------------------


def _told(
    person,
    project,
    concept,
    *,
    days_ago=1,
    change="dataset_arrived",
    visibility=Visibility.LAB,
):
    return _noted(
        person,
        concept,
        days_ago=days_ago,
        kind="project_development",
        force="fact",
        subject="project",
        explicit=True,
        project=project,
        visibility=visibility,
        change=change,
        conversation=f"t{days_ago}",
    )


def test_a_told_fact_is_an_active_development_at_once(ada, imaging):
    data = _concept("scanner dataset", Facet.SETTING)
    _told(ada, imaging, data)
    run = _night()
    development = ProjectDevelopment.objects.get()
    assert development.status == ProjectDevelopment.Status.ACTIVE
    assert development.origin == ProjectDevelopment.Origin.TOLD
    assert development.change == "dataset_arrived"
    assert development.visibility == Visibility.LAB
    assert run.developments == {"active": 1}
    _night()
    assert ProjectDevelopment.objects.count() == 1


def test_an_undone_development_is_not_brought_back(ada, imaging):
    data = _concept("scanner dataset", Facet.SETTING)
    _told(ada, imaging, data)
    _night()
    evolve.undo_development(ProjectDevelopment.objects.get(), by=ada)
    _night()
    assert list(ProjectDevelopment.objects.values_list("status", flat=True)) == [
        "rejected"
    ]


def test_a_later_development_supersedes_the_earlier(ada, imaging):
    data = _concept("scanner dataset", Facet.SETTING)
    _told(ada, imaging, data, days_ago=5)
    _night()
    _told(ada, imaging, data, days_ago=1, change="blocker_closed")
    run = _night()
    statuses = dict(ProjectDevelopment.objects.values_list("occurred_on", "status"))
    assert sorted(statuses.values()) == ["active", "superseded"]
    assert run.superseded == 1
    newest = ProjectDevelopment.objects.order_by("-occurred_on").first()
    assert newest.supersedes is not None


def test_ambient_development_talk_is_pending(ada, imaging):
    data = _concept("scanner dataset", Facet.SETTING)
    for days, key in ((15, "a"), (1, "b")):
        _noted(
            ada,
            data,
            days_ago=days,
            kind="project_development",
            force="fact",
            subject="project",
            project=imaging,
            visibility=Visibility.LAB,
            change="dataset_arrived",
            conversation=key,
        )
    _night()
    development = ProjectDevelopment.objects.get()
    assert development.status == ProjectDevelopment.Status.PENDING
    assert not development.in_effect


def test_a_dm_fact_about_a_lab_project_is_personal(ada, imaging):
    data = _concept("scanner dataset", Facet.SETTING)
    _told(ada, imaging, data, visibility=Visibility.PERSONAL)
    _night()
    development = ProjectDevelopment.objects.get()
    assert development.visibility == Visibility.PERSONAL
    from apps.ambient.read import developments_in_effect

    assert list(developments_in_effect(imaging)) == []  # the lab reader
    assert list(developments_in_effect(imaging, reader=ada)) == [development]


# -- retraction -----------------------------------------------------------------------


def test_forget_that_removes_a_pending_suggestion_and_its_development(ada, imaging):
    cp = _concept("conformal prediction")
    _consistent(ada, cp)
    data = _concept("scanner dataset", Facet.SETTING)
    _told(ada, imaging, data)
    _night()
    reconcile.forget_observations(
        ada, list(Observation.objects.values_list("pk", flat=True))
    )
    run = evolve.evolve()
    assert run.retractions == 1
    assert not Edge.objects.filter(user=ada, tier="conversational").exists()
    assert ProjectDevelopment.objects.get().status == ProjectDevelopment.Status.REJECTED


def test_a_confirmed_edge_survives_its_evidence_being_forgotten(ada):
    cp = _concept("conformal prediction")
    _consistent(ada, cp)
    _night()
    confirm(ada, cp.pk, "interested_in")
    reconcile.forget_observations(
        ada, list(Observation.objects.values_list("pk", flat=True))
    )
    evolve.evolve()
    edge = Edge.objects.get(user=ada, tier="conversational")
    assert edge.status == EdgeStatus.ACTIVE and edge.evidence == []


def test_opting_out_with_deletion_removes_every_derived_influence(ada, imaging):
    cp = _concept("conformal prediction")
    _consistent(ada, cp)
    data = _concept("scanner dataset", Facet.SETTING)
    _noted(
        ada,
        data,
        days_ago=1,
        kind="project_development",
        force="fact",
        subject="project",
        explicit=True,
        project=imaging,
        visibility=Visibility.LAB,
        change="dataset_arrived",
        conversation="t",
    )
    _night()
    confirm(ada, cp.pk, "interested_in")
    reconcile.forget_person(ada)
    evolve.evolve()
    assert not Edge.objects.filter(user=ada, tier="conversational").exists()
    assert not Finding.objects.filter(user=ada).exists()
    assert ProjectDevelopment.objects.get().status == ProjectDevelopment.Status.REJECTED
    # Their own declared profile is theirs and stays.
    assert Profile.objects.get(user=ada).interests["areas"] == ["medical imaging"]
