"""Meeting transcripts: one meeting, one window (ambient Plan 11, steps 9–12).

A person uploads a meeting's transcript for a project or a lab they belong
to. Uploading is the per-meeting consent, and the source it creates carries
it. Then:

- the transcript is parsed into turns: WebVTT (``<v Name>`` or ``Name:`` cues),
  SRT, or plain ``Name: text`` lines;
- the uploader maps each speaker label to a member of the meeting's lab or
  project. A label mapped to anyone else, or to nobody, is dropped before the
  buffer, and so are the turns of anyone not opted in to transcripts or on a
  free tier: :func:`~.ingest.record` checks each one like any message;
- the kept turns sit in the buffer for ``AMBIENT_TRANSCRIPT_TTL_HOURS`` and are
  read at the next hourly read. The reading keeps only project developments,
  at ``AMBIENT_TRANSCRIPT_WEIGHT`` of their usual weight;
- the participants are told on the bell (``read.transcripts_to_announce``).

Nothing here stores a line of the transcript outside the buffer.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from . import filters
from .adapters.base import PlatformEvent
from .adapters.transcript import TranscriptAdapter
from .eligibility import ambient_enabled
from .models import ChannelHint, PlaceKind, Source, TranscriptMeeting

_ADAPTER = TranscriptAdapter()

_CUE_TIME = re.compile(
    r"(?:(\d{1,2}):)?(\d{1,2}):(\d{2})(?:[.,](\d{1,3}))?\s*-->\s*[\d:.,]+"
)
_VOICE = re.compile(r"^<v\s+([^>]+)>(.*?)(?:</v>)?$", re.I)
_SPOKEN = re.compile(
    r"^(?:\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?\s+)?([^:\[\]]{1,60}):\s+(.+)$"
)


@dataclass(frozen=True)
class Turn:
    label: str
    text: str
    offset_seconds: float


def _seconds(h, m, s, ms) -> float:
    return int(h or 0) * 3600 + int(m) * 60 + int(s) + int(ms or 0) / 1000


def _clock(text: str) -> float:
    parts = [int(p) for p in text.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def parse(text: str) -> list[Turn]:
    """Turns, in order. Unlabelled lines join the previous speaker's turn."""
    turns: list[Turn] = []
    offset = 0.0
    for raw in (text or "").replace("\r", "").split("\n"):
        line = raw.strip()
        if not line or line.upper() == "WEBVTT" or line.isdigit():
            continue
        cue = _CUE_TIME.search(line)
        if cue:
            offset = _seconds(*cue.groups())
            continue
        voice = _VOICE.match(line)
        spoken = _SPOKEN.match(line) if voice is None else None
        if voice:
            label, words = voice.group(1).strip(), voice.group(2).strip()
        elif spoken:
            if spoken.group(1):
                offset = _clock(spoken.group(1))
            label, words = spoken.group(2).strip(), spoken.group(3).strip()
        elif turns:
            last = turns[-1]
            turns[-1] = Turn(last.label, f"{last.text} {line}", last.offset_seconds)
            continue
        else:
            continue
        if turns and turns[-1].label == label:
            last = turns[-1]
            turns[-1] = Turn(label, f"{last.text} {words}", last.offset_seconds)
        else:
            turns.append(Turn(label, words, offset))
    return turns


def labels(text: str) -> list[str]:
    """The distinct speaker labels, in order of first appearance."""
    return list(dict.fromkeys(turn.label for turn in parse(text)))


class TranscriptRefused(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def members_of(*, project=None, lab=None) -> set[int]:
    """Who may be named as a speaker: the project's members (and owner), or
    the lab's members."""
    from apps.accounts.models import LabMembership

    ids: set[int] = set()
    if project is not None:
        ids |= set(project.members.values_list("pk", flat=True))
        if project.scope_user_id:
            ids.add(project.scope_user_id)
        lab = lab or (project.scope_lab if project.scope_lab_id else None)
    if lab is not None and project is None:
        ids |= set(
            LabMembership.objects.filter(lab=lab).values_list("user_id", flat=True)
        )
    return ids


def ingest(
    organiser,
    *,
    title: str,
    occurred_at,
    text: str,
    speakers: dict,
    project=None,
    lab=None,
) -> TranscriptMeeting:
    """Read a transcript into the buffer. ``speakers`` maps each label to a
    user id (or to nothing). Raises :class:`TranscriptRefused` when the
    feature is off or the organiser does not belong to the meeting."""
    if not (
        ambient_enabled() and getattr(settings, "AMBIENT_TRANSCRIPTS_ENABLED", False)
    ):
        raise TranscriptRefused("transcripts_disabled")
    if project is None and lab is None:
        raise TranscriptRefused("no_project_or_lab")
    allowed = members_of(project=project, lab=lab)
    if organiser.pk not in allowed:
        raise TranscriptRefused("organiser_not_a_member")
    lab = lab or (project.scope_lab if project and project.scope_lab_id else None)

    counts = {"stored": 0, "unmapped": 0, "not_a_member": 0}
    participants: set[int] = set()
    turns = parse(text)
    with transaction.atomic():
        source = Source.objects.create(
            kind=Source.Kind.TRANSCRIPT,
            external_id=f"meeting:{uuid.uuid4()}",
            lab=lab,
            label=title[:120],
            consent_state=Source.Consent.ACTIVE,
            consent_changed_at=timezone.now(),
            consent_changed_by=organiser,
            raw_ttl_hours=int(settings.AMBIENT_TRANSCRIPT_TTL_HOURS),
        )
        meeting = TranscriptMeeting.objects.create(
            source=source,
            organiser=organiser,
            lab=lab,
            project=project,
            title=title[:200],
            occurred_at=occurred_at,
            turns=len(turns),
        )
        if project is not None:
            # The meeting is about its project: attribution's channel hint.
            ChannelHint.objects.create(
                source=source,
                place_id=str(meeting.pk),
                place_label=title[:120],
                project=project,
                set_by=organiser,
            )
    for index, turn in enumerate(turns):
        user_id = speakers.get(turn.label)
        if not user_id:
            counts["unmapped"] += 1
            continue
        if int(user_id) not in allowed:
            counts["not_a_member"] += 1
            continue
        participants.add(int(user_id))
        outcome = _ADAPTER.deliver(
            PlatformEvent(
                source_external_id=source.external_id,
                message_external_id=f"turn-{index}",
                text=filters.truncate(turn.text),
                sent_at=occurred_at + timedelta(seconds=turn.offset_seconds),
                author_external_id=f"user:{int(user_id)}",
                place_kind=PlaceKind.TRANSCRIPT,
                place_id=str(meeting.pk),
                place_label=title[:120],
            )
        )
        key = "stored" if outcome.stored else outcome.reason
        counts[key] = counts.get(key, 0) + 1
    meeting.participant_ids = sorted(participants)
    meeting.counts = counts
    meeting.save(update_fields=["participant_ids", "counts"])
    return meeting


def keep_only_developments(observations: list) -> list:
    """What a transcript is allowed to yield (step 10): decisions, blockers
    and commitments — the project-development kind — and nothing about a
    person's interests, until Plan 10 shows speech is precise enough."""
    return [item for item in observations if item.kind == "project_development"]
