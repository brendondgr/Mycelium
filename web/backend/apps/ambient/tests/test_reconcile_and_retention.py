"""What happens when the conversation behind the ledger changes, or ends.

An edit invalidates a reading; a deletion removes the evidence; a person asking
to be forgotten takes everything with it. Each path that deletes leaves a
retraction, because a thing that had influence has to be able to have it taken
back out.

The retention sweep is here too, with the assertion Plan 01 actually cares
about: it removes message references past their window **and nothing else**.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.core.cache import caches
from django.utils import timezone

from apps.accounts.models import Lab
from apps.ambient import buffer, reconcile, retention
from apps.ambient.ingest import IncomingMessage, record
from apps.ambient.models import (
    Force,
    ListeningConsent,
    Observation,
    ObservationFeedback,
    PlaceKind,
    Platform,
    RawMessageRef,
    Retraction,
    Source,
    Subject,
    UnderstandingKind,
    Visibility,
)
from apps.billing.models import Subscription, Tier
from apps.research.models import Project


@pytest.fixture(autouse=True)
def _ambient_on(settings):
    settings.AMBIENT_ENABLED = True
    settings.AMBIENT_REPEAT_WINDOW_DAYS = 30
    settings.AMBIENT_REF_RETENTION_DAYS = 45
    settings.CACHES = {
        **settings.CACHES,
        "ambient": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "ambient-reconcile-tests",
        },
    }
    caches["ambient"].clear()
    yield
    caches["ambient"].clear()


@pytest.fixture
def source(db) -> Source:
    return Source.objects.create(
        kind=Source.Kind.DISCORD_GUILD,
        external_id="guild-1",
        consent_state=Source.Consent.ACTIVE,
    )


@pytest.fixture
def speaker(db) -> User:
    user = User.objects.create_user("ada", "ada@example.org", "pw")
    Subscription.objects.create(tier=Tier.SPORE, scope_user=user)
    ListeningConsent.objects.create(user=user, platform=Platform.DISCORD, enabled=True)
    return user


def _say(source, speaker, text, external_id="m1", sent_at=None):
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
        ),
    )


def _understand(source, speaker, external_ids, project=None):
    return Observation.objects.create(
        source=source,
        speaker=speaker,
        external_message_ids=list(external_ids),
        observed_at=timezone.now(),
        text="On 12 Sep in #methods they said annotation cost is the blocker.",
        subject=Subject.PROJECT,
        understanding_kind=UnderstandingKind.PROJECT_DEVELOPMENT,
        force=Force.FACT,
        place_kind=PlaceKind.CHANNEL,
        place_label="methods",
        visibility=Visibility.LAB,
        project=project,
    )


# -- an edit invalidates the reading, not the record ---------------------------


def test_an_edit_marks_what_rested_on_it_stale(source, speaker):
    _say(source, speaker, "annotation cost is the blocker")
    observation = _understand(source, speaker, ["m1"])

    touched = reconcile.message_edited(source, "m1", "compute cost is the blocker")
    assert touched == 1

    observation.refresh_from_db()
    assert observation.status == Observation.Status.STALE


def test_an_edit_replaces_the_body_in_the_buffer(source, speaker):
    _say(source, speaker, "annotation cost is the blocker")
    reconcile.message_edited(source, "m1", "compute cost is the blocker")
    assert buffer.get(source.pk, "m1") == "compute cost is the blocker"


def test_an_edit_recomputes_the_repeat_hash(source, speaker):
    _say(source, speaker, "the venue moved", external_id="m1")
    second = _say(source, speaker, "the venue moved", external_id="m2")
    assert second.repeat

    # The original is edited into something else; the copy is no longer a copy.
    reconcile.message_edited(source, "m1", "the venue is unchanged after all")
    second.ref.refresh_from_db()
    assert second.ref.repeat_of_id is None


def test_editing_a_message_nobody_recorded_does_nothing(source, speaker):
    assert reconcile.message_edited(source, "never-seen", "hello") == 0


# -- a deletion removes the evidence -------------------------------------------


def test_deleting_a_message_deletes_what_cited_it(source, speaker):
    _say(source, speaker, "annotation cost is the blocker")
    _understand(source, speaker, ["m1"])

    retraction = reconcile.message_deleted(source, "m1")

    assert Observation.objects.count() == 0
    assert retraction.reason == Retraction.Reason.PLATFORM_DELETE
    assert retraction.user == speaker
    assert retraction.recomputed_at is None


def test_deleting_a_message_drops_its_body_and_tombstones_the_reference(
    source, speaker
):
    _say(source, speaker, "annotation cost is the blocker")
    reconcile.message_deleted(source, "m1")

    assert buffer.get(source.pk, "m1") is None
    ref = RawMessageRef.objects.get(source=source, external_id="m1")
    assert ref.deleted_at is not None
    assert ref.content_hash == ""  # it can never be matched as a repeat again


def test_a_deleted_message_is_not_a_repeat_root_for_anything(source, speaker):
    _say(source, speaker, "the venue moved", external_id="m1")
    reconcile.message_deleted(source, "m1")
    third = _say(source, speaker, "the venue moved", external_id="m3")
    assert not third.repeat


def test_the_retraction_names_the_projects_that_must_be_recomputed(
    source, speaker, db
):
    lab = Lab.objects.create(name="PULSE")
    project = Project.objects.create(name="Imaging", scope_lab=lab)
    _say(source, speaker, "annotation cost is the blocker")
    _understand(source, speaker, ["m1"], project=project)

    retraction = reconcile.message_deleted(source, "m1")
    assert retraction.project_ids == [str(project.pk)]


def test_deleting_a_message_nothing_rested_on_records_no_retraction(source, speaker):
    _say(source, speaker, "good morning")
    assert reconcile.message_deleted(source, "m1") is None
    assert Retraction.objects.count() == 0


# -- delete my observations -----------------------------------------------------


def test_forgetting_a_person_removes_everything_derived_from_them(source, speaker):
    _say(source, speaker, "annotation cost is the blocker")
    observation = _understand(source, speaker, ["m1"])
    ObservationFeedback.objects.create(
        observation=observation,
        user=speaker,
        verdict=ObservationFeedback.Verdict.CONFIRMED,
        channel=ObservationFeedback.Channel.DM_DIALOGUE,
    )

    retraction = reconcile.forget_person(speaker)

    assert Observation.objects.filter(speaker=speaker).count() == 0
    assert RawMessageRef.objects.filter(speaker=speaker).count() == 0
    assert ObservationFeedback.objects.count() == 0
    assert buffer.get(source.pk, "m1") is None
    assert retraction.reason == Retraction.Reason.OPT_OUT
    assert retraction.observation_ids == [observation.pk]


def test_the_receipt_is_not_a_copy_of_what_it_removed(source, speaker):
    _say(source, speaker, "annotation cost is the blocker")
    _understand(source, speaker, ["m1"])
    retraction = reconcile.forget_person(speaker)
    assert "annotation" not in retraction.note
    assert "blocker" not in retraction.note


def test_forgetting_one_person_leaves_another_alone(source, speaker, db):
    other = User.objects.create_user("bo", "bo@example.org", "pw")
    Subscription.objects.create(tier=Tier.SPORE, scope_user=other)
    ListeningConsent.objects.create(user=other, platform=Platform.DISCORD, enabled=True)

    _say(source, speaker, "mine", external_id="m1")
    _say(source, other, "theirs", external_id="m2")
    _understand(source, other, ["m2"])

    reconcile.forget_person(speaker)
    assert Observation.objects.filter(speaker=other).count() == 1
    assert RawMessageRef.objects.filter(speaker=other).count() == 1


def test_a_person_can_remove_one_piece_of_evidence(source, speaker):
    _say(source, speaker, "annotation cost is the blocker")
    keep = _understand(source, speaker, ["m1"])
    drop = _understand(source, speaker, ["m1"])

    retraction = reconcile.forget_observations(speaker, [drop.pk])

    assert retraction.reason == Retraction.Reason.PERSON_REQUEST
    assert list(Observation.objects.values_list("pk", flat=True)) == [keep.pk]


def test_a_person_cannot_remove_somebody_elses_evidence(source, speaker, db):
    other = User.objects.create_user("bo", "bo@example.org", "pw")
    theirs = _understand(source, other, ["m9"])
    assert reconcile.forget_observations(speaker, [theirs.pk]) is None
    assert Observation.objects.filter(pk=theirs.pk).exists()


# -- a surface withdrawing consent ----------------------------------------------


def test_revoking_a_source_stops_listening_and_empties_the_buffer(source, speaker):
    _say(source, speaker, "annotation cost is the blocker")
    reconcile.revoke_source(source)

    source.refresh_from_db()
    assert not source.listening
    assert buffer.get(source.pk, "m1") is None


def test_revoking_a_source_does_not_erase_what_people_confirmed(source, speaker):
    """The observations are the people's record, not the server's."""
    _say(source, speaker, "annotation cost is the blocker")
    _understand(source, speaker, ["m1"])
    reconcile.revoke_source(source)
    assert Observation.objects.count() == 1


def test_revoking_with_deletion_leaves_a_retraction(source, speaker):
    _say(source, speaker, "annotation cost is the blocker")
    _understand(source, speaker, ["m1"])
    retraction = reconcile.revoke_source(source, delete_observations=True)
    assert Observation.objects.count() == 0
    assert retraction.reason == Retraction.Reason.SOURCE_REVOKED


# -- the sweep -------------------------------------------------------------------


def test_the_sweep_removes_references_past_the_window(source, speaker):
    _say(
        source,
        speaker,
        "old news",
        external_id="old",
        sent_at=timezone.now() - timedelta(days=60),
    )
    _say(source, speaker, "today's news", external_id="new")

    result = retention.sweep()

    assert result.refs_deleted == 1
    assert list(RawMessageRef.objects.values_list("external_id", flat=True)) == ["new"]


def test_the_sweep_touches_nothing_else(source, speaker):
    """Plan 01's acceptance criterion, word for word."""
    _say(
        source,
        speaker,
        "old news",
        external_id="old",
        sent_at=timezone.now() - timedelta(days=60),
    )
    observation = _understand(source, speaker, ["old"])

    retention.sweep()

    observation.refresh_from_db()
    assert observation.status == Observation.Status.ACTIVE
    assert Observation.objects.count() == 1
    assert Source.objects.count() == 1


def test_the_retention_window_can_never_undercut_the_repeat_window(settings):
    settings.AMBIENT_REPEAT_WINDOW_DAYS = 90
    settings.AMBIENT_REF_RETENTION_DAYS = 7
    assert retention.ref_retention_days() == 91


def test_the_sweep_clears_a_stamp_for_a_body_that_is_already_gone(source, speaker):
    outcome = _say(source, speaker, "annotation cost is the blocker")
    ref = outcome.ref
    ref.buffered_until = timezone.now() - timedelta(hours=1)
    ref.save(update_fields=["buffered_until"])

    result = retention.sweep()

    ref.refresh_from_db()
    assert ref.buffered_until is None
    assert result.stamps_cleared == 1
