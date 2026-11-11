"""The Discord surface (plan D): who is asking, where, and which conversation.

The bot (``mylo/``) reaches this module through
``tools._framework.services.get("agent").discord_surface()`` and never imports
the agent. It only enqueues and watches: the turn runs in the Celery worker,
exactly as on the web.

``ask`` runs the Discord gate (``apps.integrations.services.gate``), resolves
the place (``resolve.place_for``), finds or opens the conversation through
``AgentThreadLink``, builds the ``Caller`` and calls ``service.send``. Every
"no" comes back as a :class:`Refusal` with a sentence ready to post. Nothing
here decides what anyone may see: that is the agent's gate.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import timedelta
from urllib.parse import quote

from django.db import IntegrityError, transaction
from django.utils import timezone

from .. import config, refs, service, store, stream
from ..caller import Audience, Caller, Guest, Scope, clean_name
from ..models import (
    AgentDiscordTurn,
    AgentEvent,
    AgentQueuedMessage,
    AgentThread,
    AgentThreadLink,
)

logger = logging.getLogger(__name__)

UNBOUND = "This server isn't set up for Mylo."
EMPTY = "What can I help with?"
NO_MODEL = "I can't answer right now: no language model is set up on this Mycelium."
AGENT_OFF = "Mylo chat isn't enabled on this Mycelium."
GUEST_LIMIT = (
    "You've asked me {cap} questions today. Ask again tomorrow, or connect your "
    "Discord to Mycelium."
)
PLACE_LIMIT = "This server has asked me {cap} questions today. Ask again tomorrow."
CONNECT_DM = (
    "To talk to me here, connect your Discord to an activated Mycelium account: "
    "open your profile in Mycelium and use **Connect Discord**, or run "
    "`/activate` with a code from there."
)
REPLY_HINT = "I can only read replies that ping me."


@dataclass(frozen=True)
class Refusal:
    code: str
    message: str

    def __bool__(self) -> bool:
        return False


@dataclass(frozen=True)
class Handle:
    """One question on its way to an answer (an ``AgentDiscordTurn``)."""

    turn_id: int
    thread_id: str
    link_id: int
    discord_user_id: str
    channel_id: str
    trigger_message_id: str
    status_message_id: str = ""
    user_event_seq: int = 0
    queued: bool = False
    guest: bool = False
    #: The first answer in this conversation (the model line shows on it).
    first: bool = False
    asked_at: float = 0.0
    shared: bool = False


# --------------------------------------------------------------------------- #
# ask
# --------------------------------------------------------------------------- #


def _today():
    return timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)


def _guest_limits(discord_user_id: str, guild_id: str) -> Refusal | None:
    today = _today()
    cap = int(config.get("discord_guest_daily_turns") or 0)
    if cap and (
        AgentDiscordTurn.objects.filter(
            discord_user_id=str(discord_user_id), guest=True, created_at__gte=today
        ).count()
        >= cap
    ):
        return Refusal("guest_limit", GUEST_LIMIT.format(cap=cap))
    cap = int(config.get("discord_place_daily_turns") or 0)
    if cap and (
        AgentDiscordTurn.objects.filter(
            link__guild_id=str(guild_id), guest=True, created_at__gte=today
        ).count()
        >= cap
    ):
        return Refusal("place_limit", PLACE_LIMIT.format(cap=cap))
    return None


def _scope_and_audience(place) -> tuple[Scope, Audience]:
    if place.lab is not None:
        return Scope("lab", place.lab), Audience("lab", place.lab)
    if place.department is not None:
        return (
            Scope("department", place.department),
            Audience("department", place.department),
        )
    # Several bindings, none owns the channel: public material only.
    return Scope(), Audience("instance")


def _refusal(gate_result) -> Refusal:
    return Refusal(str(gate_result.denial or "denied"), gate_result.message)


def _service_refusal(err) -> Refusal:
    text = err.detail
    if err.fix and err.code not in ("queue_full",):
        text = f"{text} {err.fix}"
    return Refusal(err.code, text)


def build_caller(
    *,
    discord_user_id: str,
    name: str,
    guild_id: str,
    channel_id: str,
    thread_id: str,
    parent_id: str,
):
    """``(caller, place)`` for one Discord message, or a :class:`Refusal`.
    Identity comes from the gateway event's ids only."""
    from apps.integrations.services import gate, resolve

    from .. import permissions

    place = resolve.place_for(guild_id, channel_id, thread_id, parent_id)
    if place.kind == resolve.PLACE_UNBOUND:
        return Refusal("unbound", UNBOUND)
    via = {
        "discord_user_id": str(discord_user_id),
        "guild_id": str(guild_id or ""),
        "channel_id": str(channel_id or ""),
        "thread_id": str(thread_id or ""),
        "parent_id": str(parent_id or ""),
        "place_kind": place.kind,
        "place_server": place.server_name,
        "place_title": place.title,
    }
    if place.kind == resolve.PLACE_DM:
        result = gate.authorize(discord_user_id=str(discord_user_id), action="chat")
        if not result:
            if result.denial in (gate.Denial.NOT_LINKED, gate.Denial.NOT_VERIFIED):
                return Refusal(str(result.denial), CONNECT_DM)
            return _refusal(result)
        return (
            Caller(
                user=result.user,
                surface="discord",
                scope=Scope(),
                audience=Audience("person"),
                via=via,
            ),
            place,
        )
    binding = place.binding or place.any_binding
    scope, audience = _scope_and_audience(place)
    user = resolve.resolve_user(str(discord_user_id))
    if user is not None or config.get("discord_access") != "public":
        result = gate.authorize(
            discord_user_id=str(discord_user_id),
            action="chat",
            guild_id=str(guild_id),
            binding_id=binding.pk,
        )
        if not result:
            return _refusal(result)
        user = result.user
        if scope.obj is None or permissions.role_in(user, scope.kind, scope.obj):
            return (
                Caller(
                    user=user,
                    surface="discord",
                    scope=scope,
                    audience=audience,
                    via=via,
                ),
                place,
            )
        # A linked account with no place in this lab or department asks as
        # anyone else in the server does: as a guest.
    result = gate.authorize_guest(
        discord_user_id=str(discord_user_id),
        action="chat_guest",
        guild_id=str(guild_id),
        binding_id=binding.pk,
    )
    if not result:
        return _refusal(result)
    guest = Guest(str(discord_user_id), clean_name(name))
    return (
        Caller(
            user=None,
            guest=guest,
            surface="discord",
            scope=scope,
            audience=audience,
            via=via,
        ),
        place,
    )


def _open_link(caller, place, *, guild_id: str, place_id: str, discord_user_id):
    """The open conversation of this place (and person, where each has their
    own), rolled over when a per-person channel conversation went quiet."""
    from apps.integrations.services import resolve

    dm = place.kind == resolve.PLACE_DM
    key_user = "" if place.shared else str(discord_user_id)
    link = (
        AgentThreadLink.objects.filter(
            guild_id=str(guild_id or ""),
            place_id=str(place_id),
            discord_user_id=key_user,
            closed_at=None,
        )
        .select_related("thread")
        .first()
    )
    if link is not None:
        thread = link.thread
        stale = False
        if not place.shared and not dm:
            hours = int(config.get("discord_channel_session_hours") or 0)
            stale = bool(hours) and thread.last_activity_at < timezone.now() - (
                timedelta(hours=hours)
            )
        if dm and thread.user_id != getattr(caller.user, "pk", None):
            stale = True  # the Discord account was linked to someone else
        if not stale:
            return link
        AgentThreadLink.objects.filter(pk=link.pk).update(closed_at=timezone.now())
    anchor = place.anchor or None
    kwargs = dict(
        scope=caller.scope,
        surface="discord",
        title=(place.title or "")[:200],
        caller=caller,
        shared=not dm,
    )
    try:
        thread = service.create_thread(
            caller.user if dm else None, anchor=anchor, **kwargs
        )
    except service.ServiceError as err:
        if err.code != "anchor_not_visible":
            raise
        anchor = None
        thread = service.create_thread(caller.user if dm else None, **kwargs)
    try:
        with transaction.atomic():
            return AgentThreadLink.objects.create(
                thread=thread,
                guild_id=str(guild_id or ""),
                place_id=str(place_id),
                discord_user_id=key_user,
                binding_id=getattr(place.binding, "pk", None),
                anchor=anchor or {},
            )
    except IntegrityError:  # someone else opened it a moment ago
        thread.delete()
        return AgentThreadLink.objects.select_related("thread").get(
            guild_id=str(guild_id or ""),
            place_id=str(place_id),
            discord_user_id=key_user,
            closed_at=None,
        )


def ask(
    *,
    discord_user_id,
    name: str,
    guild_id,
    channel_id,
    thread_id="",
    parent_id="",
    message_id,
    text: str,
    attachments=(),
    start=None,
    reply_to_id="",
) -> Handle | Refusal:
    """Ask Mylo something from Discord. A :class:`Handle` to follow, or a
    :class:`Refusal` whose ``message`` is ready to post.

    A question that replies to one of Mylo's answers (or to the question it
    answered) continues that conversation, whoever asked it first; any other
    question goes to the asker's own conversation in this place."""
    from tools._framework import host

    if not host.is_loaded("agent"):
        return Refusal("agent_off", AGENT_OFF)
    text = (text or "").strip()
    if not text and not attachments:
        return Refusal("empty", EMPTY)
    built = build_caller(
        discord_user_id=str(discord_user_id),
        name=name,
        guild_id=str(guild_id or ""),
        channel_id=str(channel_id or ""),
        thread_id=str(thread_id or ""),
        parent_id=str(parent_id or ""),
    )
    if isinstance(built, Refusal):
        return built
    caller, place = built
    if caller.is_guest:
        limited = _guest_limits(str(discord_user_id), str(guild_id))
        if limited is not None:
            return limited
    if service.status().get("model") is None:
        return Refusal("no_model", NO_MODEL)
    place_id = str(thread_id or channel_id)
    try:
        link = _link_for_reply(
            guild_id=str(guild_id or ""),
            place_id=place_id,
            reply_to_id=str(reply_to_id or ""),
        ) or _open_link(
            caller,
            place,
            guild_id=str(guild_id or ""),
            place_id=place_id,
            discord_user_id=str(discord_user_id),
        )
        thread = link.thread
        caller = replace(caller, thread_id=thread.pk)
        first = not AgentEvent.objects.filter(
            thread=thread, type="assistant", payload__final=True
        ).exists()
        thread.refresh_from_db()
        if (
            thread.state == AgentThread.State.WAITING
            and not thread.shared
            and caller.user is not None
        ):
            # A DM answering Mylo's own question.
            seq = store.last_seq(thread)
            service.answer(caller, thread, text, start=start)
            result = {"status": "answered", "seq": seq}
        else:
            result = service.send(
                caller,
                thread,
                text,
                attachments=attachments if not thread.shared else (),
                start=start,
            )
    except service.ServiceError as err:
        return _service_refusal(err)
    turn = AgentDiscordTurn.objects.create(
        link=link,
        user_event_seq=int(result.get("seq") or 0),
        queued_id=result.get("queued_id"),
        trigger_message_id=str(message_id),
        channel_id=str(channel_id),
        discord_user_id=str(discord_user_id),
        guest=caller.is_guest,
    )
    return _handle(turn, first=first)


def _handle(turn: AgentDiscordTurn, *, first: bool = False) -> Handle:
    link = turn.link
    return Handle(
        turn_id=turn.pk,
        thread_id=str(link.thread_id),
        link_id=link.pk,
        discord_user_id=turn.discord_user_id,
        channel_id=turn.channel_id,
        trigger_message_id=turn.trigger_message_id,
        status_message_id=turn.status_message_id,
        user_event_seq=turn.user_event_seq,
        queued=bool(turn.queued_id) and not turn.user_event_seq,
        guest=turn.guest,
        first=first,
        asked_at=turn.created_at.timestamp() if turn.created_at else time.time(),
        shared=bool(link.thread.shared),
    )


# --------------------------------------------------------------------------- #
# follow and the answer
# --------------------------------------------------------------------------- #


def _user_seq(turn: AgentDiscordTurn) -> int:
    """The turn's ``user`` event, found once a queued question got its turn."""
    if turn.user_event_seq:
        return turn.user_event_seq
    if not turn.queued_id:
        return 0
    event = (
        AgentEvent.objects.filter(
            thread_id=turn.link.thread_id,
            type="user",
            payload__queued_id=turn.queued_id,
        )
        .order_by("seq")
        .first()
    )
    if event is None:
        return 0
    AgentDiscordTurn.objects.filter(pk=turn.pk).update(user_event_seq=event.seq)
    turn.user_event_seq = event.seq
    return event.seq


def _turn_events(thread, seq: int) -> list:
    """Events of one turn: from its question up to the next question."""
    out = []
    for event in store.events(thread, after=seq):
        if event.type == "user":
            break
        out.append(event)
    return out


def _ended(message: dict) -> bool:
    kind = message.get("type")
    payload = message.get("payload") or {}
    if kind == "assistant" and payload.get("final"):
        return True
    return kind in ("error", "question") or (
        kind == "state" and payload.get("state") in ("idle", "error", "waiting")
    )


def follow(handle: Handle, *, poll: float = 1.0, max_seconds=None) -> Iterator[dict]:
    """The turn's activity view (S-9: never thinking), ending with its answer.

    A queued question yields ``{"type": "queued"}`` until its turn starts.
    With the stream bus down it reads the log once a second instead, so an
    answer is late, not lost."""
    from ..activity import Projector

    turn = AgentDiscordTurn.objects.select_related("link").get(pk=handle.turn_id)
    thread = AgentThread.objects.get(pk=handle.thread_id)
    if max_seconds is None:
        max_seconds = int(config.get("discord_turn_timeout_minutes") or 30) * 60
    started = time.monotonic()
    announced = False
    while not _user_seq(turn):
        if not announced:
            announced = True
            yield {"type": "queued"}
        if not AgentQueuedMessage.objects.filter(pk=turn.queued_id).exists():
            if not _user_seq(turn):
                return  # removed from the queue (deleted, or stopped)
        if time.monotonic() - started > max_seconds:
            return
        time.sleep(poll)
    seq = turn.user_event_seq
    try:
        messages = stream.follow(
            thread,
            after=seq,
            view="activity",
            stop_when_idle=True,
            poll=poll,
            max_seconds=max_seconds,
        )
        for message in messages:
            if message.get("type") == "heartbeat":
                continue
            if message.get("type") == "user":
                return  # the next person's turn
            yield message
            if _ended(message):
                return
        return
    except Exception:  # the stream bus is down: read the log instead
        logger.warning("agent stream unavailable; following %s by polling", thread.pk)
    projector = Projector(thread)
    sent = seq
    while time.monotonic() - started <= max_seconds:
        for event in store.events(thread, after=sent):
            sent = event.seq
            if event.type == "user":
                return
            shown = projector.project(stream.event_message(event))
            if shown is None:
                continue
            yield shown
            if _ended(shown):
                return
        time.sleep(poll)


#: The app page that opens an item in its reader, by the kind the agent names
#: in the item's title ("[grant] …"). The web panel's `open-ref.ts` has the
#: same table; keep the two in step.
_FEEDS = {
    "paper": "/app/research-papers",
    "grant": "/app/grants",
    "fellowship": "/app/fellowships",
    "conference": "/app/conferences",
}


def _source_url(key: str) -> str:
    """The item's own page at its source, or ``""`` when it has none (or the
    key is not an item)."""
    from django.core.exceptions import ValidationError

    from tools.retrieval.read import ContentItem

    try:
        item = ContentItem.objects.filter(pk=key).only("source_url", "metadata").first()
    except (ValidationError, ValueError):
        return ""
    if item is None:
        return ""
    meta = item.metadata or {}
    return item.source_url or meta.get("url") or meta.get("website") or ""


def _item_url(key: str, *, guest: bool, title: str) -> str:
    """Where a cited item opens from Discord: its own page at the source, for
    everyone. Only an item with no page of its own falls back to the web app
    (and only for a member — a guest has no account to open it with)."""
    from django.conf import settings

    source = _source_url(key)
    if source or guest:
        return source
    base = str(getattr(settings, "DISCORD_APP_BASE_URL", "") or "").rstrip("/")
    if not base:
        return ""
    kind = re.match(r"^\[(\w+)\]", title)
    feed = _FEEDS.get(kind.group(1).lower() if kind else "", _FEEDS["paper"])
    return f"{base}{feed}?item={quote(str(key), safe='')}"


def sources(thread, text: str, *, guest: bool) -> list[dict]:
    """``[{n, title, url}]`` for every ``#n`` the answer cites, in order. A
    link goes to the item's own page at its source; the web app only when the
    item has none."""
    out, seen = [], set()
    for match in re.finditer(r"#(\d+)\b", text or ""):
        n = int(match.group(1))
        if n in seen:
            continue
        seen.add(n)
        entry = refs.lookup(thread, n)
        if entry is None:
            continue
        title = str(entry.get("title") or "")
        url = ""
        if entry.get("kind") == "item":
            url = _item_url(entry["key"], guest=guest, title=title)
        out.append({"n": n, "title": title, "url": url})
    return out


def result(handle: Handle) -> dict:
    """Where the turn stands: ``{state, text, sources, model, question,
    error, elapsed}``; ``state`` is ``answered``, ``failed``, ``cancelled``,
    ``waiting`` or ``running``."""
    turn = AgentDiscordTurn.objects.select_related("link").get(pk=handle.turn_id)
    thread = AgentThread.objects.get(pk=handle.thread_id)
    elapsed = time.time() - handle.asked_at if handle.asked_at else 0.0
    out = {
        "state": "running",
        "text": "",
        "sources": [],
        "model": None,
        "question": None,
        "error": "",
        "elapsed": elapsed,
    }
    if turn.state == AgentDiscordTurn.State.CANCELLED:
        out["state"] = "cancelled"
        return out
    seq = _user_seq(turn)
    if not seq:
        return out
    events = _turn_events(thread, seq)
    stopped = any(
        e.type == "note" and e.payload.get("text") == "Stopped." for e in events
    )
    for event in events:
        p = event.payload
        if event.type == "assistant" and p.get("final"):
            out.update(
                state="answered",
                text=p.get("text") or "",
                model=p.get("model"),
                sources=sources(thread, p.get("text") or "", guest=handle.guest),
            )
        elif event.type == "question":
            out.update(state="waiting", question=dict(p))
        elif event.type == "error":
            out.update(state="failed", error=p.get("detail") or "")
    if out["state"] == "running" and stopped:
        out["state"] = "cancelled"
    if out["state"] == "running":
        thread_state = thread.state
        if thread_state != AgentThread.State.RUNNING and events:
            out["state"] = "failed"
    return out


def set_status_message(handle: Handle, message_id) -> Handle:
    AgentDiscordTurn.objects.filter(pk=handle.turn_id).update(
        status_message_id=str(message_id)
    )
    return replace(handle, status_message_id=str(message_id))


def finish(handle: Handle, state: str, message_ids=()) -> None:
    """Record that the bot delivered (or gave up on) this turn, and every
    other message the answer was posted as."""
    fields = {"state": state, "finished_at": timezone.now()}
    ids = [str(m) for m in message_ids or () if m]
    if ids:
        fields["message_ids"] = ids
    AgentDiscordTurn.objects.filter(pk=handle.turn_id).update(**fields)


def _link_for_reply(*, guild_id: str, place_id: str, reply_to_id: str):
    """The conversation a reply continues: the one whose question or answer
    the replied-to message was, in this same place. ``None`` when the reply
    is to anything else."""
    from django.db.models import Q

    if not reply_to_id:
        return None
    turn = (
        AgentDiscordTurn.objects.filter(
            Q(status_message_id=reply_to_id)
            | Q(trigger_message_id=reply_to_id)
            | Q(message_ids__contains=[reply_to_id]),
            link__guild_id=guild_id,
            link__place_id=place_id,
        )
        .select_related("link__thread")
        .order_by("-created_at")
        .first()
    )
    return turn.link if turn is not None else None


# --------------------------------------------------------------------------- #
# stop, forget, deletion, recovery
# --------------------------------------------------------------------------- #


def stop(handle: Handle, *, discord_user_id) -> Refusal | None:
    """Stop the running answer: the asker, or a manager of the place's lab or
    department (the same right as ``/setup``)."""
    turn = AgentDiscordTurn.objects.select_related("link", "link__thread").get(
        pk=handle.turn_id
    )
    if str(discord_user_id) != turn.discord_user_id:
        from apps.integrations.services import gate

        link = turn.link
        if link.binding_id is None:
            return Refusal("forbidden", "Only the person who asked can stop this.")
        granted = gate.authorize(
            discord_user_id=str(discord_user_id),
            action="chat_manage",
            guild_id=link.guild_id,
            binding_id=link.binding_id,
        )
        if not granted:
            return Refusal(
                "forbidden", "Only the person who asked, or a manager, can stop this."
            )
    if turn.queued_id and not _user_seq(turn):
        AgentQueuedMessage.objects.filter(pk=turn.queued_id).delete()
    else:
        service.cancel(None, turn.link.thread)
    AgentDiscordTurn.objects.filter(pk=turn.pk).update(
        state=AgentDiscordTurn.State.CANCELLED, finished_at=timezone.now()
    )
    return None


def _blank(event: AgentEvent) -> None:
    payload = dict(event.payload)
    payload.update(text="", cards=[], mentions=[], inline=[], forgotten=True)
    AgentEvent.objects.filter(pk=event.pk).update(payload=payload)


def forget_command(*, discord_user_id, guild_id, place_id) -> str:
    """``/mylo forget``, through the gate (audited), as a sentence."""
    from apps.integrations.services import gate, resolve

    discord_user_id = str(discord_user_id)
    if guild_id and resolve.resolve_user(discord_user_id) is None:
        place = resolve.place_for(str(guild_id), str(place_id))
        binding = place.binding or place.any_binding
        result = gate.authorize_guest(
            discord_user_id=discord_user_id,
            action="chat_forget",
            guild_id=str(guild_id),
            binding_id=getattr(binding, "pk", None),
        )
    else:
        result = gate.authorize(discord_user_id=discord_user_id, action="chat_forget")
    if not result:
        return result.message
    n = forget(discord_user_id=discord_user_id, guild_id=guild_id, place_id=place_id)
    if not guild_id:
        return (
            "Done: our conversation here is deleted."
            if n
            else "There was nothing to forget here."
        )
    if not n:
        return "You haven't asked me anything here that I still hold."
    return f"Done: I've blanked {n} of your questions here. Others' stay."


def forget(*, discord_user_id, guild_id, place_id) -> int:
    """``/mylo forget``: in a DM the conversation is deleted; elsewhere the
    caller's own questions in this place are blanked (others' stay)."""
    discord_user_id = str(discord_user_id)
    links = AgentThreadLink.objects.filter(
        guild_id=str(guild_id or ""), place_id=str(place_id)
    ).select_related("thread")
    count = 0
    for link in links:
        thread = link.thread
        if not guild_id and link.discord_user_id == discord_user_id:
            thread.delete()
            count += 1
            continue
        AgentQueuedMessage.objects.filter(
            thread=thread, speaker__discord_user_id=discord_user_id
        ).delete()
        for event in AgentEvent.objects.filter(
            thread=thread,
            type="user",
            payload__speaker__discord_user_id=discord_user_id,
        ):
            if not event.payload.get("forgotten"):
                _blank(event)
                count += 1
    return count


def new_command(*, discord_user_id, guild_id, place_id) -> str:
    """``/mylo new``, through the same gate as forget, as a sentence."""
    from apps.integrations.services import gate, resolve

    discord_user_id = str(discord_user_id)
    if guild_id and resolve.resolve_user(discord_user_id) is None:
        place = resolve.place_for(str(guild_id), str(place_id))
        binding = place.binding or place.any_binding
        result = gate.authorize_guest(
            discord_user_id=discord_user_id,
            action="chat_forget",
            guild_id=str(guild_id),
            binding_id=getattr(binding, "pk", None),
        )
    else:
        result = gate.authorize(discord_user_id=discord_user_id, action="chat_forget")
    if not result:
        return result.message
    closed = new_conversation(
        discord_user_id=discord_user_id, guild_id=guild_id, place_id=place_id
    )
    if not closed:
        return "There's no conversation to refresh here yet: just ask me something."
    return (
        "Fresh start: your next question here begins a new conversation. "
        "Replying to one of my earlier answers still continues that one."
    )


def new_conversation(*, discord_user_id, guild_id, place_id) -> int:
    """``/mylo new``: close the open conversation the caller's next question
    here would join (their own; in a Discord thread, the thread's shared one),
    so it starts afresh. Nothing is deleted: the old conversation stays
    readable, and a reply to one of its answers still continues it."""
    from apps.integrations.services import resolve

    guild_id = str(guild_id or "")
    shared = bool(guild_id) and resolve.place_for(guild_id, str(place_id)).shared
    return AgentThreadLink.objects.filter(
        guild_id=guild_id,
        place_id=str(place_id),
        discord_user_id="" if shared else str(discord_user_id),
        closed_at=None,
    ).update(closed_at=timezone.now())


# --------------------------------------------------------------------------- #
# Switches (/mylo chat …): the gate first, then the agent's own policy door
# --------------------------------------------------------------------------- #

GUEST_WORDS = {
    "full": "everything a lab member would be told here, people included",
    "no_people": "the same without looking up people",
    "public": "the thread's opening post and the public corpus only",
    "off": "nothing: only linked accounts may ask",
}


def set_chat(*, discord_user_id, on: bool) -> str:
    """``/mylo chat on|off``: the person's own switch (``discord_allowed``)."""
    from apps.integrations.services import gate

    result = gate.authorize(discord_user_id=str(discord_user_id), action="chat_self")
    if not result:
        return result.message
    service.set_preferences(result.user, discord_allowed=bool(on))
    return (
        "Mylo chat in Discord is **on** for you."
        if on
        else "Mylo chat in Discord is **off** for you. I won't answer your "
        "questions here until you turn it back on."
    )


def _manage(discord_user_id, guild_id, channel_id, thread_id, parent_id):
    """``(user, kind, org, place)`` for a manager of this place, or a
    sentence."""
    from apps.integrations.services import gate, resolve

    if not guild_id:
        return "Run this in a server channel, not in a DM."
    place = resolve.place_for(str(guild_id), str(channel_id), thread_id, parent_id)
    if place.binding is None:
        if place.kind == resolve.PLACE_UNBOUND:
            return UNBOUND
        return (
            "I can't tell which lab or department this channel belongs to. "
            "Choose it as one of the binding's channels in `/setup` first."
        )
    result = gate.authorize(
        discord_user_id=str(discord_user_id),
        action="chat_manage",
        guild_id=str(guild_id),
        binding_id=place.binding.pk,
    )
    if not result:
        return result.message
    if place.binding.lab_id:
        return result.user, "lab", place.binding.lab, place
    return result.user, "department", place.binding.department, place


def set_channel(
    *, discord_user_id, guild_id, channel_id, thread_id="", parent_id="", on: bool
) -> str:
    """``/mylo chat here on|off``: a manager turns chat on or off for this
    channel (in a thread: its parent channel or forum)."""
    got = _manage(discord_user_id, guild_id, channel_id, thread_id, parent_id)
    if isinstance(got, str):
        return got
    user, kind, org, _place = got
    target = str(parent_id or channel_id) if thread_id else str(channel_id)
    policy = service.get_org_policy(user, kind, org)
    off = set(policy.discord_channels_off if policy else [])
    if on:
        off.discard(target)
    else:
        off.add(target)
    service.set_org_policy(user, kind, org, discord_channels_off=sorted(off))
    where = f"<#{int(target)}>" if target.isdigit() else "this channel"
    return (
        f"Mylo chat is **on** in {where}."
        if on
        else f"Mylo chat is **off** in {where}. People can still ask me in a DM."
    )


def set_guests(
    *, discord_user_id, guild_id, channel_id, thread_id="", parent_id="", level: str
) -> str:
    """``/mylo chat guests …``: what people without an account are told here."""
    got = _manage(discord_user_id, guild_id, channel_id, thread_id, parent_id)
    if isinstance(got, str):
        return got
    user, kind, org, _place = got
    level = str(level).replace("-", "_")
    try:
        service.set_org_policy(user, kind, org, discord_guests=level)
    except service.ServiceError as err:
        return err.detail
    in_force = service.guest_level_in_force(kind, org)
    line = f"Guests here now get {GUEST_WORDS.get(level, level)}."
    if in_force != level:
        line += (
            f" This Mycelium allows at most **{in_force.replace('_', '-')}**, so "
            f"that is what applies: {GUEST_WORDS.get(in_force, in_force)}."
        )
    return line


def question_deleted(trigger_message_id) -> bool:
    """The question's Discord message was deleted: drop it from the queue if it
    has not run, and blank its stored text."""
    found = False
    for turn in AgentDiscordTurn.objects.filter(
        trigger_message_id=str(trigger_message_id)
    ).select_related("link"):
        found = True
        if turn.queued_id and not _user_seq(turn):
            AgentQueuedMessage.objects.filter(pk=turn.queued_id).delete()
            AgentDiscordTurn.objects.filter(pk=turn.pk).update(
                state=AgentDiscordTurn.State.CANCELLED, finished_at=timezone.now()
            )
            continue
        event = AgentEvent.objects.filter(
            thread_id=turn.link.thread_id, seq=turn.user_event_seq, type="user"
        ).first()
        if event is not None:
            _blank(event)
    return found


def place_deleted(place_id) -> int:
    """A Discord thread was deleted: its conversation goes with it."""
    links = list(
        AgentThreadLink.objects.filter(place_id=str(place_id)).select_related("thread")
    )
    for link in links:
        link.thread.delete()
    return len(links)


def close_links(*, guild_id=None, binding_id=None) -> int:
    """A binding removed, or a server Mylo left: every link in it is closed
    (the retention sweep deletes the conversations later)."""
    rows = AgentThreadLink.objects.filter(closed_at=None)
    if binding_id is not None:
        rows = rows.filter(binding_id=binding_id)
    elif guild_id:
        rows = rows.filter(guild_id=str(guild_id))
    else:
        return 0
    return rows.update(closed_at=timezone.now())


def reconcile() -> list[Handle]:
    """Questions not yet delivered, oldest first (after a restart or a gateway
    resume). Each comes back with its ``status_message_id``; the bot checks
    :func:`result` and delivers, or says it lost track."""
    rows = AgentDiscordTurn.objects.filter(
        state=AgentDiscordTurn.State.PENDING
    ).select_related("link", "link__thread")
    return [_handle(turn) for turn in rows]


def bus_ok() -> bool:
    """Whether the stream bus answers (``/mylo health``)."""
    try:
        stream.bus().has_flag("mylo:health")
    except Exception:  # noqa: BLE001
        return False
    return True


def timed_out(handle: Handle) -> bool:
    minutes = int(config.get("discord_turn_timeout_minutes") or 30)
    return bool(handle.asked_at) and time.time() - handle.asked_at > minutes * 60


def ping_due(handle: Handle) -> bool:
    """Whether the answer is slow enough to ping the asker (S-12)."""
    minutes = int(config.get("discord_ping_after_minutes") or 0)
    return bool(minutes) and time.time() - handle.asked_at > minutes * 60


__all__ = [
    "EMPTY",
    "REPLY_HINT",
    "Handle",
    "Refusal",
    "ask",
    "bus_ok",
    "close_links",
    "finish",
    "follow",
    "forget",
    "forget_command",
    "set_channel",
    "set_chat",
    "set_guests",
    "ping_due",
    "place_deleted",
    "question_deleted",
    "reconcile",
    "result",
    "set_status_message",
    "sources",
    "stop",
    "timed_out",
]
