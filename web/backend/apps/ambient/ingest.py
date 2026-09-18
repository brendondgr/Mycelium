"""Recording one message: the only way anything enters the ledger.

The order of operations here is the product promise, so it is worth stating
plainly:

1. **Resolve eligibility first.** Before a body is held anywhere, before a row
   is written, before an id is logged. A message from somebody without a
   linked, paid, opted-in account is discarded here and leaves nothing behind
   — not an observation, not a reference, not a counter keyed to them.
2. **Hash, then buffer, then reference.** The content hash is computed from the
   text in memory and the normalised string is dropped immediately. The body
   goes to Redis under a TTL. Postgres gets the id, the time, the place and the
   hash — never the body.
3. **Repeats collapse.** A message whose hash the same speaker already sent
   inside ``AMBIENT_REPEAT_WINDOW_DAYS`` points at that earlier message and
   counts as one piece of evidence.

Nothing here extracts, attributes, or decides anything. It records that
something was said, by somebody Mycelium is allowed to listen to, and holds the
words just long enough for Plan 04 to read them once.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.utils import timezone

from . import buffer
from .eligibility import observable
from .models import PlaceKind, RawMessageRef, Source, SpeakerKind
from .text import content_hash

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IncomingMessage:
    """One message as an adapter hands it over, platform-independent.

    ``speaker`` is the resolved Mycelium user, or None — either because the
    sender has no linked account (in which case the message is discarded) or
    because the sender is Mylo itself (``speaker_kind = mylo``).
    """

    external_id: str
    text: str
    sent_at: object  # an aware datetime
    place_kind: str = PlaceKind.CHANNEL
    place_id: str = ""
    place_label: str = ""
    speaker: User | None = None
    speaker_external_id: str = ""
    speaker_kind: str = SpeakerKind.LINKED
    attachment_urls: list[str] = field(default_factory=list)
    edited_at: object | None = None
    # The person deliberately told Mylo rather than being overheard.
    explicit: bool = False
    # Other people the message named. ``mentions_count`` is everybody; the ids
    # are only of mentioned people who have opted in themselves — anybody else
    # is at most a number.
    mentions_count: int = 0
    mentioned_user_ids: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class Recorded:
    """What recording one message did, so a caller can count without guessing."""

    stored: bool
    reason: str = ""
    ref: RawMessageRef | None = None
    buffered: bool = False
    repeat: bool = False


def _repeat_window_start():
    days = int(getattr(settings, "AMBIENT_REPEAT_WINDOW_DAYS", 30))
    return timezone.now() - timedelta(days=days)


def find_repeat_root(
    speaker: User, digest: str, *, before=None
) -> RawMessageRef | None:
    """The earliest live message from ``speaker`` with the same hash, if any.

    Repeats chain to the root rather than to the previous copy, so counting
    evidence never has to walk a chain. Deleted references are excluded: a
    message whose original was removed is a new first, not a repeat of nothing.
    """
    if not digest or speaker is None:
        return None
    candidates = RawMessageRef.objects.filter(
        speaker=speaker,
        content_hash=digest,
        deleted_at__isnull=True,
        sent_at__gte=_repeat_window_start(),
    )
    if before is not None:
        candidates = candidates.filter(sent_at__lte=before)
    root = candidates.filter(repeat_of__isnull=True).order_by("sent_at", "pk").first()
    if root is not None:
        return root
    # Every copy in the window is itself a repeat — follow one to its root.
    child = candidates.order_by("sent_at", "pk").first()
    return child.repeat_of if child is not None else None


def record(source: Source, message: IncomingMessage) -> Recorded:
    """Record one message, or refuse it. The single entry point to the ledger."""
    is_mylo = message.speaker_kind == SpeakerKind.MYLO
    if not is_mylo:
        verdict = observable(message.speaker, source)
        if not verdict:
            # Nothing is written and nothing is retained. The counter below is
            # keyed on the reason, never on the person.
            logger.debug("ambient: discarded a message (%s)", verdict.reason)
            return Recorded(False, verdict.reason)
    elif not source.listening:
        return Recorded(False, "source_not_consented")

    digest = content_hash(message.text)
    repeat_root = (
        None
        if is_mylo
        else find_repeat_root(message.speaker, digest, before=message.sent_at)
    )

    ttl = buffer.ttl_seconds(source)
    held = False
    if message.text:
        held = buffer.put(source.pk, message.external_id, message.text, ttl=ttl)

    try:
        with transaction.atomic():
            ref = RawMessageRef.objects.create(
                source=source,
                external_id=message.external_id,
                place_kind=message.place_kind,
                place_id=message.place_id,
                place_label=message.place_label,
                speaker=None if is_mylo else message.speaker,
                speaker_kind=message.speaker_kind,
                speaker_external_id=message.speaker_external_id,
                sent_at=message.sent_at,
                buffered_until=(
                    timezone.now() + timedelta(seconds=ttl) if held else None
                ),
                content_hash=digest,
                repeat_of=repeat_root,
                attachment_urls=list(message.attachment_urls),
                edited_at=message.edited_at,
                explicit=bool(message.explicit),
                mentions_count=max(0, int(message.mentions_count or 0)),
                mentioned_user_ids=[int(one) for one in message.mentioned_user_ids],
            )
    except IntegrityError:
        # The same message arriving twice — a gateway resume, a retried handoff.
        # The buffer write above is idempotent, so the existing row stands.
        existing = RawMessageRef.objects.filter(
            source=source, external_id=message.external_id
        ).first()
        return Recorded(
            False, "already_recorded", ref=existing, buffered=held, repeat=False
        )

    if not is_mylo:
        _attribute_on_arrival(ref, message.text)

    return Recorded(
        True, ref=ref, buffered=held, repeat=repeat_root is not None
    )


def _attribute_on_arrival(ref: RawMessageRef, text: str) -> None:
    """Decide which project this is about while the text is still in memory.

    Every signal used here is a cheap lookup, and no model is called, so this is
    bookkeeping rather than evaluation. A failure is logged and leaves the
    message unresolved — it never costs the message itself, which is already
    recorded; the nightly read gets another chance at it.
    """
    from .attribution import attribute_ref

    try:
        attribute_ref(ref, text)
    except Exception:  # pragma: no cover - attribution must never lose a message
        logger.exception("ambient: could not attribute message %s", ref.pk)
