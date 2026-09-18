"""The read API: windows, evidence, and the rule that guards a lab packet.

A window is assembled from Postgres (which messages) and Redis (which bodies
still exist), so it can honestly be short. Reading one releases the bodies it
read, because reading is what the buffer is for.

The load-bearing assertion here is the last one: lab evidence is filtered on
visibility inside the query. A private career aspiration reaching a lab packet
would be the single worst failure this feature could have, and it is not left
to a call site to remember.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.core.cache import caches
from django.utils import timezone

from apps.accounts.models import Lab
from apps.ambient import read
from apps.ambient.ingest import IncomingMessage, record
from apps.ambient.models import (
    Force,
    ListeningConsent,
    Observation,
    ObservationFeedback,
    PlaceKind,
    Platform,
    Retraction,
    Source,
    SpeakerKind,
    Subject,
    UnderstandingKind,
    Visibility,
)
from apps.billing.models import Subscription, Tier
from apps.research.models import Project


@pytest.fixture(autouse=True)
def _ambient_on(settings):
    settings.AMBIENT_ENABLED = True
    settings.CACHES = {
        **settings.CACHES,
        "ambient": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "ambient-read-tests",
        },
    }
    caches["ambient"].clear()
    yield
    caches["ambient"].clear()


@pytest.fixture
def lab(db) -> Lab:
    return Lab.objects.create(name="PULSE")


@pytest.fixture
def source(lab) -> Source:
    return Source.objects.create(
        kind=Source.Kind.DISCORD_GUILD,
        external_id="guild-1",
        lab=lab,
        consent_state=Source.Consent.ACTIVE,
    )


@pytest.fixture
def speaker(db) -> User:
    user = User.objects.create_user("ada", "ada@example.org", "pw")
    Subscription.objects.create(tier=Tier.SPORE, scope_user=user)
    ListeningConsent.objects.create(user=user, platform=Platform.DISCORD, enabled=True)
    return user


def _say(source, speaker, text, external_id, sent_at=None, **kwargs):
    return record(
        source,
        IncomingMessage(
            external_id=external_id,
            text=text,
            sent_at=sent_at or timezone.now(),
            place_kind=PlaceKind.CHANNEL,
            place_label="methods",
            speaker=speaker,
            speaker_external_id="author-1",
            **kwargs,
        ),
    )


def _understand(source, speaker, **overrides):
    fields = dict(
        source=source,
        speaker=speaker,
        external_message_ids=["m1"],
        observed_at=timezone.now(),
        text="On 12 Sep in #methods they said annotation cost is the blocker.",
        subject=Subject.PROJECT,
        understanding_kind=UnderstandingKind.PROJECT_DEVELOPMENT,
        force=Force.FACT,
        place_kind=PlaceKind.CHANNEL,
        place_label="methods",
        visibility=Visibility.LAB,
    )
    fields.update(overrides)
    return Observation.objects.create(**fields)


# -- windows --------------------------------------------------------------------


def test_a_window_reads_a_stretch_of_conversation_in_order(source, speaker):
    now = timezone.now()
    _say(source, speaker, "first", "m1", sent_at=now - timedelta(minutes=10))
    _say(source, speaker, "second", "m2", sent_at=now - timedelta(minutes=5))

    got = read.window(source, since=now - timedelta(hours=1))

    assert [message.text for message in got.messages] == ["first", "second"]
    assert got.complete


def test_a_window_carries_mylos_line_so_an_answer_makes_sense(source, speaker):
    now = timezone.now()
    record(
        source,
        IncomingMessage(
            external_id="mylo-1",
            text="Do you want that in your reports?",
            sent_at=now - timedelta(minutes=2),
            place_kind=PlaceKind.CHANNEL,
            speaker=None,
            speaker_kind=SpeakerKind.MYLO,
        ),
    )
    _say(source, speaker, "yes please", "m2", sent_at=now)

    got = read.window(source, since=now - timedelta(hours=1))
    assert [message.from_mylo for message in got.messages] == [True, False]


def test_a_window_is_honest_about_a_body_that_expired(source, speaker):
    now = timezone.now()
    _say(source, speaker, "first", "m1", sent_at=now - timedelta(minutes=10))
    _say(source, speaker, "second", "m2", sent_at=now - timedelta(minutes=5))

    from apps.ambient import buffer

    buffer.drop(source.pk, ["m1"])

    got = read.window(source, since=now - timedelta(hours=1))
    assert len(got) == 2
    assert len(got.readable) == 1
    assert not got.complete


def test_releasing_a_window_deletes_the_bodies_it_read(source, speaker):
    _say(source, speaker, "annotation cost is the blocker", "m1")
    got = read.window(source, since=timezone.now() - timedelta(hours=1))
    assert got.readable

    read.release(got)

    again = read.window(source, since=timezone.now() - timedelta(hours=1))
    assert again.readable == []
    assert len(again) == 1  # the reference stays; the words do not


def test_a_window_leaves_out_a_message_the_person_took_back(source, speaker):
    from apps.ambient import reconcile

    _say(source, speaker, "first", "m1")
    _say(source, speaker, "second", "m2")
    reconcile.message_deleted(source, "m1")

    got = read.window(source, since=timezone.now() - timedelta(hours=1))
    assert got.external_ids() == ["m2"]


def test_a_window_outside_the_range_is_empty(source, speaker):
    _say(source, speaker, "last week", "m1", sent_at=timezone.now() - timedelta(days=7))
    got = read.window(source, since=timezone.now() - timedelta(hours=1))
    assert len(got) == 0
    assert got.complete  # nothing is missing from nothing


# -- evidence --------------------------------------------------------------------


def test_observations_for_a_person_can_be_narrowed_by_kind(source, speaker):
    _understand(source, speaker)
    _understand(
        source,
        speaker,
        understanding_kind=UnderstandingKind.CURRENT_CURIOSITY,
        visibility=Visibility.PERSONAL,
    )
    rows = read.observations_for(
        speaker, kinds=[UnderstandingKind.CURRENT_CURIOSITY]
    )
    assert rows.count() == 1


def test_a_stale_observation_is_not_read_as_current(source, speaker):
    observation = _understand(source, speaker)
    observation.status = Observation.Status.STALE
    observation.save(update_fields=["status"])
    assert read.observations_for(speaker).count() == 0


def test_project_evidence_is_scoped_to_the_project(source, speaker, lab):
    project = Project.objects.create(name="Imaging", scope_lab=lab)
    other = Project.objects.create(name="Other", scope_lab=lab)
    _understand(source, speaker, project=project)
    assert read.project_evidence(project).count() == 1
    assert read.project_evidence(other).count() == 0


def test_a_private_aspiration_never_reaches_lab_evidence(source, speaker, lab):
    """The rule is in the query, not in the caller's memory."""
    _understand(
        source,
        speaker,
        understanding_kind=UnderstandingKind.CAREER_DIRECTION,
        text="They said they want to move toward clinical work.",
        visibility=Visibility.PERSONAL,
    )
    shared = _understand(source, speaker)

    rows = read.lab_evidence(lab)
    assert list(rows) == [shared]


def test_feedback_is_read_back_newest_first(source, speaker):
    observation = _understand(source, speaker)
    ObservationFeedback.objects.create(
        observation=observation,
        user=speaker,
        verdict=ObservationFeedback.Verdict.CONFIRMED,
        channel=ObservationFeedback.Channel.DM_DIALOGUE,
    )
    ObservationFeedback.objects.create(
        observation=observation,
        user=speaker,
        verdict=ObservationFeedback.Verdict.CORRECTED,
        channel=ObservationFeedback.Channel.WEB_REVIEW,
    )
    verdicts = list(read.feedback_for(observation).values_list("verdict", flat=True))
    assert verdicts[0] == "corrected"


# -- retractions and settings ------------------------------------------------------


def test_a_retraction_waits_until_it_has_been_recomputed(speaker):
    retraction = Retraction.objects.create(
        reason=Retraction.Reason.PERSON_REQUEST, user=speaker, observation_ids=[1]
    )
    assert list(read.pending_retractions()) == [retraction]

    read.mark_recomputed(retraction)
    assert list(read.pending_retractions()) == []


def test_the_read_api_answers_whether_somebody_is_listening(speaker):
    assert read.listening_enabled(speaker, Platform.DISCORD)
    assert not read.listening_enabled(speaker, Platform.SLACK)
    assert not read.questions_muted(speaker, Platform.DISCORD)


def test_active_sources_can_be_scoped_to_a_lab(source, lab, db):
    Source.objects.create(
        kind=Source.Kind.DISCORD_GUILD,
        external_id="guild-2",
        consent_state=Source.Consent.PENDING,
    )
    assert list(read.active_sources(lab=lab)) == [source]
    assert read.active_sources().count() == 1
