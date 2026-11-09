"""The learning pass: quiet threads become observations (D-2, D-3).

A thread idle for ``learning_idle_minutes`` with new events since it was last
read, whose owner has not opted out, is handed to ambient through the
``agent.thread_quiet`` event. Only the person's own messages are sent; Mylo's
replies, function results and paper text never are, so Mylo cannot learn from
its own guesses or from what it read. A failed hand-off backs off from five
minutes, doubling, to six hours.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.db.models import F
from django.utils import timezone

from tools._framework import events as bus

from . import config, store
from .events import THREAD_QUIET
from .memory_after import learning_on_for
from .models import AgentThread

logger = logging.getLogger(__name__)

BACKOFF_START = timedelta(minutes=5)
BACKOFF_MAX = timedelta(hours=6)


def due_threads(now=None):
    now = now or timezone.now()
    idle = timedelta(minutes=int(config.get("learning_idle_minutes")))
    # A shared thread (Discord, plan D) is never read here: a question in a
    # shared place is learned from only under Discord listening consent, and a
    # guest's never (S-7).
    rows = AgentThread.objects.filter(
        last_activity_at__lte=now - idle, shared=False
    ).exclude(state="running")
    rows = rows.filter(learn_after__isnull=True) | rows.filter(learn_after__lte=now)
    return rows.select_related("user").order_by("last_activity_at")


def _messages(thread) -> list[dict]:
    return [
        {"seq": e.seq, "ts": e.ts.isoformat(), "text": e.payload.get("text", "")}
        for e in store.events(thread, after=thread.learned_seq)
        if e.type == "user" and e.payload.get("text")
    ]


def run_pass(*, now=None, limit: int = 200) -> int:
    if not config.get("learning"):
        return 0
    handed = 0
    for thread in due_threads(now)[:limit]:
        last = store.last_seq(thread)
        if last <= thread.learned_seq:
            continue
        if not learning_on_for(thread.user):
            # opted out: nothing is recorded, now or later
            AgentThread.objects.filter(pk=thread.pk).update(learned_seq=last)
            continue
        messages = _messages(thread)
        if not messages:
            AgentThread.objects.filter(pk=thread.pk).update(learned_seq=last)
            continue
        try:
            bus.publish(THREAD_QUIET, raise_errors=True, **payload(thread, messages))
        except Exception:
            logger.exception("agent learning: hand-off failed for %s", thread.pk)
            failures = thread.learn_failures + 1
            delay = min(BACKOFF_START * (2 ** (failures - 1)), BACKOFF_MAX)
            AgentThread.objects.filter(pk=thread.pk).update(
                learn_failures=F("learn_failures") + 1,
                learn_after=timezone.now() + delay,
            )
            continue
        AgentThread.objects.filter(pk=thread.pk).update(
            learned_seq=last, learn_failures=0, learn_after=None
        )
        handed += 1
    return handed


def payload(thread, messages) -> dict:
    return {
        "thread_id": str(thread.pk),
        "user_id": thread.user_id,
        "scope": thread.scope_kind,
        "lab_id": thread.scope_lab_id,
        "department_id": str(thread.scope_department_id)
        if thread.scope_department_id
        else None,
        "project_id": str(thread.scope_project_id) if thread.scope_project_id else None,
        "messages": messages,
        "title": thread.title,
        "purpose": thread.purpose,
    }
