"""The ledger's shape, and the four things it refuses to store.

Plan 01's acceptance criteria are written here as tests because they are the
feature's promises, not its implementation details: an observation cannot exist
without a speaker, a visibility, and a passed grounding check; there is no
quote column anywhere; and a verdict, once given, is never rewritten.
"""

import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.ambient.models import (
    Force,
    Observation,
    ObservationFeedback,
    Origin,
    PlaceKind,
    Retraction,
    Source,
    Subject,
    UnderstandingKind,
    Visibility,
)


@pytest.fixture
def source(db) -> Source:
    return Source.objects.create(
        kind=Source.Kind.DISCORD_GUILD,
        external_id="900000000000000001",
        consent_state=Source.Consent.ACTIVE,
    )


@pytest.fixture
def speaker(db) -> User:
    return User.objects.create_user("ada", "ada@example.org", "pw")


def _observation(source, speaker, **overrides) -> Observation:
    fields = dict(
        source=source,
        speaker=speaker,
        external_message_ids=["m1", "m2"],
        observed_at=timezone.now(),
        text=(
            "On 12 Sep in #methods they said they wanted to try conformal "
            "prediction on the imaging data."
        ),
        subject=Subject.SELF,
        understanding_kind=UnderstandingKind.CURRENT_CURIOSITY,
        force=Force.PREFERENCE,
        place_kind=PlaceKind.CHANNEL,
        place_label="methods",
        visibility=Visibility.PERSONAL,
    )
    fields.update(overrides)
    return Observation.objects.create(**fields)


# -- what the ledger refuses ---------------------------------------------------


def test_an_observation_needs_a_speaker(source, speaker):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _observation(source, None)


def test_an_observation_needs_a_visibility(source, speaker):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _observation(source, speaker, visibility="")


def test_an_ungrounded_observation_cannot_be_saved(source, speaker):
    """Grounding is checked against the window before it is discarded; a row
    that failed it is not written at all."""
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _observation(source, speaker, grounded=False)


def test_an_observation_needs_mylos_account_of_what_was_said(source, speaker):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _observation(source, speaker, text="")


def test_project_confidence_stays_a_probability(source, speaker):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _observation(source, speaker, project_confidence=1.4)


def test_the_model_has_no_quote_column(source, speaker):
    """OD-A6, as a test. The evidence a person sees is an explanation Mylo
    wrote; nothing verbatim is stored, and no future migration should quietly
    add somewhere to put it."""
    forbidden = {"quote", "body", "raw_text", "content", "message", "verbatim"}
    names = {
        field.name
        for field in Observation._meta.get_fields()
        if hasattr(field, "attname")
    }
    assert not names & forbidden


# -- what it does store --------------------------------------------------------


def test_an_observation_records_where_and_when_without_an_unreadable_id(
    source, speaker
):
    observation = _observation(source, speaker)
    assert observation.place_kind == PlaceKind.CHANNEL
    assert observation.place_label == "methods"  # a name, not a snowflake
    assert observation.external_message_ids == ["m1", "m2"]


def test_extraction_confidence_is_separate_from_influence(source, speaker):
    """How sure the extractor is is not how much this should move anything."""
    observation = _observation(source, speaker, extraction_confidence=0.95)
    assert observation.extraction_confidence == 0.95
    assert observation.influence is None  # Plan 04's to set, and only its


def test_attribution_may_honestly_be_unresolved(source, speaker):
    observation = _observation(source, speaker)
    assert observation.project_id is None
    assert observation.project_confidence is None


def test_rows_are_written_as_model_output_by_default(source, speaker):
    """There is no rule-based fallback in this feature; `rule` exists so the
    harm check is a query."""
    assert _observation(source, speaker).origin == Origin.MODEL
    assert Observation.objects.filter(origin=Origin.RULE).count() == 0


def test_supersession_links_forward_and_back(source, speaker):
    earlier = _observation(
        source,
        speaker,
        text="We might try conformal prediction.",
        force=Force.POSSIBILITY,
    )
    later = _observation(
        source,
        speaker,
        text="We decided against conformal prediction.",
        force=Force.REJECTION,
        supersedes=earlier,
    )
    earlier.status = Observation.Status.SUPERSEDED
    earlier.superseded_at = timezone.now()
    earlier.save(update_fields=["status", "superseded_at"])

    assert later.supersedes_id == earlier.pk
    assert earlier.superseded_by.get() == later


def test_visibility_separates_a_career_aspiration_from_the_lab(source, speaker):
    personal = _observation(
        source,
        speaker,
        understanding_kind=UnderstandingKind.CAREER_DIRECTION,
        visibility=Visibility.PERSONAL,
    )
    shared = _observation(
        source,
        speaker,
        understanding_kind=UnderstandingKind.PROJECT_DEVELOPMENT,
        visibility=Visibility.LAB,
    )
    assert not personal.is_lab_visible
    assert shared.is_lab_visible
    lab_rows = Observation.objects.filter(visibility=Visibility.LAB)
    assert personal not in lab_rows


# -- feedback is a label, and labels are not rewritten -------------------------


def test_a_verdict_is_recorded_with_the_channel_it_came_through(source, speaker):
    observation = _observation(source, speaker)
    feedback = ObservationFeedback.objects.create(
        observation=observation,
        user=speaker,
        verdict=ObservationFeedback.Verdict.CONFIRMED,
        channel=ObservationFeedback.Channel.DM_DIALOGUE,
    )
    assert observation.feedback.get() == feedback


def test_feedback_is_append_only(source, speaker):
    observation = _observation(source, speaker)
    feedback = ObservationFeedback.objects.create(
        observation=observation,
        user=speaker,
        verdict=ObservationFeedback.Verdict.REJECTED,
        channel=ObservationFeedback.Channel.WEB_REVIEW,
    )
    feedback.verdict = ObservationFeedback.Verdict.CONFIRMED
    with pytest.raises(ValueError):
        feedback.save()


def test_a_correction_is_a_new_row_not_an_edit(source, speaker):
    observation = _observation(source, speaker)
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
        corrected_text="It was the tabular data, not the imaging data.",
        channel=ObservationFeedback.Channel.WEB_REVIEW,
    )
    verdicts = list(observation.feedback.values_list("verdict", flat=True))
    assert verdicts == ["corrected", "confirmed"]  # newest first, both kept


# -- retractions ---------------------------------------------------------------


def test_a_retraction_names_what_must_be_recomputed_and_keeps_no_text(
    source, speaker
):
    retraction = Retraction.objects.create(
        reason=Retraction.Reason.PLATFORM_DELETE,
        user=speaker,
        source=source,
        observation_ids=[7, 9],
        note="one message deleted on Discord",
    )
    assert retraction.recomputed_at is None
    names = {
        field.name
        for field in Retraction._meta.get_fields()
        if hasattr(field, "attname")
    }
    assert not names & {"text", "quote", "body"}
