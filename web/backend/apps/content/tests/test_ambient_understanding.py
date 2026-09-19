"""Plan 05 as the matching layer sees it: exploration themes, attention,
developments in the alerts, the context version, the prompts.

The ledger side is ``apps/ambient/tests/test_evolving.py``; these live here
because the ambient app may not import ``apps.content`` (its boundary test).

Originally: Plan 05 — the evolving profile layer.

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
from apps.ambient import deliberate, evolve
from apps.ambient.models import (
    Observation,
    ProjectAttention,
    Source,
    Visibility,
)
from apps.billing.models import Subscription, Tier
from apps.knowledge.models import Concept, Edge, Facet, Relation, Scope
from apps.knowledge.service import confirm
from apps.knowledge.tests.conftest import embedder  # noqa: F401 - the fake embedder
from apps.knowledge.tests.fakes import FakeEmbedder
from apps.research.models import Project, ProjectMember, ProjectState


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


def _night():
    deliberate.deliberate()
    return evolve.evolve()


# -- reaching ranking: exploration themes ---------------------------------------------


def test_explorations_change_nothing_while_drift_is_off(ada):
    from apps.content import explorations

    cp = _concept("conformal prediction")
    _consistent(ada, cp)
    _night()
    confirm(ada, cp.pk, "interested_in")
    assert explorations.for_user(ada) == []
    interests = {"areas": ["medical imaging"]}
    assert explorations.with_explorations(interests, []) == (interests, {})


def test_an_exploration_is_its_own_theme_after_the_declared_ones(ada, settings):
    from apps.content import explorations
    from apps.content.clustering import cluster_interests

    settings.AMBIENT_DRIFT_ENABLED = True
    cp = _concept("conformal prediction")
    _consistent(ada, cp)
    _night()
    confirm(ada, cp.pk, "interested_in")
    found = explorations.for_user(ada)
    assert found == [(cp.pk, "conformal prediction")]
    interests, weights = explorations.with_explorations(
        Profile.objects.get(user=ada).interests, found
    )
    clusters = cluster_interests(interests)
    assert [c.id for c in clusters] == ["c-all", f"explore-{cp.pk}"]
    assert clusters[0].areas == ["medical imaging"]
    assert clusters[1].label == "Exploring: conformal prediction"
    assert weights == {f"explore-{cp.pk}": 0.15}


def test_an_exploration_already_declared_adds_nothing():
    from apps.content.explorations import with_explorations

    interests = {"areas": ["Conformal Prediction"]}
    assert with_explorations(interests, [(7, "conformal prediction")]) == (
        interests,
        {},
    )


def test_an_exploration_theme_cannot_outrank_an_equal_declared_one():
    from apps.content.fusion import combine_clusters

    class Item:
        def __init__(self, pk):
            self.id = pk

    items = {"a": Item("a"), "b": Item("b")}
    per_interest = {"declared": {"a": 0.8}, "explored": {"b": 0.8}}
    clusters = {"c1": ["declared"], "explore-1": ["explored"]}
    even = combine_clusters(per_interest, clusters, items, beta=0.15)
    weighted = combine_clusters(
        per_interest, clusters, items, beta=0.15, cluster_weights={"explore-1": 0.15}
    )
    assert {h.item.id: round(h.final_score, 4) for h in even} == {"a": 0.8, "b": 0.8}
    ranked = [h.item.id for h in sorted(weighted, key=lambda h: -h.final_score)]
    assert ranked == ["a", "b"]
    b = next(h for h in weighted if h.item.id == "b")
    assert b.per_cluster["explore-1"] == pytest.approx(0.8)  # its own slate order
    assert b.final_score == pytest.approx(0.8 * 0.15)


# -- attention ordering ---------------------------------------------------------------


def test_the_project_a_person_is_on_leads_their_report(ada, lab):
    from apps.content.briefing import by_attention

    a = Project.objects.create(name="Alpha", scope_lab=lab)
    b = Project.objects.create(name="Beta", scope_lab=lab)
    c = Project.objects.create(name="Gamma", scope_lab=lab)
    assert by_attention(ada, [a, b, c]) == ([a, b, c], None)
    now = timezone.now()
    ProjectAttention.objects.create(
        user=ada, project=c, share_7d=0.7, share_28d=0.4, computed_at=now
    )
    ProjectAttention.objects.create(
        user=ada, project=b, share_7d=0.3, share_28d=0.6, computed_at=now
    )
    ordered, lead = by_attention(ada, [a, b, c])
    assert ordered == [c, b, a]  # an idle project is kept, just not first
    assert lead == str(c.id)
    ProjectAttention.objects.filter(project=c).update(share_7d=0.35)
    assert by_attention(ada, [a, b, c])[1] is None  # no clear lead, no deeper slate


# -- developments reach the alerts ----------------------------------------------------


def test_a_closed_blocker_stops_matching_and_a_dropped_method_leaves_the_approach(
    ada, imaging
):
    from apps.content.alerts import developments_for
    from apps.content.matchers import blockers, overlap

    ProjectState.objects.create(
        project=imaging,
        slow={
            "blockers": [
                {"id": "b1", "text": "no annotation budget for the MRI labels"},
                {"id": "b2", "text": "waiting for GPU access"},
            ],
            "method": ["graph neural networks", "random forests"],
            "claimed_contribution": "segmentation with fewer labels",
        },
    )
    budget = _concept("annotation budget", Facet.SETTING)
    gnn = _concept("graph neural networks")
    _told(ada, imaging, budget, days_ago=3, change="blocker_closed")
    _told(ada, imaging, gnn, days_ago=2, change="method_dropped")
    _night()
    changed = developments_for(imaging, ada)
    assert changed == {
        "blocker_closed": ("annotation budget",),
        "method_dropped": ("graph neural networks",),
    }
    slow = imaging.state.slow
    assert (
        overlap._project_approach(slow, changed["method_dropped"]) == "random forests"
    )
    assert overlap._project_approach(slow) == "graph neural networks random forests"

    class Precis:
        reusable = "a labelled MRI dataset and GPU hours"

    rows = blockers.blocker_rows(
        imaging, {"x": Precis()}, closed=changed["blocker_closed"]
    )
    assert {row.blocker_id for row in rows} == {"b2"}


def test_a_private_development_never_reaches_a_lab_reader(ada, imaging, lab):
    from apps.content.alerts import developments_for

    budget = _concept("annotation budget", Facet.SETTING)
    _told(ada, imaging, budget, change="blocker_closed", visibility=Visibility.PERSONAL)
    _night()
    assert developments_for(imaging, lab) == {}
    assert developments_for(imaging, ada) == {"blocker_closed": ("annotation budget",)}


# -- the context version --------------------------------------------------------------


def test_the_context_version_moves_only_when_the_picture_does(ada, imaging):
    from apps.content.understanding import context_version

    first = context_version(ada, None, [imaging])
    assert first == context_version(ada, None, [imaging])
    cp = _concept("conformal prediction")
    _consistent(ada, cp)
    _night()
    assert context_version(ada, None, [imaging]) == first  # pending changes nothing
    confirm(ada, cp.pk, "interested_in")
    second = context_version(ada, None, [imaging])
    assert second != first
    _told(ada, imaging, _concept("scanner dataset", Facet.SETTING))
    _night()
    assert context_version(ada, None, [imaging]) != second


# -- the confirmed-understanding fields ------------------------------------------------


def test_the_contract_accepts_the_new_fields_and_nothing_else():
    from rest_framework.exceptions import ValidationError

    from apps.accounts.interests import validate_interests

    ok = validate_interests(
        {
            "areas": ["x"],
            "preferences": ["empirical over theoretical"],
            "trajectory": {"direction": "clinical research", "horizon": "two years"},
            "learning_goals": ["causal inference"],
        }
    )
    assert ok["trajectory"]["direction"] == "clinical research"
    with pytest.raises(ValidationError):
        validate_interests({"areas": ["x"], "trajectory": {"horizon": "soon"}})
    with pytest.raises(ValidationError):
        validate_interests({"areas": ["x"], "explorations": ["y"]})


def test_the_prompts_read_the_new_fields_only_when_set():
    from apps.content import understanding
    from apps.content.opportunity_llm import _profile_text

    plain = {"areas": ["medical imaging"]}
    assert understanding.lines(plain) == []
    assert _profile_text(plain, {}) == "Research focus: medical imaging"
    rich = {
        **plain,
        "preferences": ["reproducible code matters"],
        "trajectory": {"direction": "clinical research", "target_stage": "postdoc"},
        "learning_goals": ["causal inference"],
    }
    text = _profile_text(rich, {})
    assert "Work preferences: reproducible code matters" in text
    assert "Career direction: clinical research (postdoc)" in text
    assert "Wants to learn (not yet a skill): causal inference" in text


def test_a_learning_goal_on_the_profile_is_a_wants_to_learn_edge(ada):
    from apps.knowledge.service import project_declared

    profile = Profile.objects.get(user=ada)
    profile.interests = {**profile.interests, "learning_goals": ["causal inference"]}
    profile.save()
    project_declared(ada)
    assert (
        Edge.objects.filter(
            user=ada, tier="declared", relation=Relation.WANTS_TO_LEARN
        ).count()
        == 1
    )
