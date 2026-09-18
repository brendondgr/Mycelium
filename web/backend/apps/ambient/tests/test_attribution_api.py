"""The editor's tools: aliases, channel hints, and "this was a different project".

The permission assertions are the load-bearing ones. An editor sees lab-channel
messages attributed to their lab project and nothing else — never a DM, never
somebody's personal project, never another lab's server, and never any message
text, because none is kept.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Lab, LabMembership
from apps.ambient.attribution import continuity_for
from apps.ambient.models import (
    AttributionCorrection,
    ChannelHint,
    Observation,
    ObservationFeedback,
    PlaceKind,
    RawMessageRef,
    Source,
)
from apps.research.models import Project, ProjectMember


@pytest.fixture
def lab(db):
    return Lab.objects.create(name="PULSE", slug="pulse")


@pytest.fixture
def pi(lab):
    user = User.objects.create_user("pi", "pi@example.org", "pw")
    LabMembership.objects.create(user=user, lab=lab, role=LabMembership.Role.OWNER)
    return user


@pytest.fixture
def ada(lab):
    user = User.objects.create_user("ada", "ada@example.org", "pw")
    LabMembership.objects.create(user=user, lab=lab)
    return user


@pytest.fixture
def guild(lab):
    return Source.objects.create(
        kind=Source.Kind.DISCORD_GUILD,
        external_id="g",
        lab=lab,
        consent_state=Source.Consent.ACTIVE,
    )


@pytest.fixture
def imaging(lab, ada):
    project = Project.objects.create(name="Imaging pipeline", scope_lab=lab)
    ProjectMember.objects.create(project=project, user=ada)
    return project


@pytest.fixture
def annotation(lab, ada):
    project = Project.objects.create(name="Annotation study", scope_lab=lab)
    ProjectMember.objects.create(project=project, user=ada)
    return project


def _client(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


_n = iter(range(100_000))


def _ref(source, speaker, project, *, place_kind=PlaceKind.CHANNEL, place_id="c1",
         label="methods", minutes_ago=5, **attribution):
    return RawMessageRef.objects.create(
        source=source,
        external_id=f"m{next(_n)}",
        place_kind=place_kind,
        place_id=place_id,
        place_label=label,
        speaker=speaker,
        sent_at=timezone.now() - timedelta(minutes=minutes_ago),
        project=project,
        project_confidence=0.8 if project else 0.0,
        attribution={
            "decided_by": "resolved",
            "anchor": True,
            "scores": {str(project.pk): {"name": 0.6}} if project else {},
            "matched": {str(project.pk): ["imaging"]} if project else {},
            **attribution,
        },
    )


def _url(project) -> str:
    return f"/api/ambient/projects/{project.pk}/conversation/"


# -- aliases -------------------------------------------------------------------------


def test_an_editor_can_set_aliases(pi, imaging):
    response = _client(pi).patch(
        f"/api/projects/{imaging.pk}/",
        {"aliases": ["IMG-seg", "img-SEG", "  ", "the imaging pipeline"]},
        format="json",
    )
    assert response.status_code == 200, response.data
    imaging.refresh_from_db()
    assert imaging.aliases == ["IMG-seg", "the imaging pipeline"]
    assert response.data["aliases"] == imaging.aliases


def test_an_alias_too_short_to_mean_anything_is_refused(pi, imaging):
    response = _client(pi).patch(
        f"/api/projects/{imaging.pk}/", {"aliases": ["ML"]}, format="json"
    )
    assert response.status_code == 400


def test_the_projects_own_name_is_not_an_alias(pi, imaging):
    _client(pi).patch(
        f"/api/projects/{imaging.pk}/",
        {"aliases": ["imaging PIPELINE", "IMG"]},
        format="json",
    )
    imaging.refresh_from_db()
    assert imaging.aliases == ["IMG"]


def test_a_member_who_cannot_edit_cannot_set_aliases(ada, imaging):
    response = _client(ada).patch(
        f"/api/projects/{imaging.pk}/", {"aliases": ["IMG"]}, format="json"
    )
    assert response.status_code == 403


# -- what an editor can see -----------------------------------------------------------


def test_an_editor_sees_lab_channel_attributions(pi, ada, guild, imaging):
    _ref(guild, ada, imaging)
    response = _client(pi).get(_url(imaging))
    assert response.status_code == 200
    (entry,) = response.data["attributions"]
    assert entry["speaker"]["name"] == "ada"
    assert entry["place_label"] == "methods"
    assert entry["matched"] == ["imaging"]
    assert entry["confidence"] == 0.8
    assert "text" not in entry  # there is no text to show


def test_a_dm_never_appears_in_a_lab_projects_list(pi, ada, guild, imaging):
    dm = Source.objects.create(
        kind=Source.Kind.DISCORD_DM, external_id="ada", consent_state="active"
    )
    _ref(dm, ada, imaging, place_kind=PlaceKind.DM, place_id="")
    assert _client(pi).get(_url(imaging)).data["attributions"] == []


def test_another_labs_server_never_appears(pi, ada, imaging):
    other = Lab.objects.create(name="Elsewhere", slug="elsewhere")
    theirs = Source.objects.create(
        kind=Source.Kind.DISCORD_GUILD,
        external_id="g2",
        lab=other,
        consent_state="active",
    )
    _ref(theirs, ada, imaging)
    assert _client(pi).get(_url(imaging)).data["attributions"] == []


def test_somebody_who_cannot_edit_the_project_sees_nothing(ada, guild, imaging):
    assert _client(ada).get(_url(imaging)).status_code == 403


def test_a_personal_project_shows_only_its_owners_messages(ada, guild):
    mine = Project.objects.create(name="Thesis", scope_user=ada)
    _ref(guild, ada, mine)
    response = _client(ada).get(_url(mine))
    assert len(response.data["attributions"]) == 1


def test_nobody_else_can_see_a_personal_projects_attributions(pi, ada, guild):
    mine = Project.objects.create(name="Thesis", scope_user=ada)
    _ref(guild, ada, mine)
    assert _client(pi).get(_url(mine)).status_code == 403


def test_the_card_lists_heard_channels_and_skips_excluded_ones(
    pi, ada, guild, imaging
):
    _ref(guild, ada, None, place_id="c1", label="methods")
    _ref(guild, ada, None, place_id="c2", label="random")
    guild.excluded_place_ids = ["c2"]
    guild.save(update_fields=["excluded_place_ids"])
    data = _client(pi).get(_url(imaging)).data
    assert [channel["label"] for channel in data["channels"]] == ["methods"]
    assert data["listening"] is True


def test_the_alternatives_are_the_labs_other_projects(pi, guild, imaging, annotation):
    data = _client(pi).get(_url(imaging)).data
    assert [one["name"] for one in data["alternatives"]] == ["Annotation study"]


# -- channel hints ---------------------------------------------------------------------


def _hint(user, project, place_id, on=True):
    return _client(user).post(
        f"/api/ambient/projects/{project.pk}/channel-hints/",
        {"place_id": place_id, "on": on},
        format="json",
    )


def test_an_editor_can_point_a_heard_channel_at_a_project(pi, ada, guild, imaging):
    _ref(guild, ada, None, place_id="c1")
    response = _hint(pi, imaging, "c1")
    assert response.status_code == 200
    assert response.data["hinted_channels"] == ["c1"]
    assert ChannelHint.objects.get().project == imaging


def test_a_channel_mylo_never_heard_cannot_be_hinted(pi, guild, imaging):
    assert _hint(pi, imaging, "nope").status_code == 400


def test_pointing_a_channel_elsewhere_moves_it(pi, ada, guild, imaging, annotation):
    _ref(guild, ada, None, place_id="c1")
    _hint(pi, imaging, "c1")
    _hint(pi, annotation, "c1")
    assert ChannelHint.objects.get().project == annotation


def test_a_hint_can_be_cleared(pi, ada, guild, imaging):
    _ref(guild, ada, None, place_id="c1")
    _hint(pi, imaging, "c1")
    _hint(pi, imaging, "c1", on=False)
    assert ChannelHint.objects.count() == 0


def test_a_hint_needs_a_listening_server(pi, imaging):
    assert _hint(pi, imaging, "c1").status_code == 400


# -- corrections -----------------------------------------------------------------------


def _correct(user, ref, project):
    return _client(user).post(
        f"/api/ambient/attributions/{ref.pk}/correct/",
        {"project": str(project.pk) if project else None},
        format="json",
    )


def test_an_editor_can_correct_an_attribution(pi, ada, guild, imaging, annotation):
    ref = _ref(guild, ada, imaging)
    response = _correct(pi, ref, annotation)
    assert response.status_code == 200, response.data
    ref.refresh_from_db()
    assert ref.project == annotation
    assert ref.project_confidence == 1.0
    assert ref.attribution["corrected"] is True


def test_a_correction_is_a_labelled_example_with_the_scores(
    pi, ada, guild, imaging, annotation
):
    ref = _ref(guild, ada, imaging)
    _correct(pi, ref, annotation)
    label = AttributionCorrection.objects.get()
    assert label.from_project == imaging
    assert label.to_project == annotation
    assert label.from_confidence == 0.8
    assert label.scores == {str(imaging.pk): {"name": 0.6}}
    assert label.corrected_by == pi


def test_not_about_a_project_is_a_valid_answer(pi, ada, guild, imaging):
    ref = _ref(guild, ada, imaging)
    _correct(pi, ref, None)
    ref.refresh_from_db()
    assert ref.project is None
    assert ref.attribution["corrected"] is True


def test_a_correction_reaches_an_observation_resting_on_it(
    pi, ada, guild, imaging, annotation
):
    ref = _ref(guild, ada, imaging)
    observation = Observation.objects.create(
        source=guild,
        speaker=ada,
        external_message_ids=[ref.external_id],
        observed_at=timezone.now(),
        text="On 12 Sep in #methods they said the masks were wrong.",
        understanding_kind="project_development",
        force="fact",
        place_kind=PlaceKind.CHANNEL,
        visibility="lab",
        project=imaging,
    )
    response = _correct(pi, ref, annotation)
    assert response.data["observations_updated"] == 1
    observation.refresh_from_db()
    assert observation.project == annotation
    feedback = ObservationFeedback.objects.get()
    assert feedback.verdict == ObservationFeedback.Verdict.CORRECTED
    assert feedback.channel == ObservationFeedback.Channel.WEB_REVIEW


def test_the_speaker_can_correct_their_own_message(ada, guild, imaging, annotation):
    ref = _ref(guild, ada, imaging)
    assert _correct(ada, ref, annotation).status_code == 200


def test_somebody_else_cannot_correct_it(lab, ada, guild, imaging, annotation):
    stranger = User.objects.create_user("cy", "cy@example.org", "pw")
    LabMembership.objects.create(user=stranger, lab=lab)
    ref = _ref(guild, ada, imaging)
    assert _correct(stranger, ref, annotation).status_code == 403


def test_nobody_can_file_a_message_under_another_labs_project(pi, ada, guild, imaging):
    other = Lab.objects.create(name="Elsewhere", slug="elsewhere")
    theirs = Project.objects.create(name="Theirs", scope_lab=other)
    ref = _ref(guild, ada, imaging)
    assert _correct(pi, ref, theirs).status_code == 403


def test_an_editor_cannot_file_a_message_under_the_speakers_personal_project(
    pi, ada, guild, imaging
):
    mine = Project.objects.create(name="Thesis", scope_user=ada)
    ref = _ref(guild, ada, imaging)
    assert _correct(pi, ref, mine).status_code == 403


def test_the_speaker_can_move_their_own_dm_to_a_lab_project_they_are_on(
    ada, imaging, annotation
):
    dm = Source.objects.create(
        kind=Source.Kind.DISCORD_DM, external_id="ada", consent_state="active"
    )
    ref = _ref(dm, ada, imaging, place_kind=PlaceKind.DM, place_id="")
    assert _correct(ada, ref, annotation).status_code == 200


def test_a_correction_becomes_an_anchor_for_continuity(
    pi, ada, guild, imaging, annotation
):
    ref = _ref(guild, ada, imaging, anchor=False)
    _correct(pi, ref, annotation)
    carried = continuity_for(guild, "c1", before=timezone.now())
    assert carried[0] == str(annotation.pk)
