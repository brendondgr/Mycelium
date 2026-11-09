"""The agent write door: what surfaces (the web API, the CLI, later Discord)
call. A surface builds the ``Caller``; everything here re-checks it through
the gate. Surfaces reach this module with ``services.get("agent")`` so they
keep working when the tool is disabled or deleted."""

from __future__ import annotations

import re

from django.db import transaction
from django.utils import timezone

from tools._framework.agentspec import width_rank

from . import config, permissions, refs, store, stream
from .caller import Audience, Caller, Scope, for_thread
from .models import (
    AgentEvent,
    AgentOrgPolicy,
    AgentPreference,
    AgentQueuedMessage,
    AgentThread,
)


class ServiceError(Exception):
    def __init__(
        self, code: str, detail: str, fix: str = "", status: int = 400
    ) -> None:
        super().__init__(detail)
        self.code, self.detail, self.fix, self.status = code, detail, fix, status

    def as_dict(self) -> dict:
        return {"code": self.code, "detail": self.detail, "fix": self.fix}


def _gate(caller: Caller) -> None:
    decision = permissions.may_chat(caller)
    if not decision.allowed:
        raise ServiceError(decision.code, decision.detail, decision.fix, status=403)


# --------------------------------------------------------------------------- #
# Threads
# --------------------------------------------------------------------------- #


def scope_from(user, kind: str | None, ref: str | None) -> Scope:
    """Resolve a requested scope (``lab`` + slug, ``project`` + uuid, …)."""
    from apps.accounts.models import Department, Lab
    from apps.research.models import Project

    if kind in ("", None, "personal"):
        return Scope("personal")
    obj = None
    try:
        if kind == "lab":
            obj = Lab.objects.filter(slug=ref).first()
        elif kind == "department":
            obj = Department.objects.filter(pk=ref).first()
        elif kind == "project":
            obj = (
                Project.objects.select_related(
                    "scope_lab", "scope_department", "scope_user"
                )
                .filter(pk=ref)
                .first()
            )
    except Exception:  # a malformed id reads the same as an invisible one
        obj = None
    if obj is None or permissions.role_in(user, kind, obj) is None:
        raise ServiceError(
            "scope_not_visible", f"You can't open this {kind} with Mylo.", status=404
        )
    return Scope(kind, obj)


def _anchor(value) -> dict:
    anchor = refs.parse_anchor(value)
    if anchor is None:
        raise ServiceError(
            "bad_anchor",
            "That is not something a conversation can be about.",
            'Send {"kind": "item", "key": "<id>"} or "item:<id>".',
        )
    return anchor


def create_thread(
    user,
    *,
    scope: Scope,
    surface: str = "web",
    title: str = "",
    anchor=None,
    caller: Caller | None = None,
    shared: bool = False,
) -> AgentThread:
    """A new thread. With ``anchor`` (``{"kind", "key"}`` or ``"kind:key"``)
    the conversation is about that object for good: it is reference ``#1``
    and every turn resolves it again for whoever is asking (S2). The creator
    must be able to see it.

    A surface that has already built the asker's ``caller`` (Discord: maybe
    a guest, with the place's audience) passes it; ``shared`` makes a thread
    with no owner that belongs to its place (plan D)."""
    caller = caller or Caller(user=user, surface=surface, scope=scope)
    _gate(caller)
    info = None
    if anchor:
        anchor = _anchor(anchor)
        info = refs.resolve(caller, f"{anchor['kind']}:{anchor['key']}")
        if info is None:
            raise ServiceError(
                "anchor_not_visible",
                "You can't open a conversation about that.",
                status=404,
            )
        # Stored as the resolver names it, so #1 and the list filter agree.
        anchor = {"kind": info.kind, "key": info.key}
    fields = {
        "lab": "scope_lab",
        "department": "scope_department",
        "project": "scope_project",
    }
    kwargs = {fields[scope.kind]: scope.obj} if scope.kind in fields else {}
    with transaction.atomic():
        thread = AgentThread.objects.create(
            user=None if shared else user,
            shared=bool(shared),
            scope_kind=scope.kind,
            surface=surface,
            title=title[:200],
            settings={"anchor": anchor} if info is not None else {},
            **kwargs,
        )
        if info is not None:
            refs.number(thread, info)  # the first reference: #1
    return thread


def get_thread(user, thread_id) -> AgentThread:
    """Only the owner may read a thread; an org admin cannot."""
    try:
        return AgentThread.objects.select_related(
            "user", "scope_lab", "scope_department", "scope_project"
        ).get(pk=thread_id, user=user, shared=False)
    except Exception:  # missing, someone else's, or a malformed id: all the same
        raise ServiceError("not_found", "No such conversation.", status=404) from None


def list_threads(
    user, *, q: str = "", archived: bool = False, anchor=None, limit: int = 50
):
    """The person's threads, most recent first. ``anchor`` (``"kind:key"`` or
    a dict) keeps only the threads about that object."""
    from django.db.models import Q

    rows = AgentThread.objects.filter(user=user, shared=False, archived=archived)
    if anchor:
        a = _anchor(anchor)
        rows = rows.filter(
            settings__anchor__kind=a["kind"], settings__anchor__key=a["key"]
        )
    if q:
        rows = rows.filter(
            Q(title__icontains=q)
            | Q(purpose__icontains=q)
            | Q(digest__text__icontains=q)
        ).distinct()
    return list(rows.order_by("-pinned", "-last_activity_at")[:limit])


def update_thread(
    user, thread_id, *, title=None, archived=None, pinned=None
) -> AgentThread:
    thread = get_thread(user, thread_id)
    fields = []
    if pinned is not None:
        thread.pinned = _truthy(pinned)
        fields.append("pinned")
    if title is not None:
        thread.title = str(title)[:200]
        fields.append("title")
    if archived is not None:
        thread.archived = bool(archived)
        fields.append("archived")
    if fields:
        thread.save(update_fields=[*fields, "updated_at"])
    return thread


def _truthy(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def delete_thread(user, thread_id) -> None:
    """Deletes the thread and its events. Files attached in it stay with their
    owner; observations already recorded follow ambient's own deletion path."""
    get_thread(user, thread_id).delete()


def fork_thread(user, thread_id, seq: int) -> AgentThread:
    thread = get_thread(user, thread_id)
    if seq < 1 or seq > store.last_seq(thread):
        raise ServiceError("bad_seq", "That point is not in this conversation.")
    return store.fork(thread, seq)


# --------------------------------------------------------------------------- #
# Messages
# --------------------------------------------------------------------------- #


def _today_turns(user) -> int:
    from django.db.models import Q

    start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    return AgentEvent.objects.filter(
        Q(thread__user=user) | Q(payload__speaker__user_id=user.pk),
        type="user",
        ts__gte=start,
    ).count()


def _check_budget(user) -> None:
    if user is None:  # a guest: the Discord adapter holds the guest limits
        return
    cap = int(config.get("daily_turns") or 0)
    if cap and _today_turns(user) >= cap:
        raise ServiceError(
            "daily_limit",
            f"You've used today's {cap} messages to Mylo.",
            "It resets at midnight.",
            status=429,
        )


def resolve_mentions(caller: Caller, thread: AgentThread, mentions) -> list[str]:
    """Check every tagged reference for the caller and the audience, number it,
    and return its card. A reference that cannot be seen fails here, at send
    time, rather than silently inside the model."""
    cards = []
    for token in mentions or []:
        info = refs.resolve(caller, str(token))
        if info is None:
            raise ServiceError(
                "mention_not_visible",
                f"{token} is not something you can open.",
                status=404,
            )
        if width_rank(info.output) < width_rank(caller.audience.width):
            raise ServiceError(
                "mention_audience",
                f"{token} can't be shown to everyone who will read this.",
                "Ask in a DM.",
                status=403,
            )
        n = refs.number(thread, info)
        cards.append(refs.card(n, info))
    return cards


def _speaks(caller: Caller | None, thread) -> bool:
    """Whether a message records who spoke and from where (plan D): every
    Discord message and every shared thread; web and CLI threads as before."""
    return caller is not None and (
        bool(getattr(thread, "shared", False)) or caller.surface == "discord"
    )


def record_user_message(
    thread,
    text: str,
    *,
    mentions=(),
    caller: Caller | None = None,
    inline=None,
    cards=None,
    speaker: dict | None = None,
    turn: dict | None = None,
    queued_id: int | None = None,
) -> AgentEvent:
    if cards is None:
        cards = resolve_mentions(caller or for_thread(thread), thread, mentions)
    if _speaks(caller, thread):
        speaker = speaker or caller.speaker()
        turn = turn or caller.turn()
    return store.append(
        thread,
        "user",
        {
            "text": text,
            "mentions": list(mentions or []),
            "cards": cards,
            **({"inline": inline} if inline else {}),
            **({"speaker": speaker} if speaker else {}),
            **({"turn": turn} if turn else {}),
            **({"queued_id": queued_id} if queued_id else {}),
        },
    )


#: Questions that may wait in a shared thread while a turn runs (plan D).
SHARED_QUEUE_MAX = 5


def send(
    caller: Caller,
    thread: AgentThread,
    text: str,
    *,
    mentions=(),
    attachments=(),
    steer: bool = False,
    start=None,
) -> dict:
    """Send a message. During a running turn it is queued (answered together
    when the turn ends) or, with ``steer``, written at once for the running
    turn's next model call."""
    _gate(caller)
    text = (text or "").strip()
    if not text and not attachments:
        raise ServiceError("empty", "Say something to Mylo.")
    _check_budget(caller.user)
    thread.refresh_from_db()
    if thread.state == AgentThread.State.WAITING:
        raise ServiceError(
            "waiting",
            "Mylo asked you a question; answer it first.",
            "POST to the thread's answer route.",
            status=409,
        )
    cards = resolve_mentions(caller, thread, mentions)
    inline: list = []
    if attachments:
        from . import attachments as att

        more_cards, inline = att.attach(caller, thread, attachments)
        cards += more_cards
    if thread.state == AgentThread.State.RUNNING and not steer:
        speaks = _speaks(caller, thread)
        if (
            thread.shared
            and AgentQueuedMessage.objects.filter(thread=thread).count()
            >= SHARED_QUEUE_MAX
        ):
            raise ServiceError(
                "queue_full",
                "One at a time, please.",
                "Ask again once Mylo has answered.",
                status=429,
            )
        row = AgentQueuedMessage.objects.create(
            thread=thread,
            text=text,
            mentions=list(mentions or []),
            speaker=caller.speaker() if speaks else {},
            turn=caller.turn() if speaks else {},
        )
        return {"status": "queued", "queued_id": row.pk}
    event = record_user_message(
        thread, text, mentions=mentions, caller=caller, inline=inline, cards=cards
    )
    if thread.state == AgentThread.State.RUNNING:
        return {"status": "steered", "seq": event.seq}
    (start or start_turn)(thread)
    return {"status": "started", "seq": event.seq}


def answer(caller: Caller, thread: AgentThread, text: str, *, start=None) -> dict:
    _gate(caller)
    thread.refresh_from_db()
    question = (
        AgentEvent.objects.filter(thread=thread, type="question")
        .order_by("-seq")
        .first()
    )
    pending = {e.payload.get("call_id") for e in store.pending_calls(thread)}
    if (
        thread.state != AgentThread.State.WAITING
        or question is None
        or (question.payload.get("call_id") not in pending)
    ):
        raise ServiceError(
            "not_waiting", "Mylo isn't waiting for an answer.", status=409
        )
    with transaction.atomic():
        store.append(
            thread, "answer", {"call_id": question.payload["call_id"], "text": text}
        )
        store.append(
            thread,
            "tool_result",
            {
                "call_id": question.payload["call_id"],
                "name": "ask_user",
                "status": "ok",
                "content": f"The person answered: {text}",
            },
        )
        store.set_state(thread, AgentThread.State.IDLE)
    (start or start_turn)(thread)
    return {"status": "started"}


def cancel(caller: Caller, thread: AgentThread) -> dict:
    stream.request_cancel(thread.pk)
    task_id = (thread.settings or {}).get("task_id")
    if task_id:
        try:
            from config.celery import app

            app.control.revoke(task_id)
        except Exception:  # the cancel flag already stops the loop
            pass
    if not thread.shared:
        # A shared thread's queue is other people's questions: Stop ends
        # only the running turn, and the next question gets its own.
        AgentQueuedMessage.objects.filter(thread=thread).delete()
    return {"status": "cancelling"}


def start_turn(thread: AgentThread) -> None:
    """Run the turn in the worker. The thread is marked running first, so a
    message sent before the worker picks it up is queued, not lost."""
    from . import tasks

    store.set_state(thread, AgentThread.State.RUNNING)
    stream.clear_cancel(thread.pk)
    result = tasks.run_turn.delay(str(thread.pk))
    data = dict(thread.settings or {})
    data["task_id"] = getattr(result, "id", "") or ""
    AgentThread.objects.filter(pk=thread.pk).update(settings=data)


def check_view(caller: Caller, view: str) -> str:
    """``activity`` (default) for everyone; ``raw`` — thinking, arguments,
    results — only for the CLI and staff."""
    from .activity import VIEWS

    if view not in VIEWS:
        raise ServiceError(
            "bad_view", f"Unknown view {view!r}.", f"Use one of {', '.join(VIEWS)}."
        )
    if view == "raw" and not (
        caller.surface == "cli" or getattr(caller.user, "is_staff", False)
    ):
        raise ServiceError(
            "raw_view_staff_only",
            "The raw view is for staff.",
            "Leave out view, or use view=activity.",
            status=403,
        )
    return view


def _own(caller: Caller, thread: AgentThread) -> None:
    """Only the owner reads a thread here. A shared thread has none: it is
    read only where it lives (the Discord adapter), never through the web."""
    if (
        thread.shared
        or caller.user is None
        or thread.user_id != getattr(caller.user, "pk", None)
    ):
        raise ServiceError("not_found", "No such conversation.", status=404)


def subscribe(
    caller: Caller,
    thread: AgentThread,
    *,
    after: int = 0,
    view: str = "activity",
    **kw,
):
    _own(caller, thread)
    return stream.follow(thread, after=after, view=check_view(caller, view), **kw)


def thread_events(
    caller: Caller, thread: AgentThread, *, after: int = 0, view: str = "activity"
) -> list[dict]:
    """Stored events after ``after`` in the requested view, each as
    ``{seq, type, ts, payload}``."""
    from .activity import Projector

    _own(caller, thread)
    view = check_view(caller, view)
    projector = Projector(thread) if view == "activity" else None
    out = []
    for event in store.events(thread, after=after):
        message = stream.event_message(event)
        if projector is not None:
            message = projector.project(message)
            if message is None:
                continue
        out.append(
            {
                "seq": message["id"],
                "type": message["type"],
                "ts": message["ts"],
                "payload": message.get("payload", {}),
            }
        )
    return out


# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #


def export(caller: Caller, thread: AgentThread, *, fmt: str = "json"):
    """The log as JSON, or a readable transcript. References are re-checked:
    anything the caller can no longer see is shown as unavailable."""
    _own(caller, thread)
    events = store.events(thread)
    visible: dict[int, str | None] = {}
    for entry in refs.thread_refs(thread):
        info = refs.resolve(caller, entry["ref"])
        visible[entry["n"]] = info.title if info else None
    if fmt == "json":
        return {
            "thread": {
                "id": str(thread.pk),
                "title": thread.title,
                "purpose": thread.purpose,
                "scope": thread.scope_kind,
                "created_at": thread.created_at.isoformat(),
            },
            "references": [
                {"n": n, "title": t or "(no longer available)"}
                for n, t in visible.items()
            ],
            "events": [_redact(e, visible) for e in events],
        }
    lines = [f"# {thread.title or 'Conversation with Mylo'}", ""]
    for e in events:
        if e.type == "user":
            lines += [f"**You:** {e.payload.get('text', '')}", ""]
        elif e.type == "assistant" and e.payload.get("final"):
            lines += [
                f"**Mylo:** {_resolve_cites(e.payload.get('text', ''), visible)}",
                "",
            ]
        elif e.type == "question":
            lines += [f"**Mylo asked:** {e.payload.get('question', '')}", ""]
        elif e.type == "answer":
            lines += [f"**You answered:** {e.payload.get('text', '')}", ""]
    if visible:
        lines += ["## References", ""]
        lines += [f"- #{n}: {t or '(no longer available)'}" for n, t in visible.items()]
    return "\n".join(lines) + "\n"


def _redact(event, visible) -> dict:
    payload = dict(event.payload)
    if event.type == "tool_result" and payload.get("refs"):
        if any(visible.get(n) is None for n in payload["refs"]):
            payload["content"] = (
                "(this result refers to something you can no longer see)"
            )
    if event.type == "user" and payload.get("cards"):
        payload["cards"] = [
            c if visible.get(_card_n(c)) is not None else "(no longer available)"
            for c in payload["cards"]
        ]
    return {
        "seq": event.seq,
        "type": event.type,
        "ts": event.ts.isoformat(),
        "payload": payload,
    }


def _card_n(card: str) -> int | None:
    m = re.match(r"#(\d+)", card)
    return int(m.group(1)) if m else None


def _resolve_cites(text: str, visible) -> str:
    def sub(m):
        title = visible.get(int(m.group(1)))
        return f"#{m.group(1)} ({title})" if title else f"#{m.group(1)} (unavailable)"

    return re.sub(r"#(\d+)\b", sub, text)


# --------------------------------------------------------------------------- #
# Policy and preferences
# --------------------------------------------------------------------------- #


def get_preferences(user) -> AgentPreference:
    pref, _ = AgentPreference.objects.get_or_create(user=user)
    return pref


def learning_enabled(user) -> bool:
    from apps.ambient.read import listening_enabled

    return listening_enabled(user, "agent_chat")


def set_preferences(user, **changes) -> AgentPreference:
    """Chat, Discord and group switches live here; learning is ambient's
    consent row for Mylo chat, written through ambient's service."""
    from apps.ambient.service import set_agent_chat_listening

    pref = get_preferences(user)
    was_learning = learning_enabled(user)
    fields = []
    for key in ("chat_enabled", "discord_allowed"):
        if key in changes:
            setattr(pref, key, bool(changes[key]))
            fields.append(key)
    if "groups_off" in changes:
        pref.groups_off = sorted({str(v) for v in changes["groups_off"] or []})
        fields.append("groups_off")
    if fields:
        pref.save(update_fields=[*fields, "updated_at"])
    if "learning" in changes:
        set_agent_chat_listening(user, on=bool(changes["learning"]))
    if learning_enabled(user) and not was_learning:
        # Turning learning back on marks existing chats as read: no flood of
        # questions about old conversations.
        for t in AgentThread.objects.filter(user=user):
            AgentThread.objects.filter(pk=t.pk).update(learned_seq=store.last_seq(t))
    return pref


def _can_manage(user, kind: str, org) -> bool:
    from apps.accounts.permissions import (
        user_can_manage_department,
        user_can_manage_lab,
    )

    if kind == "lab":
        return user_can_manage_lab(user, org)
    return user_can_manage_department(user, org)


def get_org_policy(user, kind: str, org) -> AgentOrgPolicy | None:
    if permissions.role_in(user, kind, org) is None:
        raise ServiceError("not_found", f"No such {kind}.", status=404)
    return AgentOrgPolicy.objects.filter(**{kind: org}).first()


def set_org_policy(user, kind: str, org, **changes) -> AgentOrgPolicy:
    """Owners and admins narrow what members can use. Never wider than the
    instance; never an on/off switch for the agent (D-5). Audited."""
    from apps.accounts.services import record_audit_event

    if not _can_manage(user, kind, org):
        raise ServiceError(
            "forbidden",
            f"Only the {kind}'s owners and admins can change this.",
            status=403,
        )
    policy, _ = AgentOrgPolicy.objects.get_or_create(**{kind: org})
    before = _policy_dict(policy)
    if "groups_off" in changes:
        policy.groups_off = sorted({str(g) for g in changes["groups_off"] or []})
    if "discord_channels_off" in changes:
        policy.discord_channels_off = sorted(
            {str(c) for c in changes["discord_channels_off"] or []}
        )
    if "max_risk" in changes:
        risk = str(changes["max_risk"])
        order = ("read", "write", "external", "destructive")
        if risk not in order or order.index(risk) > order.index(config.get("max_risk")):
            raise ServiceError(
                "too_wide", "An organization can't allow more than the instance does."
            )
        policy.max_risk = risk
    if "members_inform_org" in changes:
        policy.members_inform_org = bool(changes["members_inform_org"])
    if "discord_guests" in changes:
        from tools._framework.agentspec import GUEST_LEVELS

        level = str(changes["discord_guests"]).replace("-", "_")
        if level not in GUEST_LEVELS:
            raise ServiceError(
                "bad_guest_level",
                f"Unknown guest level {level!r}.",
                f"Use one of {', '.join(GUEST_LEVELS)}.",
            )
        policy.discord_guests = level
    policy.updated_by = user
    policy.save()
    record_audit_event(
        actor=user,
        action="agent.org_policy",
        target_type=kind,
        target_id=str(org.pk),
        metadata={"before": before, "after": _policy_dict(policy)},
    )
    return policy


def _policy_dict(policy: AgentOrgPolicy) -> dict:
    return {
        "groups_off": policy.groups_off,
        "discord_channels_off": policy.discord_channels_off,
        "max_risk": policy.max_risk,
        "members_inform_org": policy.members_inform_org,
        "discord_guests": policy.discord_guests,
    }


def guest_ceiling() -> str:
    """The host's most a guest may be told (``[tools.agent]
    discord_guest_level``); ``off`` unless guests may ask at all."""
    if config.get("discord_access") != "public":
        return "off"
    return str(config.get("discord_guest_level") or "full")


def guest_level_in_force(kind: str, org) -> str:
    """The lower of the host's ceiling and the org's own setting."""
    from tools._framework.agentspec import guest_rank

    ceiling = guest_ceiling()
    row = AgentOrgPolicy.objects.filter(**{kind: org}).first()
    own = row.discord_guests if row else "full"
    return own if guest_rank(own) < guest_rank(ceiling) else ceiling


def catalog_view(caller: Caller) -> list[dict]:
    """What the UI may show: every function, whether it is available here and,
    if not, why. Built by the same function as the model's catalog."""
    gate = permissions.may_chat(caller)
    if not gate.allowed:
        return [
            {
                "name": "*",
                "group": "*",
                "summary": "",
                "allowed": False,
                **gate.as_dict(),
            }
        ]
    out = []
    for fn, d in permissions.catalog(caller):
        out.append(
            {
                "name": fn.name,
                "group": fn.group,
                "summary": fn.summary,
                "allowed": d.allowed,
                "layer": d.layer,
                "code": d.code,
                "detail": d.detail,
                "fix": d.fix,
            }
        )
    return sorted(out, key=lambda r: (r["group"], r["name"]))


def status() -> dict:
    """``{"model": {name, label, location}}``, or ``model: None`` with why."""
    from .llmcall import model_info

    info = model_info()
    if info:
        return {"model": info}
    return {
        "model": None,
        "code": "no_model",
        "detail": "No language model is configured on this instance.",
        "fix": "The operator sets LLM_MODEL (or tools.agent.model).",
    }


def discord_surface():
    """The Discord surface (``surfaces/discord.py``) for the bot, which reaches
    the agent only through ``services.get("agent")`` (plan D)."""
    from .surfaces import discord

    return discord


__all__ = [
    "Audience",
    "Caller",
    "Scope",
    "ServiceError",
    "answer",
    "cancel",
    "catalog_view",
    "check_view",
    "create_thread",
    "delete_thread",
    "discord_surface",
    "export",
    "fork_thread",
    "get_org_policy",
    "get_preferences",
    "get_thread",
    "list_threads",
    "scope_from",
    "send",
    "set_org_policy",
    "set_preferences",
    "status",
    "subscribe",
    "thread_events",
    "update_thread",
]
