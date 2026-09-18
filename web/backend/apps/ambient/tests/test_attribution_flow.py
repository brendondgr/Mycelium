"""Attribution end to end: on arrival, across a conversation, and at night.

Plan 03's fixture list, as tests: two projects that share vocabulary; a
conversation that switches projects mid-channel; a lapsed speaker discarded; a
mention of a colleague; a thread that inherits, then diverges.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.core.cache import caches
from django.utils import timezone

from apps.accounts.models import Lab
from apps.ambient import read, reconcile, service
from apps.ambient.attribution import attribute_window
from apps.ambient.models import (
    ChannelHint,
    ListeningConsent,
    PlaceKind,
    Platform,
    RawMessageRef,
    SourceActivity,
)
from apps.billing.models import Subscription, Tier
from apps.integrations.models import DiscordIdentity
from apps.research.models import Project, ProjectMember, ProjectState

GUILD = "900"


@pytest.fixture(autouse=True)
def _ambient_on(settings):
    settings.AMBIENT_ENABLED = True
    settings.AMBIENT_MIN_MESSAGE_CHARS = 1
    settings.AMBIENT_ATTRIBUTION_FLOOR = 0.6
    settings.AMBIENT_ATTRIBUTION_MARGIN = 0.25
    settings.AMBIENT_CONTINUITY_MINUTES = 30
    settings.CACHES = {
        **settings.CACHES,
        "ambient": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "ambient-attribution-flow",
        },
    }
    caches["ambient"].clear()
    yield
    caches["ambient"].clear()


def _person(name: str, snowflake: str, *, opted_in=True) -> User:
    user = User.objects.create_user(name, f"{name}@example.org", "pw")
    Subscription.objects.create(tier=Tier.SPORE, scope_user=user)
    DiscordIdentity.objects.create(
        user=user,
        discord_user_id=snowflake,
        link_method=DiscordIdentity.LinkMethod.ACTIVATION_CODE,
        state=DiscordIdentity.State.ACTIVE,
    )
    if opted_in:
        ListeningConsent.objects.create(
            user=user, platform=Platform.DISCORD, enabled=True
        )
    return user


@pytest.fixture
def lab(db) -> Lab:
    return Lab.objects.create(name="PULSE", slug="pulse")


@pytest.fixture
def ada(db) -> User:
    return _person("ada", "111")


@pytest.fixture
def bo(db) -> User:
    return _person("bo", "222")


@pytest.fixture
def projects(lab, ada, bo):
    imaging = Project.objects.create(
        name="Imaging pipeline", scope_lab=lab, aliases=["IMG-seg"]
    )
    annotation = Project.objects.create(
        name="Annotation study", scope_lab=lab, aliases=["labelling study"]
    )
    for project in (imaging, annotation):
        for person in (ada, bo):
            ProjectMember.objects.create(project=project, user=person)
    ProjectState.objects.create(
        project=imaging,
        slow={"problem": "segmenting brain tumours in MRI", "data": ["BraTS 2021"]},
        fast={"venue_targets": [{"venue": "MICCAI"}]},
    )
    ProjectState.objects.create(
        project=annotation,
        slow={"problem": "what expert labels cost", "data": ["rater logs"]},
        fast={"venue_targets": [{"venue": "MICCAI"}]},
    )
    return imaging, annotation


@pytest.fixture
def listening(lab):
    service.set_guild_listening(GUILD, on=True, lab=lab)
    return service.guild_source(GUILD)


def _say(text, *, author="111", message_id, minutes_ago=0, place="chan-1",
         kind=PlaceKind.CHANNEL, label="methods", mentions=None):
    return service.heard(
        guild_id=GUILD,
        message_id=message_id,
        text=text,
        sent_at=timezone.now() - timedelta(minutes=minutes_ago),
        author_id=author,
        place_kind=kind,
        place_id=place,
        place_label=label,
        mention_ids=mentions,
    )


def _ref(message_id) -> RawMessageRef:
    return RawMessageRef.objects.get(external_id=message_id)


# -- on arrival -------------------------------------------------------------------


def test_an_alias_attributes_on_arrival(listening, projects):
    imaging, _ = projects
    _say("IMG-seg converged overnight", message_id="m1")
    ref = _ref("m1")
    assert ref.project == imaging
    assert ref.project_confidence >= 0.9
    assert ref.attribution["matched"][str(imaging.pk)] == ["IMG-seg"]
    assert ref.attributed_at is not None


def test_shared_vocabulary_is_left_unresolved(listening, projects):
    _say("we should aim for MICCAI this cycle", message_id="m1")
    ref = _ref("m1")
    assert ref.project is None
    assert ref.project_confidence == 0.0
    assert ref.attribution["decided_by"] in {"below_floor", "no_margin"}


def test_the_stored_attribution_is_not_the_message(listening, projects):
    _say("IMG-seg converged overnight after the new augmentation", message_id="m1")
    assert "augmentation" not in repr(_ref("m1").attribution)


def test_a_conversation_that_switches_projects_mid_channel(listening, projects):
    imaging, annotation = projects
    _say("IMG-seg converged overnight", message_id="m1", minutes_ago=3)
    _say("nice, ship it", message_id="m2", minutes_ago=2)
    _say("separately the labelling study needs more raters", message_id="m3",
         minutes_ago=1)
    _say("I can find two", message_id="m4", minutes_ago=0)

    assert _ref("m1").project == imaging
    assert _ref("m2").project == imaging  # carried by continuity
    assert _ref("m3").project == annotation  # the content moved on
    assert _ref("m4").project == annotation  # and continuity followed it


def test_continuity_does_not_cross_channels(listening, projects):
    _say("IMG-seg converged overnight", message_id="m1", minutes_ago=1)
    _say("nice, ship it", message_id="m2", place="chan-2")
    assert _ref("m2").project is None


def test_a_channel_hint_raises_but_does_not_decide(listening, projects):
    imaging, _ = projects
    ChannelHint.objects.create(source=listening, place_id="chan-1", project=imaging)
    _say("tired today", message_id="m1")
    ref = _ref("m1")
    assert ref.project is None
    assert ref.attribution["scores"][str(imaging.pk)] == {"hint": 0.3}


# -- threads ------------------------------------------------------------------------


def test_a_thread_inherits_then_diverges(listening, projects):
    imaging, annotation = projects
    kwargs = {"place": "thread-1", "kind": PlaceKind.THREAD, "label": "Friday sync"}
    _say("IMG-seg status?", message_id="t1", minutes_ago=90, **kwargs)
    # Long after continuity would have faded, the thread still holds.
    _say("done on my side", message_id="t2", minutes_ago=5, **kwargs)
    _say("different topic — the labelling study lost two raters", message_id="t3",
         minutes_ago=4, **kwargs)

    assert _ref("t1").project == imaging
    assert _ref("t2").project == imaging
    assert _ref("t3").project == annotation


# -- mentions ------------------------------------------------------------------------


def test_a_mentioned_colleague_is_recorded(listening, projects, bo):
    _say("bo has the numbers", message_id="m1", mentions=["222"])
    ref = _ref("m1")
    assert ref.mentions_count == 1
    assert ref.mentioned_user_ids == [bo.pk]


def test_somebody_who_never_opted_in_is_at_most_a_number(listening, projects):
    _person("cy", "333", opted_in=False)
    _say("cy has the numbers", message_id="m1", mentions=["333", "444"])
    ref = _ref("m1")
    assert ref.mentions_count == 2
    assert ref.mentioned_user_ids == []


def test_naming_yourself_is_not_a_mention(listening, projects):
    _say("note to self", message_id="m1", mentions=["111"])
    assert _ref("m1").mentions_count == 0


# -- edits -----------------------------------------------------------------------------


def test_an_edit_re_attributes(listening, projects):
    _, annotation = projects
    _say("IMG-seg is slow", message_id="m1")
    reconcile.message_edited(listening, "m1", "the labelling study is slow")
    assert _ref("m1").project == annotation


def test_an_edit_never_overrides_a_persons_correction(listening, projects):
    imaging, annotation = projects
    _say("IMG-seg is slow", message_id="m1")
    ref = _ref("m1")
    ref.project = annotation
    ref.attribution = {**ref.attribution, "corrected": True}
    ref.save(update_fields=["project", "attribution"])

    reconcile.message_edited(listening, "m1", "IMG-seg is very slow")
    assert _ref("m1").project == annotation


# -- a lapsed speaker ------------------------------------------------------------------


def test_a_speaker_who_opted_out_before_the_read_is_discarded(listening, projects, ada):
    _say("IMG-seg is slow", message_id="m1")
    ListeningConsent.objects.filter(user=ada).update(enabled=False)

    window = read.window(listening, since=timezone.now() - timedelta(hours=1))

    assert len(window) == 0
    assert not RawMessageRef.objects.filter(external_id="m1").exists()
    activity = SourceActivity.objects.get(source=listening)
    assert activity.dropped_lapsed == 1


def test_a_lapsed_plan_is_discarded_the_same_way(listening, projects, ada, bo):
    _say("IMG-seg is slow", message_id="m1")
    _say("agreed", author="222", message_id="m2")
    Subscription.objects.filter(scope_user=ada).delete()

    window = read.window(listening, since=timezone.now() - timedelta(hours=1))

    assert window.external_ids() == ["m2"]


def test_revalidation_can_be_skipped_explicitly(listening, projects, ada):
    _say("IMG-seg is slow", message_id="m1")
    ListeningConsent.objects.filter(user=ada).update(enabled=False)
    window = read.window(
        listening, since=timezone.now() - timedelta(hours=1), revalidate=False
    )
    assert len(window) == 1


# -- the nightly pass ------------------------------------------------------------------


def _fake_embedder(texts):
    """Tumours point one way, labels the other — enough to test the plumbing."""
    vectors = []
    for text in texts:
        folded = text.lower()
        vectors.append(
            [
                1.0 if ("tumour" in folded or "mri" in folded) else 0.0,
                1.0 if ("label" in folded or "rater" in folded) else 0.0,
                0.1,
            ]
        )
    return vectors


def test_the_nightly_pass_resolves_with_similarity(listening, projects):
    imaging, _ = projects
    ChannelHint.objects.create(source=listening, place_id="chan-1", project=imaging)
    _say("the tumour masks on the MRI look wrong", message_id="m1")
    assert _ref("m1").project is None  # the hint alone could not decide

    window = read.window(listening, since=timezone.now() - timedelta(hours=1))
    counts = attribute_window(window, embedder=_fake_embedder)

    assert counts == {"considered": 1, "resolved": 1}
    ref = _ref("m1")
    assert ref.project == imaging
    assert "semantic" in ref.attribution["scores"][str(imaging.pk)]


def test_the_nightly_pass_never_touches_a_resolved_attribution(listening, projects):
    imaging, _ = projects
    _say("IMG-seg is slow", message_id="m1")
    before = _ref("m1").attributed_at
    window = read.window(listening, since=timezone.now() - timedelta(hours=1))
    counts = attribute_window(window, embedder=_fake_embedder)
    assert counts["considered"] == 0
    assert _ref("m1").attributed_at == before


def test_the_nightly_pass_without_an_embedder_changes_nothing_it_cannot(
    listening, projects
):
    _say("we should aim for MICCAI", message_id="m1")
    window = read.window(listening, since=timezone.now() - timedelta(hours=1))
    counts = attribute_window(window)
    assert counts == {"considered": 1, "resolved": 0}


def test_a_dm_is_attributed_only_to_the_speakers_own_projects(db, ada, lab):
    mine = Project.objects.create(name="Thesis chapter", scope_user=ada)
    Project.objects.create(
        name="Shared lab thing", scope_lab=lab, share_in_lab_reports=True
    )
    service.heard(
        guild_id="",
        message_id="dm-1",
        text="the thesis chapter draft is done, the shared lab thing too",
        sent_at=timezone.now(),
        author_id="111",
        is_dm=True,
    )
    ref = _ref("dm-1")
    assert ref.project == mine
