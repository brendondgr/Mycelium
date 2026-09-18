"""The adapter contract, end to end, through a fake platform.

The point of these tests is that Discord is not the design. Everything a real
adapter does — resolve a surface, resolve a speaker, translate an event — is
exercised here without any Discord code existing, so the interface is verified
before the first platform is written against it.

They also pin the one thing an adapter must never do: make a message ingestible
by inventing a speaker for somebody who has no Mycelium account.
"""

import pytest
from django.contrib.auth.models import User
from django.core.cache import caches
from django.utils import timezone

from apps.ambient.adapters import adapter_for, register, registered
from apps.ambient.adapters.base import PlatformEvent
from apps.ambient.adapters.fake import FakeAdapter
from apps.ambient.models import (
    ListeningConsent,
    PlaceKind,
    Platform,
    RawMessageRef,
    Source,
    SpeakerKind,
)
from apps.billing.models import Subscription, Tier


@pytest.fixture(autouse=True)
def _ambient_on(settings):
    settings.AMBIENT_ENABLED = True
    settings.CACHES = {
        **settings.CACHES,
        "ambient": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "ambient-adapter-tests",
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
        label="PULSE Lab",
        consent_state=Source.Consent.ACTIVE,
    )


@pytest.fixture
def member(db) -> User:
    user = User.objects.create_user("ada", "ada@example.org", "pw")
    Subscription.objects.create(tier=Tier.SPORE, scope_user=user)
    ListeningConsent.objects.create(user=user, platform=Platform.DISCORD, enabled=True)
    return user


@pytest.fixture
def adapter(member) -> FakeAdapter:
    return FakeAdapter({"author-1": member})


def _event(**overrides) -> PlatformEvent:
    base = dict(
        source_external_id="guild-1",
        message_external_id="msg-1",
        text="the annotation cost is what is blocking us",
        sent_at=timezone.now(),
        author_external_id="author-1",
        place_kind=PlaceKind.CHANNEL,
        place_id="chan-1",
        place_label="methods",
    )
    base.update(overrides)
    return PlatformEvent(**base)


def test_an_event_reaches_the_ledger_through_the_adapter(source, adapter, member):
    outcome = adapter.deliver(_event())
    assert outcome.stored
    ref = RawMessageRef.objects.get()
    assert ref.source == source
    assert ref.speaker == member
    assert ref.speaker_external_id == "author-1"
    assert ref.place_label == "methods"


def test_a_surface_nobody_connected_is_not_listened_to(db, adapter):
    outcome = adapter.deliver(_event(source_external_id="some-other-guild"))
    assert not outcome.stored
    assert outcome.reason == "unknown_source"
    assert RawMessageRef.objects.count() == 0


def test_an_unknown_platform_identity_resolves_to_nobody(source, adapter):
    """The ordinary case: most people in a server have no Mycelium account."""
    assert adapter.resolve_speaker("a-stranger") is None
    outcome = adapter.deliver(_event(author_external_id="a-stranger"))
    assert outcome.reason == "speaker_unlinked"
    assert RawMessageRef.objects.count() == 0


def test_mylos_own_messages_are_buffered_without_a_speaker(source, adapter):
    outcome = adapter.deliver(
        _event(
            message_external_id="mylo-1",
            author_external_id="bot-1",
            text="Do you want that in your reports?",
            from_mylo=True,
        )
    )
    assert outcome.stored
    assert outcome.ref.speaker_id is None
    assert outcome.ref.speaker_kind == SpeakerKind.MYLO


def test_translation_carries_the_attachment_url_and_the_edit_time(
    source, adapter
):
    edited = timezone.now()
    outcome = adapter.deliver(
        _event(
            attachment_urls=["https://example.org/paper.pdf"],
            edited_at=edited,
        )
    )
    assert outcome.ref.attachment_urls == ["https://example.org/paper.pdf"]
    assert outcome.ref.edited_at == edited


def test_an_adapter_decides_nothing_about_meaning(source, adapter):
    """No understanding kind, no force, no project — those are later plans."""
    message = adapter.to_message(_event(), None)
    assert not hasattr(message, "understanding_kind")
    assert not hasattr(message, "force")
    assert not hasattr(message, "project")


def test_the_registry_finds_an_adapter_by_platform(adapter):
    register(adapter)
    try:
        assert adapter_for(Platform.DISCORD) is adapter
        assert Platform.DISCORD in registered()
    finally:
        registered().pop(Platform.DISCORD, None)


def test_nothing_is_registered_by_default():
    """A running deployment's registry only ever holds real platforms."""
    assert adapter_for(Platform.SLACK) is None


def test_a_dm_and_a_channel_are_different_places(source, adapter, member):
    adapter.deliver(_event())
    adapter.deliver(
        _event(
            message_external_id="msg-2",
            place_kind=PlaceKind.DM,
            place_id="",
            place_label="",
        )
    )
    kinds = set(RawMessageRef.objects.values_list("place_kind", flat=True))
    assert kinds == {PlaceKind.CHANNEL, PlaceKind.DM}
