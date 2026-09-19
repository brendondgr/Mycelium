"""The adapter contract: how a platform gets its conversation into the ledger.

An adapter's whole job is translation. It turns whatever its platform sends
into a :class:`PlatformEvent`, and it turns a platform identity into a Mycelium
user. That is all it does.

In particular an adapter does **not**:

* extract anything — no understanding kind, no force, no summary (Plan 04);
* attribute anything — no project, no confidence (Plan 03);
* decide who may be listened to — :mod:`~apps.ambient.eligibility` does, and
  :func:`~apps.ambient.ingest.record` calls it before anything is held;
* keep any message text of its own.

Writing the interface here, with a fake adapter behind it, is what keeps Discord
from becoming the design. Slack, Teams and transcripts are later adapters over
this same shape, not later special cases.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from django.contrib.auth.models import User

from ..ingest import IncomingMessage, Recorded, record
from ..models import PlaceKind, Source, SpeakerKind


@dataclass(frozen=True)
class PlatformEvent:
    """One message as a platform reports it, before Mycelium knows anything.

    ``author_external_id`` is the platform's own id for the sender — a Discord
    snowflake, a Slack user id. It is not yet a Mycelium user and may never
    become one, which is the normal case for most people in a server.
    """

    source_external_id: str
    message_external_id: str
    text: str
    sent_at: object  # an aware datetime
    author_external_id: str
    place_kind: str = PlaceKind.CHANNEL
    place_id: str = ""
    place_label: str = ""
    attachment_urls: list[str] = field(default_factory=list)
    edited_at: object | None = None
    # The person addressed Mylo directly — a DM, an @mention, a note command,
    # the message action, a reaction on Mylo's own post.
    explicit: bool = False
    # Platform ids of the people the message names. Resolved by the adapter;
    # only those who have opted in themselves are kept as ids.
    mention_external_ids: list[str] = field(default_factory=list)
    # True when the sender is Mylo itself. Its messages are buffered so a window
    # reads coherently — a question Mylo asked is what makes the next line an
    # answer — and are never evidence.
    from_mylo: bool = False
    # The platform id of the message this one replies to, if any. A reply to
    # Mylo is engagement, not independent interest (Plan 04, step 5).
    reply_to_external_id: str = ""


class Adapter(ABC):
    """Base class for every platform adapter.

    Subclasses supply three things: which platform they speak for, which
    :class:`~apps.ambient.models.Source` kind their surfaces are, and how to
    turn one of their platform identities into a Mycelium user. The delivery
    path itself is shared, so every platform enters the ledger through exactly
    one door.
    """

    #: The :class:`~apps.ambient.models.Platform` this adapter speaks for.
    platform: str
    #: The :class:`~apps.ambient.models.Source.Kind` its surfaces are recorded as.
    source_kind: str

    @abstractmethod
    def resolve_speaker(self, author_external_id: str) -> User | None:
        """The Mycelium user behind a platform id, or None.

        None is the ordinary answer: most people in a server have no Mycelium
        account, and nothing about them is recorded. An adapter must never
        invent a placeholder user to make a message ingestible.
        """

    def source_for(self, source_external_id: str) -> Source | None:
        """The connected surface this event came from, or None if there is none.

        A surface nobody connected is not listened to. Adapters override this
        only when their surfaces are keyed unusually.
        """
        return Source.objects.filter(
            kind=self.source_kind, external_id=source_external_id
        ).first()

    def resolve_mentions(self, event: PlatformEvent) -> tuple[int, list[int]]:
        """``(count, ids)`` for the people a message names.

        The count is everybody named other than the speaker. The ids are only
        of people who have opted in on this platform themselves — a mention of
        somebody who never agreed to any of this is recorded as a number and
        nothing more.
        """
        from ..eligibility import person_opted_in

        others = [
            one
            for one in dict.fromkeys(str(x) for x in event.mention_external_ids)
            if one and one != str(event.author_external_id)
        ]
        ids: list[int] = []
        for external_id in others:
            user = self.resolve_speaker(external_id)
            if user is not None and person_opted_in(user, self.platform):
                ids.append(user.pk)
        return len(others), ids

    def to_message(self, event: PlatformEvent, speaker: User | None) -> IncomingMessage:
        """The platform-independent shape. Pure translation, no judgement."""
        count, ids = (0, []) if event.from_mylo else self.resolve_mentions(event)
        return IncomingMessage(
            external_id=event.message_external_id,
            text=event.text,
            sent_at=event.sent_at,
            place_kind=event.place_kind,
            place_id=event.place_id,
            place_label=event.place_label,
            speaker=None if event.from_mylo else speaker,
            speaker_external_id=event.author_external_id,
            speaker_kind=SpeakerKind.MYLO if event.from_mylo else SpeakerKind.LINKED,
            attachment_urls=list(event.attachment_urls),
            edited_at=event.edited_at,
            explicit=bool(event.explicit),
            mentions_count=count,
            mentioned_user_ids=ids,
            reply_to_external_id=str(event.reply_to_external_id or ""),
        )

    def deliver(self, event: PlatformEvent) -> Recorded:
        """Translate one event and hand it to the ledger. The only way in."""
        source = self.source_for(event.source_external_id)
        if source is None:
            return Recorded(False, "unknown_source")
        speaker = (
            None if event.from_mylo else self.resolve_speaker(event.author_external_id)
        )
        return record(source, self.to_message(event, speaker))
