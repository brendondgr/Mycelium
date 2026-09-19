"""The read API — the only door into the ledger from outside this app.

Every later stage reads through here: Plan 03 attributes, Plan 04 extracts and
deliberates, Plan 05 keeps the evolving profile, Plan 06 asks, Plan 09 reports.
``apps.content`` imports **this module and nothing else** from ``ambient``, and
an import-graph test enforces it, so the ledger's internals — the buffer, the
consent tables, the reconciliation paths — stay free to change without the
matching layer noticing.

The window is the interesting shape here. Assembling one asks Postgres *which*
messages fall in a range and Redis for whatever bodies are still alive. A body
that expired simply is not there, and :attr:`Window.complete` says so plainly
rather than pretending. After a caller has read a window it calls
:func:`release`, which deletes those bodies immediately — reading is what the
buffer exists for, and it has no reason to hold them afterwards.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.contrib.auth.models import User
from django.utils import timezone

from . import buffer
from .eligibility import person_opted_in, questions_muted
from .models import (
    Observation,
    ObservationFeedback,
    RawMessageRef,
    Retraction,
    Source,
    SpeakerKind,
    Visibility,
)

__all__ = [
    "Window",
    "WindowMessage",
    "window",
    "release",
    "observations_for",
    "project_evidence",
    "lab_evidence",
    "feedback_for",
    "pending_retractions",
    "mark_recomputed",
    "listening_enabled",
    "questions_muted",
    "active_sources",
    "listening_totals",
    "attention_for",
    "developments_in_effect",
]


@dataclass(frozen=True)
class WindowMessage:
    """One message in a window. ``text`` is None when its body has expired."""

    external_id: str
    sent_at: object
    place_kind: str
    place_label: str
    place_id: str
    speaker_id: int | None
    speaker_kind: str
    text: str | None
    is_repeat: bool

    @property
    def from_mylo(self) -> bool:
        """Mylo's own line. Present so the window reads coherently; never
        evidence — Plan 04 excludes these at extraction."""
        return self.speaker_kind == SpeakerKind.MYLO


@dataclass(frozen=True)
class Window:
    """A stretch of one surface's conversation, as much of it as still exists."""

    source_id: int
    since: object
    until: object
    messages: list[WindowMessage]

    def __len__(self) -> int:
        return len(self.messages)

    @property
    def readable(self) -> list[WindowMessage]:
        """The messages whose bodies are still alive."""
        return [message for message in self.messages if message.text is not None]

    @property
    def complete(self) -> bool:
        """Whether every message in the range still has its body.

        A short window is normal — it is a TTL doing its job — and a caller that
        needs to know it read a partial conversation should ask, rather than
        find out from a thin extraction.
        """
        return len(self.readable) == len(self.messages)

    def external_ids(self) -> list[str]:
        return [message.external_id for message in self.messages]


def window(source: Source, since, until=None, *, revalidate: bool = True) -> Window:
    """Assemble one window of conversation from a surface.

    Deleted messages are left out entirely: a tombstoned reference means the
    person took the message back, and a window is not the place to resurrect it.

    With ``revalidate`` (the default) every speaker is checked again first, and
    anybody who is no longer eligible — opted out, unlinked, lapsed since the
    message arrived — has their messages discarded before the window is built.
    It is the read boundary that enforces this, so no caller can forget to.
    """
    from .reconcile import drop_ineligible

    until = until or timezone.now()

    def _refs():
        return list(
            RawMessageRef.objects.filter(
                source=source,
                sent_at__gte=since,
                sent_at__lte=until,
                deleted_at__isnull=True,
            )
            .select_related("speaker")
            .order_by("sent_at", "pk")
        )

    refs = _refs()
    if revalidate and drop_ineligible(source, refs):
        refs = _refs()
    bodies = buffer.get_many(source.pk, [ref.external_id for ref in refs])
    return Window(
        source_id=source.pk,
        since=since,
        until=until,
        messages=[
            WindowMessage(
                external_id=ref.external_id,
                sent_at=ref.sent_at,
                place_kind=ref.place_kind,
                place_label=ref.place_label,
                place_id=ref.place_id,
                speaker_id=ref.speaker_id,
                speaker_kind=ref.speaker_kind,
                text=bodies.get(ref.external_id),
                is_repeat=ref.repeat_of_id is not None,
            )
            for ref in refs
        ],
    )


def release(window_: Window) -> None:
    """Delete the bodies a window held, now that it has been read.

    This is the primary deletion path for raw text. The TTL is only for the
    windows this is never called on.
    """
    buffer.drop(window_.source_id, window_.external_ids())


def observations_for(
    user: User,
    *,
    kinds=None,
    since=None,
    status=Observation.Status.ACTIVE,
    visibility=None,
):
    """What Mylo understood about one person, newest first."""
    rows = Observation.objects.filter(speaker=user)
    if status is not None:
        rows = rows.filter(status=status)
    if kinds:
        rows = rows.filter(understanding_kind__in=list(kinds))
    if since is not None:
        rows = rows.filter(observed_at__gte=since)
    if visibility is not None:
        rows = rows.filter(visibility=visibility)
    return rows


def project_evidence(project, *, since=None, status=Observation.Status.ACTIVE):
    """What Mylo understood about one project."""
    rows = Observation.objects.filter(project=project)
    if status is not None:
        rows = rows.filter(status=status)
    if since is not None:
        rows = rows.filter(observed_at__gte=since)
    return rows


def lab_evidence(lab, *, since=None):
    """Lab-visible observations from a lab's surfaces.

    Filtered on visibility in the query rather than in the caller: a private
    career aspiration must never reach a lab packet, and a rule enforced at the
    read boundary cannot be forgotten by one call site.
    """
    rows = Observation.objects.filter(
        source__lab=lab,
        visibility=Visibility.LAB,
        status=Observation.Status.ACTIVE,
    )
    if since is not None:
        rows = rows.filter(observed_at__gte=since)
    return rows


def feedback_for(observation):
    """Every verdict on an observation, newest first."""
    return ObservationFeedback.objects.filter(observation=observation)


def pending_retractions():
    """Retractions whose influence has not been taken back out yet."""
    return Retraction.objects.filter(recomputed_at__isnull=True)


def mark_recomputed(retraction: Retraction) -> Retraction:
    """Record that a retraction's downstream recompute has happened."""
    retraction.recomputed_at = timezone.now()
    retraction.save(update_fields=["recomputed_at"])
    return retraction


def listening_enabled(user: User, platform: str) -> bool:
    """Whether this person turned listening on for this platform."""
    return person_opted_in(user, platform)


def listening_totals(day=None) -> dict:
    """What every listening surface produced on one day, summed.

    Counts only — this is the shape the run-analytics report reads, and a
    report about how much was heard must not become a report about who was
    heard. Nothing here is keyed to a person, because nothing upstream is.
    """
    from django.db.models import Sum

    from .models import SourceActivity

    when = day or timezone.localdate()
    fields = [
        "heard",
        "stored",
        "dropped_not_opted_in",
        "dropped_unlinked",
        "dropped_free_tier",
        "dropped_excluded_channel",
        "dropped_too_short",
        "dropped_bot",
        "dropped_lapsed",
        "dropped_other",
    ]
    totals = SourceActivity.objects.filter(day=when).aggregate(
        **{name: Sum(name) for name in fields}
    )
    result = {name: int(totals.get(name) or 0) for name in fields}
    result["sources_listening"] = Source.objects.filter(
        consent_state=Source.Consent.ACTIVE
    ).count()
    result["sources_active_today"] = SourceActivity.objects.filter(
        day=when, heard__gt=0
    ).count()
    return result


def active_sources(*, lab=None):
    """Surfaces currently consented to be listened to."""
    rows = Source.objects.filter(consent_state=Source.Consent.ACTIVE)
    if lab is not None:
        rows = rows.filter(lab=lab)
    return rows


def attention_for(user):
    """Where this person's attributed conversation went, 7- and 28-day shares.

    Personal: it describes one person and is for that person's reports.
    """
    from .models import ProjectAttention

    return ProjectAttention.objects.filter(user=user).select_related("project")


def developments_in_effect(project, *, reader=None, changes=None):
    """A project's developments that change something: told, or confirmed.

    Lab-visible ones for anybody who can see the project. A personal one — a
    fact somebody told Mylo in a DM — only for the ``reader`` who said it, so
    a lab report never learns what one member said privately.
    """
    from django.db.models import Q

    from .models import ProjectDevelopment

    visible = Q(visibility=Visibility.LAB)
    if reader is not None:
        visible |= Q(visibility=Visibility.PERSONAL, speaker=reader)
    rows = ProjectDevelopment.objects.filter(
        project=project,
        status__in=[
            ProjectDevelopment.Status.ACTIVE,
            ProjectDevelopment.Status.CONFIRMED,
        ],
    ).filter(visible)
    if changes:
        rows = rows.filter(change__in=list(changes))
    return rows
