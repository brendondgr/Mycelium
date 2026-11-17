"""The append-only event log. Every write goes through :func:`append`, which
numbers the event under a row lock on the thread and publishes it to the live
stream once the transaction commits."""

from __future__ import annotations

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from .models import AgentEvent, AgentThread


def append(
    thread: AgentThread, type_: str, payload: dict | None = None, *, tokens: int = 0
) -> AgentEvent:
    if type_ not in AgentEvent.TYPES:
        raise ValueError(f"unknown event type {type_!r}")
    with transaction.atomic():
        AgentThread.objects.select_for_update().filter(pk=thread.pk).first()
        last = (
            AgentEvent.objects.filter(thread=thread).aggregate(m=Max("seq"))["m"] or 0
        )
        event = AgentEvent.objects.create(
            thread=thread,
            seq=last + 1,
            type=type_,
            payload=payload or {},
            tokens=tokens,
        )
        AgentThread.objects.filter(pk=thread.pk).update(
            last_activity_at=timezone.now(), updated_at=timezone.now()
        )
        transaction.on_commit(lambda: _publish(event))
    return event


def _publish(event: AgentEvent) -> None:
    from . import stream

    stream.publish_event(event)


def events(thread: AgentThread, *, after: int = 0, upto: int | None = None):
    qs = AgentEvent.objects.filter(thread=thread, seq__gt=after)
    if upto is not None:
        qs = qs.filter(seq__lte=upto)
    return list(qs.order_by("seq"))


def last_seq(thread: AgentThread) -> int:
    return AgentEvent.objects.filter(thread=thread).aggregate(m=Max("seq"))["m"] or 0


def set_state(thread: AgentThread, state: str, *, detail: str = "") -> None:
    if thread.state == state:
        return
    AgentThread.objects.filter(pk=thread.pk).update(state=state)
    thread.state = state
    append(thread, "state", {"state": state, "detail": detail})


def save_setting(thread: AgentThread, key: str, change):
    """Set one key of the thread's settings to ``change(current value)``,
    under the row's lock, and return the new value.

    Several things write a thread's settings while a turn runs: the calls of
    one step run side by side, the loop puts results away to save room, the
    request that started the turn records its task. Whoever wrote the whole
    settings back from the copy it read would undo what another wrote
    meanwhile: the references a list had just numbered were lost this way, and
    the next call on ``#2`` was refused as not visible. So every writer changes
    its own key here, and nothing else."""
    with transaction.atomic():
        row = AgentThread.objects.select_for_update().get(pk=thread.pk)
        data = dict(row.settings or {})
        data[key] = change(data.get(key))
        AgentThread.objects.filter(pk=row.pk).update(settings=data)
    thread.settings = data
    return data[key]


def pending_calls(thread: AgentThread) -> list[AgentEvent]:
    """``tool_call`` events with no ``tool_result`` yet (a crash mid-step)."""
    evs = events(thread)
    done = {e.payload.get("call_id") for e in evs if e.type == "tool_result"}
    return [
        e for e in evs if e.type == "tool_call" and e.payload.get("call_id") not in done
    ]


def fork(thread: AgentThread, seq: int, *, title: str = "") -> AgentThread:
    """A new thread holding events ``1..seq``. A trailing step whose calls
    have no results is dropped, so the fork starts from a settled state."""
    evs = events(thread, upto=seq)
    while evs:
        results = {e.payload.get("call_id") for e in evs if e.type == "tool_result"}
        tail = evs[-1]
        unresolved = [
            e
            for e in evs
            if e.type == "tool_call" and e.payload.get("call_id") not in results
        ]
        if unresolved:
            first = min(e.seq for e in unresolved)
            # drop from the assistant event that issued them
            issuing = [e for e in evs if e.type == "assistant" and e.seq < first]
            cut = issuing[-1].seq if issuing else first
            evs = [e for e in evs if e.seq < cut]
            continue
        if tail.type in ("state",):
            evs = evs[:-1]
            continue
        break
    with transaction.atomic():
        child = AgentThread.objects.create(
            user=thread.user,
            scope_kind=thread.scope_kind,
            scope_lab=thread.scope_lab,
            scope_department=thread.scope_department,
            scope_project=thread.scope_project,
            surface=thread.surface,
            title=title or (f"{thread.title} (fork)" if thread.title else ""),
            purpose=thread.purpose,
            settings=dict(thread.settings or {}),
            parent=thread,
            fork_seq=seq,
            learned_seq=len(evs),
        )
        AgentEvent.objects.bulk_create(
            AgentEvent(
                thread=child, seq=i, type=e.type, payload=e.payload, tokens=e.tokens
            )
            for i, e in enumerate(evs, start=1)
        )
    return child
