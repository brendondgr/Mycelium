"""The consent surface: nobody is observed unless three separate things say yes.

These are the assertions that keep the product's promise structural rather than
intended. The feature ships off; a surface must be consented; a person must have
opted in on that platform; and their effective tier must be paid. A server
member without a Mycelium account never resolves to a speaker at all, so there
is no code path on which they could be recorded.
"""

import pytest
from django.contrib.auth.models import User

from apps.accounts.models import Lab, LabMembership
from apps.ambient.eligibility import observable, person_opted_in, questions_muted
from apps.ambient.models import ListeningConsent, Platform, Source
from apps.billing.models import Seat, Subscription, Tier


@pytest.fixture(autouse=True)
def _ambient_on(settings):
    """Every test here is about a later gate, so the master switch starts on."""
    settings.AMBIENT_ENABLED = True


@pytest.fixture
def lab(db) -> Lab:
    return Lab.objects.create(name="PULSE")


@pytest.fixture
def source(lab) -> Source:
    return Source.objects.create(
        kind=Source.Kind.DISCORD_GUILD,
        external_id="900000000000000001",
        label="PULSE Lab",
        lab=lab,
        consent_state=Source.Consent.ACTIVE,
    )


@pytest.fixture
def member(db) -> User:
    user = User.objects.create_user("ada", "ada@example.org", "pw")
    Subscription.objects.create(tier=Tier.SPORE, scope_user=user)
    ListeningConsent.objects.create(
        user=user, platform=Platform.DISCORD, enabled=True
    )
    return user


def test_a_consented_opted_in_paid_member_is_observable(member, source):
    assert observable(member, source)


def test_the_master_switch_refuses_everything(settings, member, source):
    settings.AMBIENT_ENABLED = False
    verdict = observable(member, source)
    assert not verdict
    assert verdict.reason == "ambient_disabled"


def test_a_member_without_a_mycelium_account_is_never_recorded(source):
    """An unlinked speaker resolves to None and is refused before anything else."""
    verdict = observable(None, source)
    assert not verdict
    assert verdict.reason == "speaker_unlinked"


def test_a_source_that_has_not_consented_refuses(member, source):
    source.consent_state = Source.Consent.PENDING
    source.save(update_fields=["consent_state"])
    assert observable(member, source).reason == "source_not_consented"


def test_a_revoked_source_refuses(member, source):
    source.consent_state = Source.Consent.REVOKED
    source.save(update_fields=["consent_state"])
    assert observable(member, source).reason == "source_not_consented"


def test_listening_is_off_until_the_person_turns_it_on(db, source):
    """No row means off. The default is off by construction, not by a flag."""
    user = User.objects.create_user("bo", "bo@example.org", "pw")
    Subscription.objects.create(tier=Tier.SPORE, scope_user=user)
    assert not person_opted_in(user, Platform.DISCORD)
    assert observable(user, source).reason == "person_not_opted_in"


def test_opting_out_takes_effect_on_the_next_message(member, source):
    consent = ListeningConsent.objects.get(user=member, platform=Platform.DISCORD)
    consent.enabled = False
    consent.save(update_fields=["enabled"])
    assert observable(member, source).reason == "person_not_opted_in"


def test_consent_is_per_platform(member, source):
    """Opting in on Discord says nothing about Slack."""
    assert person_opted_in(member, Platform.DISCORD)
    assert not person_opted_in(member, Platform.SLACK)


def test_a_free_tier_member_receives_nothing(db, source):
    user = User.objects.create_user("cy", "cy@example.org", "pw")
    ListeningConsent.objects.create(user=user, platform=Platform.DISCORD, enabled=True)
    assert observable(user, source).reason == "tier_free"


def test_a_free_personal_plan_on_a_paid_lab_seat_is_paid(db, lab, source):
    """The effective tier resolves exactly as the profile caps do.

    A PI on a free personal plan who holds a seat on the lab's plan is a paid
    user here, because a person's coverage is whatever plan actually covers
    them — never the plan that happens to be in their own name.
    """
    user = User.objects.create_user("di", "di@example.org", "pw")
    LabMembership.objects.create(user=user, lab=lab)
    subscription = Subscription.objects.create(tier=Tier.LAB, scope_lab=lab)
    Seat.objects.create(
        subscription=subscription,
        member=user,
        payer_lab=lab,
        status=Seat.Status.ACTIVE,
    )
    ListeningConsent.objects.create(user=user, platform=Platform.DISCORD, enabled=True)
    assert observable(user, source)


def test_a_pending_seat_is_not_yet_paid(db, lab, source):
    user = User.objects.create_user("el", "el@example.org", "pw")
    LabMembership.objects.create(user=user, lab=lab)
    subscription = Subscription.objects.create(tier=Tier.LAB, scope_lab=lab)
    Seat.objects.create(
        subscription=subscription,
        member=user,
        payer_lab=lab,
        status=Seat.Status.PENDING,
    )
    ListeningConsent.objects.create(user=user, platform=Platform.DISCORD, enabled=True)
    assert observable(user, source).reason == "tier_free"


def test_a_deactivated_account_is_not_observed(member, source):
    member.is_active = False
    member.save(update_fields=["is_active"])
    assert observable(member, source).reason == "speaker_inactive"


def test_shut_off_is_separate_from_listening(member, source):
    """"Shut off" silences the questions; it does not stop the record."""
    consent = ListeningConsent.objects.get(user=member, platform=Platform.DISCORD)
    consent.questions_muted = True
    consent.save(update_fields=["questions_muted"])
    assert questions_muted(member, Platform.DISCORD)
    assert observable(member, source)


def test_a_source_knows_its_platform(source):
    assert source.platform == Platform.DISCORD
    transcript = Source.objects.create(
        kind=Source.Kind.TRANSCRIPT, external_id="meet-1"
    )
    assert transcript.platform == Platform.TRANSCRIPT


def test_a_personal_dm_source_has_no_lab(db):
    dm = Source.objects.create(
        kind=Source.Kind.DISCORD_DM,
        external_id="123",
        consent_state=Source.Consent.ACTIVE,
    )
    assert dm.lab_id is None
    assert dm.listening
