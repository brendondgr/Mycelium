"""The door the Mylo gateway calls through, and the gates behind it.

Plan 02's acceptance criteria are here almost word for word: with listening off
a message in a lab channel produces no raw row; with listening on and a person
opted out, theirs produce none either; a DM produces a row; and turning
listening off purges the buffer for that source.

The other thing under test is quieter and matters as much: a refusal leaves a
count and never a name.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.core.cache import caches
from django.utils import timezone

from apps.accounts.models import Lab
from apps.ambient import buffer, service
from apps.ambient.models import (
    ListeningConsent,
    MemberNotice,
    Observation,
    PlaceKind,
    Platform,
    RawMessageRef,
    Source,
    SourceActivity,
)
from apps.billing.models import Subscription, Tier
from apps.integrations.models import DiscordIdentity

GUILD = "900000000000000001"
AUTHOR = "111111111111111111"


@pytest.fixture(autouse=True)
def _ambient_on(settings):
    settings.AMBIENT_ENABLED = True
    settings.AMBIENT_MIN_MESSAGE_CHARS = 24
    settings.CACHES = {
        **settings.CACHES,
        "ambient": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "ambient-service-tests",
        },
    }
    caches["ambient"].clear()
    yield
    caches["ambient"].clear()


@pytest.fixture
def lab(db) -> Lab:
    return Lab.objects.create(name="PULSE")


@pytest.fixture
def member(db) -> User:
    user = User.objects.create_user("ada", "ada@example.org", "pw")
    Subscription.objects.create(tier=Tier.SPORE, scope_user=user)
    DiscordIdentity.objects.create(
        user=user,
        discord_user_id=AUTHOR,
        link_method=DiscordIdentity.LinkMethod.ACTIVATION_CODE,
        state=DiscordIdentity.State.ACTIVE,
    )
    return user


@pytest.fixture
def opted_in(member) -> User:
    ListeningConsent.objects.create(
        user=member, platform=Platform.DISCORD, enabled=True
    )
    return member


@pytest.fixture
def listening(lab, db) -> Source:
    service.set_guild_listening(GUILD, on=True, lab=lab)
    return service.guild_source(GUILD)


def _heard(**overrides):
    fields = dict(
        guild_id=GUILD,
        message_id="msg-1",
        text="the annotation cost is what is blocking the imaging project",
        sent_at=timezone.now(),
        author_id=AUTHOR,
        place_kind=PlaceKind.CHANNEL,
        place_id="chan-1",
        place_label="methods",
    )
    fields.update(overrides)
    return service.heard(**fields)


# -- acceptance ------------------------------------------------------------------


def test_with_listening_off_a_lab_channel_produces_no_row(lab, opted_in):
    assert not _heard()
    assert RawMessageRef.objects.count() == 0


def test_with_listening_on_an_opted_in_member_is_recorded(listening, opted_in):
    assert _heard()
    ref = RawMessageRef.objects.get()
    assert ref.speaker == opted_in
    assert ref.place_label == "methods"
    assert not ref.explicit  # overheard, not addressed


def test_with_listening_on_and_a_person_opted_out_there_is_no_row(listening, member):
    outcome = _heard()
    assert not outcome
    assert outcome.reason == "person_not_opted_in"
    assert RawMessageRef.objects.count() == 0


def test_a_dm_to_mylo_is_recorded_and_is_always_explicit(db, opted_in):
    outcome = service.heard(
        guild_id="",
        message_id="dm-1",
        text="we dropped the simulation approach",
        sent_at=timezone.now(),
        author_id=AUTHOR,
        is_dm=True,
    )
    assert outcome
    ref = RawMessageRef.objects.get()
    assert ref.explicit
    assert ref.place_kind == PlaceKind.DM
    assert ref.source.kind == Source.Kind.DISCORD_DM
    assert ref.source.lab_id is None  # a DM belongs to nobody's lab


def test_turning_listening_off_purges_the_buffer_for_that_source(listening, opted_in):
    _heard()
    assert buffer.get(listening.pk, "msg-1") is not None

    service.set_guild_listening(GUILD, on=False)

    assert buffer.get(listening.pk, "msg-1") is None
    assert not service.listening_state(GUILD)["listening"]


def test_turning_listening_off_does_not_erase_what_was_understood(
    listening, opted_in
):
    Observation.objects.create(
        source=listening,
        speaker=opted_in,
        external_message_ids=["msg-1"],
        observed_at=timezone.now(),
        text="On 12 Sep they said annotation cost is the blocker.",
        understanding_kind="project_development",
        force="fact",
        place_kind=PlaceKind.CHANNEL,
        visibility="lab",
    )
    service.set_guild_listening(GUILD, on=False)
    assert Observation.objects.count() == 1


# -- a refusal leaves a count, never a name ----------------------------------------


def test_a_drop_is_counted_against_the_server_not_the_person(listening, member):
    _heard()
    activity = SourceActivity.objects.get(source=listening)
    assert activity.heard == 1
    assert activity.dropped_not_opted_in == 1
    assert activity.stored == 0
    # Nothing keyed to the person exists anywhere.
    assert RawMessageRef.objects.count() == 0


def test_the_counters_tell_a_quiet_server_from_a_misconfigured_one(
    listening, opted_in
):
    _heard(message_id="m1")  # stored
    _heard(message_id="m2", text="lol")  # chatter
    _heard(message_id="m3", is_bot=True)  # another bot
    service.set_channel_rule(GUILD, "chan-9", rule="excluded", on=True)
    _heard(message_id="m4", place_id="chan-9")

    activity = SourceActivity.objects.get(source=listening)
    assert activity.stored == 1
    assert activity.dropped_too_short == 1
    assert activity.dropped_bot == 1
    assert activity.dropped_excluded_channel == 1
    assert activity.heard == 4


def test_a_person_is_told_once_that_a_server_is_listening(listening, member):
    outcome = _heard()
    assert outcome.notify_member

    service.record_notice(GUILD, AUTHOR, delivered=True)

    assert not _heard(message_id="m2").notify_member
    assert MemberNotice.objects.count() == 1


def test_an_undeliverable_notice_is_not_recorded_as_delivered(listening, member):
    service.record_notice(GUILD, AUTHOR, delivered=False)
    assert MemberNotice.objects.get().delivered is False


def test_somebody_with_no_account_is_never_told_anything(listening, db):
    outcome = _heard(author_id="999999999999999999")
    assert not outcome
    assert outcome.reason == "speaker_unlinked"
    assert not outcome.notify_member
    assert MemberNotice.objects.count() == 0


# -- channel rules -----------------------------------------------------------------


def test_an_excluded_channel_is_never_read(listening, opted_in):
    service.set_channel_rule(GUILD, "chan-1", rule="excluded", on=True)
    assert not _heard()
    assert RawMessageRef.objects.count() == 0


def test_an_exclusion_can_be_lifted(listening, opted_in):
    service.set_channel_rule(GUILD, "chan-1", rule="excluded", on=True)
    service.set_channel_rule(GUILD, "chan-1", rule="excluded", on=False)
    assert _heard()


def test_a_social_channel_is_heard_but_never_kept(listening, opted_in):
    service.set_channel_rule(GUILD, "chan-1", rule="social", on=True)
    outcome = _heard()
    assert outcome.reason == "social_channel"
    assert RawMessageRef.objects.count() == 0


def test_the_two_channel_rules_stay_distinguishable(listening):
    service.set_channel_rule(GUILD, "chan-1", rule="excluded", on=True)
    service.set_channel_rule(GUILD, "chan-2", rule="social", on=True)
    state = service.listening_state(GUILD)
    assert state["excluded"] == ["chan-1"]
    assert state["social"] == ["chan-2"]


# -- member state ------------------------------------------------------------------


def test_a_member_can_turn_listening_on_and_off(member):
    assert service.member_state(AUTHOR) == {
        "linked": True,
        "enabled": False,
        "questions_muted": False,
        "available": True,
    }
    service.set_member_listening(AUTHOR, on=True)
    assert service.member_state(AUTHOR)["enabled"]
    service.set_member_listening(AUTHOR, on=False)
    assert not service.member_state(AUTHOR)["enabled"]


def test_an_unlinked_snowflake_has_no_state_to_change(db):
    assert service.set_member_listening("777", on=True) == {
        "linked": False,
        "enabled": False,
        "available": True,
    }
    assert not service.member_state("777")["linked"]


# -- edits and deletions ------------------------------------------------------------


def test_an_edit_reaches_the_ledger(listening, opted_in):
    _heard()
    touched = service.message_edited(
        GUILD, "msg-1", "the compute cost is what is blocking the imaging project"
    )
    assert touched == 0  # nothing was derived from it yet
    assert buffer.get(listening.pk, "msg-1").startswith("the compute cost")


def test_a_deletion_reaches_the_ledger(listening, opted_in):
    _heard()
    assert service.message_deleted(GUILD, "msg-1")
    ref = RawMessageRef.objects.get()
    assert ref.deleted_at is not None
    assert buffer.get(listening.pk, "msg-1") is None


def test_an_event_from_an_unknown_server_is_ignored(db):
    assert service.message_edited("nope", "m", "t") == 0
    assert service.message_deleted("nope", "m") is False


# -- the master switch --------------------------------------------------------------


def test_the_master_switch_stops_everything(settings, listening, opted_in):
    settings.AMBIENT_ENABLED = False
    outcome = _heard()
    assert outcome.reason == "ambient_disabled"
    assert RawMessageRef.objects.count() == 0
    assert SourceActivity.objects.count() == 0


def test_a_long_paste_is_truncated_rather_than_refused(listening, opted_in, settings):
    settings.AMBIENT_MAX_MESSAGE_CHARS = 100
    assert _heard(text="x" * 5000)
    assert len(buffer.get(listening.pk, "msg-1")) == 100


def test_listening_state_reports_todays_volume(listening, opted_in):
    _heard(message_id="m1")
    _heard(message_id="m2", text="lol")
    state = service.listening_state(GUILD)
    assert state["known"] and state["listening"]
    assert state["heard_today"] == 2
    assert state["stored_today"] == 1
    assert state["lab_name"] == "PULSE"


def test_an_unknown_server_reports_itself_as_unknown(db):
    assert service.listening_state("nope") == {
        "known": False,
        "available": True,
        "listening": False,
        "excluded": [],
        "social": [],
        "marker_channel_id": "",
    }


def test_listening_cannot_be_turned_on_while_the_ledger_is_off(settings, lab):
    """Otherwise a server reads "listening", and a public notice says so, while
    nothing is recorded — true neither now nor the day the switch flips."""
    settings.AMBIENT_ENABLED = False
    state = service.set_guild_listening(GUILD, on=True, lab=lab)
    assert state["refused"] == "unavailable"
    assert state["available"] is False
    assert service.guild_source(GUILD) is None


def test_listening_can_always_be_turned_off(settings, listening):
    settings.AMBIENT_ENABLED = False
    state = service.set_guild_listening(GUILD, on=False)
    assert "refused" not in state
    assert not state["listening"]


def test_a_member_is_told_when_listening_is_unavailable(settings, member):
    settings.AMBIENT_ENABLED = False
    state = service.set_member_listening(AUTHOR, on=True)
    assert state == {"linked": True, "enabled": True, "available": False}


def test_the_marker_is_remembered_so_it_is_edited_not_repeated(listening):
    service.set_marker(GUILD, channel_id="chan-5", message_id="msg-99")
    state = service.listening_state(GUILD)
    assert state["marker_channel_id"] == "chan-5"
    assert state["marker_message_id"] == "msg-99"


def test_yesterdays_counters_are_a_separate_row(listening, opted_in):
    _heard()
    SourceActivity.objects.update(day=timezone.localdate() - timedelta(days=1))
    _heard(message_id="m2")
    assert SourceActivity.objects.count() == 2
