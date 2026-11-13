"""Mylo chat (the agent tool): a person's own messages to Mylo in the app.

The agent tool never calls this module (the platform imports no tool, and a
tool's import of it would be fine but is not needed): it publishes
``agent.thread_quiet`` with the person's own messages, and
:func:`on_thread_quiet` — subscribed in ``AmbientConfig.ready`` — hands them
to the ledger here. Only the person's words arrive: Mylo's replies, function
results and paper text never do, so Mylo cannot learn from its own guesses
or from what it read.

Every message is explicit (the person chose to say it to Mylo), so it carries
the "told" weight in deliberation, and still goes through confirmation before
it changes anything. The source is the person (like a Discord DM): what they
say in a chat is personal evidence, never a lab's.
"""

from __future__ import annotations

import logging

from django.contrib.auth.models import User
from django.utils.dateparse import parse_datetime

from ..models import PlaceKind, Platform, Source
from .base import Adapter, PlatformEvent

logger = logging.getLogger(__name__)


class AgentChatAdapter(Adapter):
    platform = Platform.AGENT_CHAT
    source_kind = Source.Kind.AGENT_CHAT

    def resolve_speaker(self, author_external_id: str) -> User | None:
        prefix, _, pk = str(author_external_id).partition(":")
        if prefix != "user" or not pk.isdigit():
            return None
        return User.objects.filter(pk=int(pk), is_active=True).first()


_ADAPTER = AgentChatAdapter()


def source_for_user(user_id: int) -> Source:
    source, _ = Source.objects.get_or_create(
        kind=Source.Kind.AGENT_CHAT,
        external_id=f"user:{user_id}",
        defaults={"consent_state": Source.Consent.ACTIVE, "label": "Mylo chat"},
    )
    return source


def on_thread_quiet(*, thread_id, user_id, messages, title="", **_ignored) -> int:
    """Record a quiet thread's new messages. Returns how many were stored.

    Raises only on an unexpected failure, so the agent's pass backs off and
    retries; a message refused by eligibility (opted out, free tier, the
    switch off) is simply not recorded.
    """
    source_for_user(user_id)
    stored = 0
    for message in messages:
        sent_at = parse_datetime(str(message.get("ts", "")))
        outcome = _ADAPTER.deliver(
            PlatformEvent(
                source_external_id=f"user:{user_id}",
                message_external_id=f"{thread_id}:{message['seq']}",
                text=str(message.get("text", ""))[:4000],
                sent_at=sent_at,
                author_external_id=f"user:{user_id}",
                place_kind=PlaceKind.DM,
                place_id=str(thread_id),
                place_label=str(title or "Mylo chat")[:120],
                explicit=True,
            )
        )
        if outcome.stored:
            stored += 1
    return stored


def on_thread_deleted(*, thread_id, user_id, **_ignored) -> int:
    """The person deleted a Mylo chat: retract every message of it the ledger
    recorded, as if each had been deleted on a platform. Returns how many."""
    from ..models import RawMessageRef
    from ..reconcile import message_deleted

    source = Source.objects.filter(
        kind=Source.Kind.AGENT_CHAT, external_id=f"user:{user_id}"
    ).first()
    if source is None:
        return 0
    ids = list(
        RawMessageRef.objects.filter(
            source=source,
            external_id__startswith=f"{thread_id}:",
            deleted_at__isnull=True,
        ).values_list("external_id", flat=True)
    )
    for external_id in ids:
        message_deleted(source, external_id)
    return len(ids)
