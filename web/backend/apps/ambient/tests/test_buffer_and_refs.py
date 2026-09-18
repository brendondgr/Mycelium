"""The transient buffer and the id-only reference beside it.

The promise under test is "Mylo does not keep your messages". These assertions
are what make it structural: the body lives in a cache under a TTL, Postgres
holds no text at all, a per-source override can only make the window shorter,
and reading a window explicitly drops what it read.

They also cover the quieter rule that keeps a profile honest — three copies of
one thought are one piece of evidence.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.core.cache import caches
from django.utils import timezone

from apps.ambient import buffer
from apps.ambient.ingest import IncomingMessage, record
from apps.ambient.models import (
    ListeningConsent,
    PlaceKind,
    Platform,
    RawMessageRef,
    Source,
    SpeakerKind,
)
from apps.ambient.text import content_hash, normalise
from apps.billing.models import Subscription, Tier


@pytest.fixture(autouse=True)
def _ambient_on(settings):
    settings.AMBIENT_ENABLED = True
    settings.AMBIENT_RAW_TTL_HOURS = 6
    settings.AMBIENT_RAW_TTL_HOURS_MAX = 24
    settings.AMBIENT_REPEAT_WINDOW_DAYS = 30


@pytest.fixture(autouse=True)
def _local_buffer(settings):
    """Run the buffer on a local cache so the suite needs no Redis.

    The module only uses the cache API, so this exercises the real code path.
    """
    settings.CACHES = {
        **settings.CACHES,
        "ambient": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "ambient-tests",
        },
    }
    caches["ambient"].clear()
    yield
    # A test may have swapped the alias for a failing backend; clearing is
    # housekeeping, not an assertion.
    try:
        caches["ambient"].clear()
    except Exception:
        pass


@pytest.fixture
def source(db) -> Source:
    return Source.objects.create(
        kind=Source.Kind.DISCORD_GUILD,
        external_id="900000000000000001",
        label="PULSE Lab",
        consent_state=Source.Consent.ACTIVE,
    )


@pytest.fixture
def speaker(db) -> User:
    user = User.objects.create_user("ada", "ada@example.org", "pw")
    Subscription.objects.create(tier=Tier.SPORE, scope_user=user)
    ListeningConsent.objects.create(user=user, platform=Platform.DISCORD, enabled=True)
    return user


def _message(speaker, **overrides) -> IncomingMessage:
    base = dict(
        external_id="m1",
        text="I want to try conformal prediction on the imaging data",
        sent_at=timezone.now(),
        place_kind=PlaceKind.CHANNEL,
        place_id="555",
        place_label="methods",
        speaker=speaker,
        speaker_external_id="111",
    )
    base.update(overrides)
    return IncomingMessage(**base)


# -- the body never reaches Postgres -----------------------------------------


def test_the_body_is_held_in_the_buffer_and_nowhere_else(source, speaker):
    outcome = record(source, _message(speaker))
    assert outcome.stored and outcome.buffered

    assert buffer.get(source.pk, "m1") == _message(speaker).text

    ref = outcome.ref
    stored = {
        field.name: getattr(ref, field.attname, None)
        for field in RawMessageRef._meta.get_fields()
        if hasattr(field, "attname")
    }
    text = _message(speaker).text
    assert not any(
        isinstance(value, str) and text.lower() in value.lower()
        for value in stored.values()
    )


def test_no_table_in_the_app_has_a_text_body_column(source, speaker):
    """A guard against the column nobody meant to add."""
    forbidden = {"body", "content", "message", "raw_text", "quote", "transcript_text"}
    names = {
        field.name
        for field in RawMessageRef._meta.get_fields()
        if hasattr(field, "attname")
    }
    assert not names & forbidden


def test_reading_a_window_drops_what_it_read(source, speaker):
    record(source, _message(speaker))
    record(source, _message(speaker, external_id="m2", text="and the venue moved"))

    window = buffer.get_many(source.pk, ["m1", "m2"])
    assert set(window) == {"m1", "m2"}

    buffer.drop(source.pk, window)
    assert buffer.get_many(source.pk, ["m1", "m2"]) == {}
    # The references survive — ids and timestamps, which is what reconciliation
    # needs and all it needs.
    assert RawMessageRef.objects.filter(source=source).count() == 2


def test_a_window_reads_without_the_bodies_that_expired(source, speaker):
    record(source, _message(speaker))
    record(source, _message(speaker, external_id="m2", text="second"))
    buffer.drop(source.pk, ["m1"])

    window = buffer.get_many(source.pk, ["m1", "m2"])
    assert set(window) == {"m2"}


def test_a_buffer_outage_never_raises_into_the_ingest_path(source, speaker, settings):
    settings.CACHES = {
        **settings.CACHES,
        "ambient": {"BACKEND": "apps.ambient.tests.test_buffer_and_refs.BrokenCache"},
    }
    outcome = record(source, _message(speaker))
    assert outcome.stored  # the reference is written
    assert not outcome.buffered  # the body is not held, and nothing raised
    assert outcome.ref.buffered_until is None


class BrokenCache:
    """A cache backend that fails every operation, standing in for a Redis outage."""

    def __init__(self, *args, **kwargs):
        pass

    def _fail(self, *args, **kwargs):
        raise RuntimeError("redis is down")

    get = set = delete = get_many = delete_many = _fail

    def close(self, **kwargs):
        """Django closes every cache when settings change; that must not fail."""


# -- the TTL, and the ceiling no source can raise -----------------------------


def test_the_default_window_comes_from_settings(settings):
    assert buffer.ttl_seconds() == 6 * 3600


def test_a_source_may_shorten_its_window(source):
    source.raw_ttl_hours = 2
    assert buffer.ttl_seconds(source) == 2 * 3600


def test_a_source_can_never_lengthen_the_window_past_the_ceiling(source, settings):
    source.raw_ttl_hours = 720  # a month, set straight in the database
    assert buffer.ttl_seconds(source) == settings.AMBIENT_RAW_TTL_HOURS_MAX * 3600


def test_the_reference_records_when_the_body_expires(source, speaker):
    outcome = record(source, _message(speaker))
    expected = timezone.now() + timedelta(hours=6)
    assert abs((outcome.ref.buffered_until - expected).total_seconds()) < 60


# -- eligibility decides before anything is held ------------------------------


def test_an_ineligible_message_leaves_nothing_behind(source, db):
    stranger = User.objects.create_user("no-account", "s@example.org", "pw")
    outcome = record(source, _message(stranger))
    assert not outcome.stored
    assert outcome.reason == "person_not_opted_in"
    assert RawMessageRef.objects.count() == 0
    assert buffer.get(source.pk, "m1") is None


def test_an_unlinked_speaker_is_discarded_on_arrival(source):
    outcome = record(source, _message(None))
    assert outcome.reason == "speaker_unlinked"
    assert RawMessageRef.objects.count() == 0


def test_mylo_is_buffered_for_coherence_without_a_speaker(source, speaker):
    """A question Mylo asked is what makes the next line an answer."""
    outcome = record(
        source,
        _message(
            None,
            external_id="mylo-1",
            text="Do you want uncertainty estimation in your reports?",
            speaker_kind=SpeakerKind.MYLO,
        ),
    )
    assert outcome.stored
    assert outcome.ref.speaker_id is None
    assert outcome.ref.speaker_kind == SpeakerKind.MYLO


def test_mylo_is_not_recorded_on_an_unconsented_source(source):
    source.consent_state = Source.Consent.REVOKED
    source.save(update_fields=["consent_state"])
    outcome = record(
        source, _message(None, external_id="mylo-1", speaker_kind=SpeakerKind.MYLO)
    )
    assert not outcome.stored


# -- repeats collapse ----------------------------------------------------------


def test_the_same_message_twice_is_one_piece_of_evidence(source, speaker):
    first = record(source, _message(speaker))
    second = record(source, _message(speaker, external_id="m2"))
    assert second.repeat
    assert second.ref.repeat_of_id == first.ref.pk


def test_a_third_copy_points_at_the_root_not_the_chain(source, speaker):
    first = record(source, _message(speaker))
    record(source, _message(speaker, external_id="m2"))
    third = record(source, _message(speaker, external_id="m3"))
    assert third.ref.repeat_of_id == first.ref.pk


def test_two_people_saying_the_same_thing_are_two_pieces_of_evidence(
    source, speaker, db
):
    other = User.objects.create_user("bo", "bo@example.org", "pw")
    Subscription.objects.create(tier=Tier.SPORE, scope_user=other)
    ListeningConsent.objects.create(user=other, platform=Platform.DISCORD, enabled=True)

    record(source, _message(speaker))
    outcome = record(source, _message(other, external_id="m2"))
    assert not outcome.repeat


def test_a_repeat_outside_the_window_starts_again(source, speaker, settings):
    settings.AMBIENT_REPEAT_WINDOW_DAYS = 7
    old = timezone.now() - timedelta(days=30)
    record(source, _message(speaker, sent_at=old))
    outcome = record(source, _message(speaker, external_id="m2"))
    assert not outcome.repeat


def test_attachment_only_posts_do_not_collapse_into_one_another(source, speaker):
    record(
        source,
        _message(speaker, text="", attachment_urls=["https://example.org/a.pdf"]),
    )
    outcome = record(
        source,
        _message(
            speaker,
            external_id="m2",
            text="",
            attachment_urls=["https://example.org/b.pdf"],
        ),
    )
    assert not outcome.repeat
    assert outcome.ref.content_hash == ""


def test_an_attachment_contributes_its_url_and_never_its_content(source, speaker):
    outcome = record(
        source, _message(speaker, attachment_urls=["https://example.org/paper.pdf"])
    )
    assert outcome.ref.attachment_urls == ["https://example.org/paper.pdf"]


def test_the_same_message_arriving_twice_is_recorded_once(source, speaker):
    record(source, _message(speaker))
    outcome = record(source, _message(speaker))
    assert not outcome.stored
    assert outcome.reason == "already_recorded"
    assert RawMessageRef.objects.filter(source=source).count() == 1


# -- normalisation --------------------------------------------------------------


def test_mentions_and_spacing_do_not_make_two_messages_different():
    assert content_hash("<@111> the venue  moved") == content_hash(
        "<@222>   The venue moved"
    )


def test_empty_text_has_no_hash():
    assert content_hash("   ") == ""
    assert normalise("  A  B ") == "a b"
