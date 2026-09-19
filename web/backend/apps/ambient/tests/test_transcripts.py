"""Plan 11 — meeting transcripts: one meeting, one window.

The uploader must belong to the meeting's project or lab; a label mapped to
nobody, or to someone outside it, never reaches the buffer; a participant
who has not opted in to transcripts is dropped by the same gate as any
message; only project developments are kept from what is read, at a lower
weight.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from apps.accounts.models import Lab, LabMembership
from apps.ambient import deliberate, transcripts
from apps.ambient.models import (
    ChannelHint,
    ListeningConsent,
    Observation,
    Platform,
    RawMessageRef,
    Source,
    TranscriptMeeting,
)
from apps.billing.models import Subscription, Tier
from apps.research.models import Project, ProjectMember

MET = timezone.make_aware(datetime(2026, 9, 17, 14, 0))

VTT = """WEBVTT

1
00:00:01.000 --> 00:00:04.000
<v Ada>We decided to drop the GNN baseline.</v>

2
00:00:05.000 --> 00:00:09.000
<v Bo>Agreed, and the annotation budget came through.</v>

3
00:00:10.000 --> 00:00:12.000
<v Guest>Nice, congrats everyone.</v>
"""


@pytest.fixture(autouse=True)
def _on(settings):
    settings.AMBIENT_ENABLED = True
    settings.AMBIENT_TRANSCRIPTS_ENABLED = True


def _person(name, *, opted_in=True):
    user = User.objects.create_user(name, f"{name}@example.org", "pw")
    Subscription.objects.create(tier=Tier.SPORE, scope_user=user)
    if opted_in:
        ListeningConsent.objects.create(
            user=user, platform=Platform.TRANSCRIPT, enabled=True
        )
    return user


@pytest.fixture
def team(db):
    ada, bo = _person("ada"), _person("bo", opted_in=False)
    lab = Lab.objects.create(name="PULSE", slug="pulse")
    project = Project.objects.create(name="Imaging pipeline", scope_lab=lab)
    for person in (ada, bo):
        LabMembership.objects.create(user=person, lab=lab)
        ProjectMember.objects.create(project=project, user=person)
    return SimpleNamespace(ada=ada, bo=bo, lab=lab, project=project)


# -- parsing -----------------------------------------------------------------------


def test_webvtt_voices_become_turns():
    turns = transcripts.parse(VTT)
    assert [(t.label, t.offset_seconds) for t in turns] == [
        ("Ada", 1.0),
        ("Bo", 5.0),
        ("Guest", 10.0),
    ]
    assert turns[0].text == "We decided to drop the GNN baseline."


def test_srt_and_plain_lines_with_speakers():
    srt = (
        "1\n00:01:00,000 --> 00:01:03,000\nAda: The deadline moved to March.\n\n"
        "2\n00:01:04,000 --> 00:01:06,000\nAda: And we need a second annotator.\n"
    )
    [turn] = transcripts.parse(srt)
    assert turn.label == "Ada" and turn.offset_seconds == 60.0
    assert "second annotator" in turn.text
    plain = "[00:02:10] Bo: first point\ncontinued here\nAda: reply"
    turns = transcripts.parse(plain)
    assert [(t.label, t.text) for t in turns] == [
        ("Bo", "first point continued here"),
        ("Ada", "reply"),
    ]
    assert turns[0].offset_seconds == 130


def test_labels_in_order():
    assert transcripts.labels(VTT) == ["Ada", "Bo", "Guest"]


# -- ingest ------------------------------------------------------------------------


def test_only_mapped_opted_in_members_reach_the_buffer(team):
    meeting = transcripts.ingest(
        team.ada,
        title="Imaging sync",
        occurred_at=MET,
        text=VTT,
        speakers={"Ada": team.ada.pk, "Bo": team.bo.pk, "Guest": None},
        project=team.project,
    )
    [ref] = RawMessageRef.objects.all()
    assert ref.speaker == team.ada and ref.place_kind == "transcript"
    assert ref.sent_at == MET + timedelta(seconds=1)
    assert meeting.counts == {
        "stored": 1,
        "unmapped": 1,
        "not_a_member": 0,
        "person_not_opted_in": 1,
    }
    assert sorted(meeting.participant_ids) == sorted([team.ada.pk, team.bo.pk])
    source = meeting.source
    assert source.kind == Source.Kind.TRANSCRIPT and source.raw_ttl_hours == 3
    hint = ChannelHint.objects.get(source=source)
    assert hint.project == team.project


def test_a_label_mapped_to_an_outsider_is_dropped(team):
    stranger = _person("zed")
    meeting = transcripts.ingest(
        team.ada,
        title="Imaging sync",
        occurred_at=MET,
        text=VTT,
        speakers={"Ada": team.ada.pk, "Guest": stranger.pk},
        project=team.project,
    )
    assert meeting.counts["not_a_member"] == 1
    assert not RawMessageRef.objects.filter(speaker=stranger).exists()


def test_the_uploader_must_belong_to_the_meeting(team):
    outsider = _person("oz")
    with pytest.raises(transcripts.TranscriptRefused):
        transcripts.ingest(
            outsider,
            title="x",
            occurred_at=MET,
            text=VTT,
            speakers={},
            project=team.project,
        )
    assert not TranscriptMeeting.objects.exists()


def test_nothing_while_transcripts_are_off(team, settings):
    settings.AMBIENT_TRANSCRIPTS_ENABLED = False
    with pytest.raises(transcripts.TranscriptRefused):
        transcripts.ingest(
            team.ada,
            title="x",
            occurred_at=MET,
            text=VTT,
            speakers={},
            project=team.project,
        )


# -- what reading keeps, and how much it weighs ----------------------------------------


def test_a_meeting_yields_developments_only():
    kept = transcripts.keep_only_developments(
        [
            SimpleNamespace(kind="project_development"),
            SimpleNamespace(kind="current_curiosity"),
            SimpleNamespace(kind="enduring_interest"),
        ]
    )
    assert [item.kind for item in kept] == ["project_development"]


def test_speech_weighs_less_than_writing(team, settings):
    settings.AMBIENT_TRANSCRIPT_WEIGHT = 0.3
    source = Source.objects.create(kind=Source.Kind.DISCORD_DM, external_id="d")
    base = dict(
        source=source,
        external_message_ids=["m"],
        observed_at=timezone.now(),
        speaker=team.ada,
        text="Said the lab decided to drop the GNN baseline.",
        subject="project",
        understanding_kind="project_development",
        force="decision",
        visibility="lab",
    )
    written = Observation(**base, place_kind="channel")
    spoken = Observation(**base, place_kind="transcript")
    now = timezone.now()
    assert deliberate._weight(spoken, now) == pytest.approx(
        deliberate._weight(written, now) * 0.3, abs=1e-4
    )


# -- the endpoint --------------------------------------------------------------------


def test_the_upload_asks_who_was_who_first(team, client):
    client.force_login(team.ada)
    response = client.post(
        "/api/ambient/transcripts/",
        {"text": VTT, "project": str(team.project.pk), "title": "Imaging sync"},
    )
    body = response.json()
    assert body["labels"] == ["Ada", "Bo", "Guest"]
    assert {m["id"] for m in body["members"]} == {team.ada.pk, team.bo.pk}
    assert not TranscriptMeeting.objects.exists()


def test_the_upload_reads_it_in_with_a_mapping(team, client):
    client.force_login(team.ada)
    response = client.post(
        "/api/ambient/transcripts/",
        {
            "text": VTT,
            "project": str(team.project.pk),
            "title": "Imaging sync",
            "occurred_at": MET.isoformat(),
            "speakers": json.dumps({"Ada": team.ada.pk}),
        },
    )
    assert response.status_code == 201, response.content
    assert response.json()["counts"]["stored"] == 1


def test_the_upload_is_closed_while_off(team, client, settings):
    settings.AMBIENT_TRANSCRIPTS_ENABLED = False
    client.force_login(team.ada)
    response = client.post("/api/ambient/transcripts/", {"text": VTT})
    assert response.status_code == 403
