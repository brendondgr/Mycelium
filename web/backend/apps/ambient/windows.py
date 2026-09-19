"""Which conversations are ready to be read, and what they say (Plan 04).

A **window** is one conversation in one place: consecutive messages in a
channel, a thread, or a DM, broken wherever the place went quiet for
``AMBIENT_WINDOW_QUIET_MINUTES``, and capped at ``AMBIENT_WINDOW_HOURS`` and
``AMBIENT_WINDOW_MAX_MESSAGES``. Attribution (Plan 03) has already decided which
project each message is about; a window is only about *when* to read.

**Read within the buffer's TTL.** Message bodies live for hours
(``AMBIENT_RAW_TTL_HOURS``), so the reading happens through the day rather than
once a night (decision 2026-09-19, option C): a window is ready once its place
has gone quiet, once it has hit its cap, or once its oldest body is within an
hour of expiring. The *deciding* — what the observations mean for anybody —
still happens once, at night (:mod:`.deliberate`).

Nothing here calls a model. :func:`ready` is a query; :func:`assemble` pairs the
references with whatever bodies are still alive, re-checking every speaker's
eligibility first, exactly as :func:`apps.ambient.read.window` does.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from . import buffer
from .models import RawMessageRef, Source, SpeakerKind

#: A body this close to expiring is read now rather than lost.
EXPIRY_MARGIN = timedelta(hours=1)
#: The Discord cog records a reaction on Mylo's post under this id prefix.
REACTION_PREFIX = "reaction:"


@dataclass(frozen=True)
class Spec:
    """A conversation that is ready: which references, and where."""

    source_id: int
    place_id: str
    ref_ids: tuple[int, ...]
    since: object
    until: object
    key: str


@dataclass(frozen=True)
class Line:
    """One message as the extractor sees it. ``text`` is None once expired."""

    ref_id: int
    external_id: str
    sent_at: object
    place_kind: str
    place_label: str
    place_id: str
    speaker_id: int | None
    from_mylo: bool
    text: str | None
    explicit: bool
    # Engagement with something Mylo said — a reply to it, a reaction on it.
    # Carried so the conversation reads coherently; never evidence.
    engagement: bool
    mentions_count: int
    project_id: str | None
    lab_id: int | None


@dataclass
class Conversation:
    """An assembled window, ready for the extractor."""

    spec: Spec
    source: Source
    lines: list[Line] = field(default_factory=list)

    @property
    def source_id(self) -> int:
        return self.source.pk

    @property
    def readable(self) -> list[Line]:
        return [line for line in self.lines if line.text is not None]

    @property
    def evidence(self) -> list[Line]:
        """The lines a statement may be grounded in: a person's own, alive,
        and not engagement with Mylo."""
        return [
            line
            for line in self.readable
            if not line.from_mylo and not line.engagement and line.speaker_id
        ]

    def content_hash(self) -> str:
        """What the window says, as a key: an unchanged window is never read
        twice. Built from ids and each body's own hash, never from text."""
        digest = hashlib.sha256()
        for line in self.lines:
            digest.update(line.external_id.encode())
            digest.update(b"\0")
            digest.update(
                hashlib.sha256((line.text or "").encode()).hexdigest().encode()
            )
            digest.update(b"\n")
        return digest.hexdigest()


def _quiet() -> timedelta:
    return timedelta(minutes=int(settings.AMBIENT_WINDOW_QUIET_MINUTES))


def _span() -> timedelta:
    return timedelta(hours=int(settings.AMBIENT_WINDOW_HOURS))


def _cap() -> int:
    return max(2, int(settings.AMBIENT_WINDOW_MAX_MESSAGES))


def _key(source_id: int, place_id: str, first: RawMessageRef) -> str:
    return f"{source_id}:{place_id or 'dm'}:{first.sent_at:%Y%m%dT%H%M}:{first.pk}"


def _chunks(refs: list[RawMessageRef]) -> list[list[RawMessageRef]]:
    """Split one place's unread messages into conversations."""
    chunks: list[list[RawMessageRef]] = []
    for ref in refs:
        current = chunks[-1] if chunks else None
        if (
            current is None
            or ref.sent_at - current[-1].sent_at > _quiet()
            or ref.sent_at - current[0].sent_at > _span()
            or len(current) >= _cap()
        ):
            chunks.append([ref])
        else:
            current.append(ref)
    return chunks


def ready(*, now=None, sources=None) -> list[Spec]:
    """Every conversation that should be read now, oldest first.

    The last conversation in a place is still going unless it has been quiet
    for the quiet period, reached its cap, or has a body about to expire; every
    earlier one is closed by definition.
    """
    now = now or timezone.now()
    rows = RawMessageRef.objects.filter(
        read_at__isnull=True, deleted_at__isnull=True
    ).order_by("source_id", "place_id", "sent_at", "pk")
    if sources is not None:
        rows = rows.filter(source__in=list(sources))
    by_place: dict[tuple[int, str], list[RawMessageRef]] = {}
    for ref in rows:
        by_place.setdefault((ref.source_id, ref.place_id), []).append(ref)

    specs: list[Spec] = []
    for (source_id, place_id), refs in by_place.items():
        chunks = _chunks(refs)
        for index, chunk in enumerate(chunks):
            last = index == len(chunks) - 1
            expiring = any(
                ref.buffered_until is not None
                and ref.buffered_until - now <= EXPIRY_MARGIN
                for ref in chunk
            )
            if last and not (
                now - chunk[-1].sent_at >= _quiet()
                or len(chunk) >= _cap()
                or chunk[-1].sent_at - chunk[0].sent_at >= _span()
                or expiring
            ):
                continue
            specs.append(
                Spec(
                    source_id=source_id,
                    place_id=place_id,
                    ref_ids=tuple(ref.pk for ref in chunk),
                    since=chunk[0].sent_at,
                    until=chunk[-1].sent_at,
                    key=_key(source_id, place_id, chunk[0]),
                )
            )
    specs.sort(key=lambda spec: spec.since)
    return specs


def assemble(spec: Spec) -> Conversation | None:
    """Pair a ready conversation's references with the bodies still alive.

    Every speaker is re-checked first: somebody who opted out, unlinked, or
    lapsed since their message arrived has it discarded here, before anything
    is read (:func:`apps.ambient.reconcile.drop_ineligible`).
    """
    from .reconcile import drop_ineligible

    source = Source.objects.filter(pk=spec.source_id).select_related("lab").first()
    if source is None:
        return None

    def _refs():
        return list(
            RawMessageRef.objects.filter(
                pk__in=spec.ref_ids, deleted_at__isnull=True
            ).order_by("sent_at", "pk")
        )

    refs = _refs()
    if drop_ineligible(source, refs):
        refs = _refs()
    bodies = buffer.get_many(source.pk, [ref.external_id for ref in refs])
    mylo_ids = set(
        RawMessageRef.objects.filter(
            source=source,
            speaker_kind=SpeakerKind.MYLO,
            external_id__in=[
                r.reply_to_external_id for r in refs if r.reply_to_external_id
            ],
        ).values_list("external_id", flat=True)
    )
    lines = [
        Line(
            ref_id=ref.pk,
            external_id=ref.external_id,
            sent_at=ref.sent_at,
            place_kind=ref.place_kind,
            place_label=ref.place_label,
            place_id=ref.place_id,
            speaker_id=ref.speaker_id,
            from_mylo=ref.speaker_kind == SpeakerKind.MYLO,
            text=bodies.get(ref.external_id),
            explicit=ref.explicit,
            engagement=(
                ref.external_id.startswith(REACTION_PREFIX)
                or (
                    bool(ref.reply_to_external_id)
                    and ref.reply_to_external_id in mylo_ids
                )
            ),
            mentions_count=ref.mentions_count,
            project_id=str(ref.project_id) if ref.project_id else None,
            lab_id=source.lab_id,
        )
        for ref in refs
    ]
    return Conversation(spec=spec, source=source, lines=lines)


def mark_read(conversation: Conversation, *, now=None) -> None:
    """The conversation has been read: stamp it and delete the bodies now.

    Called whatever the extractor made of it — a window that yielded nothing
    has still been read, and holding its text any longer would serve nobody.
    The one exception is the model being unreachable, where the caller leaves
    the window unread so the next hour can try again within the TTL.
    """
    now = now or timezone.now()
    RawMessageRef.objects.filter(pk__in=conversation.spec.ref_ids).update(
        read_at=now, buffered_until=None
    )
    buffer.drop(
        conversation.source.pk, [line.external_id for line in conversation.lines]
    )
