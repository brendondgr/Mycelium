"""Plan 07 — what changed, what Mylo knows, and the switches, over HTTP.

Every change that took effect is listed with how and why and can be undone,
forever; an undo is its own logged change. A private change never reaches a
lab surface — the API enforces it. What Mylo knows is editable and deletable.
The settings are the person's, and "delete my observations" deletes.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from apps.accounts.models import Lab, LabMembership, Profile
from apps.ambient import deliberate, dialogue, evolve
from apps.ambient.models import (
    AppliedChange,
    Finding,
    ListeningConsent,
    Observation,
    ObservationFeedback,
    PendingSuggestion,
    Platform,
    ProjectDevelopment,
    Source,
    Visibility,
)
from apps.billing.models import Subscription, Tier
from apps.integrations.models import DiscordIdentity
from apps.knowledge.models import Concept, Edge, EdgeStatus, Facet, Scope
from apps.knowledge.tests.conftest import embedder  # noqa: F401 - the fake embedder
from apps.knowledge.tests.fakes import FakeEmbedder
from apps.research.models import Project, ProjectMember


@pytest.fixture(autouse=True)
def _on(settings, embedder):  # noqa: F811
    settings.AMBIENT_ENABLED = True
    settings.AMBIENT_CONSISTENT_DAYS = 2
    settings.AMBIENT_CONSISTENT_SPAN_DAYS = 5
    settings.AMBIENT_CONSISTENT_CONVERSATIONS = 2


def _person(name, snowflake, *, tier=Tier.SPORE):
    user = User.objects.create_user(name, f"{name}@example.org", "pw")
    Subscription.objects.create(tier=tier, scope_user=user)
    DiscordIdentity.objects.create(
        user=user,
        discord_user_id=snowflake,
        link_method=DiscordIdentity.LinkMethod.ACTIVATION_CODE,
        state=DiscordIdentity.State.ACTIVE,
    )
    ListeningConsent.objects.create(user=user, platform=Platform.DISCORD, enabled=True)
    profile, _ = Profile.objects.get_or_create(user=user)
    profile.interests = {"version": 2, "areas": ["medical imaging"]}
    profile.save()
    return user


@pytest.fixture
def ada(db):
    return _person("ada", "111")


@pytest.fixture
def bo(db):
    return _person("bo", "222")


@pytest.fixture
def lab(ada, bo):
    lab = Lab.objects.create(name="PULSE", slug="pulse")
    LabMembership.objects.create(user=ada, lab=lab, is_lead=True)
    LabMembership.objects.create(user=bo, lab=lab)
    return lab


@pytest.fixture
def imaging(lab, ada, bo):
    project = Project.objects.create(name="Imaging pipeline", scope_lab=lab)
    for person in (ada, bo):
        ProjectMember.objects.create(project=project, user=person)
    return project


def _concept(label, facet=Facet.METHOD):
    return Concept.objects.create(
        label=label,
        facet=facet,
        scope=Scope.GLOBAL,
        embedding=FakeEmbedder().vector(label),
    )


def _noted(person, concept, *, days_ago, conversation, **kwargs):
    source, _ = Source.objects.get_or_create(
        kind=Source.Kind.DISCORD_DM,
        external_id=f"dm-{person.pk}",
        defaults={"consent_state": Source.Consent.ACTIVE},
    )
    defaults = {
        "subject": "self",
        "understanding_kind": "current_curiosity",
        "force": "preference",
        "visibility": Visibility.PERSONAL,
    }
    return Observation.objects.create(
        source=source,
        external_message_ids=[f"m-{conversation}"],
        observed_at=timezone.now() - timedelta(days=days_ago),
        speaker=person,
        text="Said they want to look into this further.",
        place_kind="dm",
        facet=concept.facet,
        topic=concept.label,
        concept=concept,
        conversation_key=conversation,
        **{**defaults, **kwargs},
    )


def _night():
    deliberate.deliberate()
    Finding.objects.exclude(outcome="ignore").update(
        explanation="You brought this up on two days.", explained="written"
    )
    evolve.evolve()


def _answered_exploration(user, label="conformal prediction"):
    concept = _concept(label)
    _noted(user, concept, days_ago=15, conversation=f"{label}-a")
    _noted(user, concept, days_ago=1, conversation=f"{label}-b")
    _night()
    now = timezone.now()
    while now.weekday() >= 5:
        now -= timedelta(days=1)
    dialogue.schedule(now=now)
    s = PendingSuggestion.objects.get(user=user, topic=label)
    dialogue.answer(s, choice="reports", surface="web", by=user)
    return concept


def _told(person, project, label, visibility):
    concept = _concept(label, Facet.SETTING)
    _noted(
        person,
        concept,
        days_ago=1,
        conversation=f"told-{label}",
        understanding_kind="project_development",
        force="fact",
        subject="project",
        explicit=True,
        project=project,
        visibility=visibility,
        change="dataset_arrived",
    )
    _night()
    return concept


# -- what changed --------------------------------------------------------------


def test_a_confirmed_exploration_is_listed_with_how_and_why(ada, client):
    _answered_exploration(ada)
    client.force_login(ada)
    [row] = client.get("/api/ambient/changes/").json()["changes"]
    assert row["kind"] == "exploration_confirmed"
    assert row["topic"] == "conformal prediction"
    assert row["surface"] == "web" and row["explanation"]
    assert row["can_undo"] and row["by"]["you"]


def test_undo_reverses_logs_and_tells_the_evidence(ada, client):
    concept = _answered_exploration(ada)
    change = AppliedChange.objects.get()
    client.force_login(ada)
    response = client.post(f"/api/ambient/changes/{change.pk}/undo/")
    assert response.status_code == 200
    assert response.json()["undo"]["kind"] == "undone"
    assert Edge.objects.get(user=ada, concept=concept).status == EdgeStatus.REJECTED
    change.refresh_from_db()
    assert change.undone_at is not None
    assert (
        ObservationFeedback.objects.filter(channel="undo", verdict="rejected").count()
        == 2
    )
    again = client.post(f"/api/ambient/changes/{change.pk}/undo/")
    assert again.status_code == 409


def test_nobody_else_can_undo_my_change(ada, bo, client):
    _answered_exploration(ada)
    change = AppliedChange.objects.get()
    client.force_login(bo)
    assert client.post(f"/api/ambient/changes/{change.pk}/undo/").status_code == 403
    assert client.get("/api/ambient/changes/").json()["changes"] == []


def test_a_told_lab_fact_is_seen_by_the_project_and_the_lab(
    ada, bo, lab, imaging, client
):
    _told(ada, imaging, "scanner dataset", Visibility.LAB)
    change = AppliedChange.objects.get()
    assert change.kind == "development_recorded" and change.visibility == "lab"
    client.force_login(bo)
    assert [
        c["topic"] for c in client.get("/api/ambient/changes/").json()["changes"]
    ] == ["scanner dataset"]
    lab_rows = client.get(f"/api/ambient/labs/{lab.slug}/changes/").json()["changes"]
    assert [c["topic"] for c in lab_rows] == ["scanner dataset"]
    # bo is a member but not an editor: no undo for them.
    assert lab_rows[0]["can_undo"] is False
    client.force_login(ada)
    assert client.post(f"/api/ambient/changes/{change.pk}/undo/").status_code == 200
    assert ProjectDevelopment.objects.get().status == "rejected"


def test_a_private_project_fact_never_reaches_the_lab(ada, bo, lab, imaging, client):
    _told(ada, imaging, "scanner dataset", Visibility.PERSONAL)
    client.force_login(bo)
    assert client.get("/api/ambient/changes/").json()["changes"] == []
    assert client.get(f"/api/ambient/labs/{lab.slug}/changes/").json()["changes"] == []
    assert (
        client.get(f"/api/ambient/projects/{imaging.pk}/developments/").json()[
            "developments"
        ]
        == []
    )
    client.force_login(ada)
    assert len(client.get("/api/ambient/changes/").json()["changes"]) == 1
    assert (
        len(
            client.get(f"/api/ambient/projects/{imaging.pk}/developments/").json()[
                "developments"
            ]
        )
        == 1
    )


def test_a_lab_feed_is_for_its_members_only(ada, lab, client):
    outsider = _person("oz", "333")
    client.force_login(outsider)
    assert client.get(f"/api/ambient/labs/{lab.slug}/changes/").status_code == 403


# -- what Mylo knows -----------------------------------------------------------


def test_what_mylo_knows_says_where_each_thing_came_from(ada, client):
    from apps.knowledge.service import project_declared

    project_declared(ada)
    _answered_exploration(ada)
    client.force_login(ada)
    body = client.get("/api/ambient/understanding/").json()
    assert "does not keep your messages" in body["statement"]
    by_tier = {(e["tier"], e["status"]) for e in body["edges"]}
    assert ("declared", "active") in by_tier and ("conversational", "active") in by_tier
    conversational = next(e for e in body["edges"] if e["tier"] == "conversational")
    assert (
        conversational["source"] == "From conversation" and conversational["editable"]
    )
    declared = next(e for e in body["edges"] if e["tier"] == "declared")
    assert declared["source"] == "You wrote this" and not declared["editable"]


def test_rewording_makes_it_mine_and_deleting_removes_it(ada, client):
    concept = _answered_exploration(ada)
    client.force_login(ada)
    url = f"/api/ambient/understanding/{concept.pk}/interested_in/"
    client.patch(url, {"label": "conformal inference"}, content_type="application/json")
    edge = Edge.objects.get(user=ada, concept=concept)
    assert edge.surface == "conformal inference" and edge.edited_by_person
    assert client.delete(url).status_code == 204
    assert not Edge.objects.filter(
        user=ada, concept=concept, tier="conversational"
    ).exists()
    assert Finding.objects.get(user=ada, concept=concept).outcome == "ignore"


def test_a_declined_topic_rests_and_can_be_reopened(ada, client):
    concept = _answered_exploration(ada)
    Edge.objects.filter(user=ada, concept=concept).update(status="rejected")
    client.force_login(ada)
    row = next(
        e
        for e in client.get("/api/ambient/understanding/").json()["edges"]
        if e["tier"] == "conversational"
    )
    assert row["resting"] is True and row["eligible_again_on"]
    response = client.post(
        f"/api/ambient/understanding/{concept.pk}/interested_in/reopen/"
    )
    assert response.status_code == 200
    assert Edge.objects.get(user=ada, concept=concept).status == EdgeStatus.ACTIVE


# -- settings ------------------------------------------------------------------


def test_the_switches_are_mine(ada, client):
    client.force_login(ada)
    body = client.get("/api/ambient/settings/").json()
    assert body["paid"] and body["linked"] and body["listening"]["discord"]
    body = client.put(
        "/api/ambient/settings/",
        {
            "questions_muted": True,
            "quiet_until": "2026-10-01",
            "listening_discord": False,
        },
        content_type="application/json",
    ).json()
    assert body["questions_muted"] and body["quiet_until"] == "2026-10-01"
    assert body["listening"]["discord"] is False


def test_a_free_tier_can_turn_listening_off_but_never_on(db, client):
    fay = _person("fay", "444", tier=Tier.FREE)
    ListeningConsent.objects.filter(user=fay).update(enabled=False)
    client.force_login(fay)
    body = client.put(
        "/api/ambient/settings/",
        {"listening_discord": True},
        content_type="application/json",
    ).json()
    assert body["paid"] is False and body["listening"]["discord"] is False


def test_delete_my_observations_needs_a_confirmation_and_then_deletes(ada, client):
    _answered_exploration(ada)
    client.force_login(ada)
    assert (
        client.post(
            "/api/ambient/observations/delete/", {}, content_type="application/json"
        ).status_code
        == 400
    )
    response = client.post(
        "/api/ambient/observations/delete/",
        {"confirm": True},
        content_type="application/json",
    )
    assert response.json()["deleted_observations"] == 2
    assert not Observation.objects.filter(speaker=ada).exists()
    assert not Edge.objects.filter(user=ada, tier="conversational").exists()
