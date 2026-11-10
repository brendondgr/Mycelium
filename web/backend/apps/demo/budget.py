"""The demo's Mylo question budget: per visitor, per network address, per day.

Three caps, each from ``[demo]`` in ``mycelium.toml``:

* ``questions_per_visitor`` — counted by the visitor's signed cookie, over
  :data:`VISITOR_WINDOW`;
* ``questions_per_ip_per_day`` — the backstop for a cleared cookie;
* ``questions_per_day`` — every visitor together, which is what bounds the
  model bill. ``0`` turns Mylo off in the demo.

The counts live in the database, not the cache: the default cache is per
process, and a budget each server process kept on its own would be no budget.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import DemoQuestion, DemoWorld

VISITOR_WINDOW = timedelta(days=30)


@dataclass(frozen=True)
class Left:
    visitor: int
    ip: int
    day: int

    @property
    def remaining(self) -> int:
        return max(0, min(self.visitor, self.ip, self.day))


@dataclass(frozen=True)
class Refusal:
    code: str
    detail: str
    fix: str


def _start_of_day():
    now = timezone.localtime()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def left(ctx) -> Left:
    """What ``ctx`` (a :class:`~apps.demo.middleware.DemoContext`) may still ask."""
    since_window = timezone.now() - VISITOR_WINDOW
    today = _start_of_day()
    rows = DemoQuestion.objects
    used_visitor = rows.filter(
        visitor=ctx.visitor, created_at__gte=since_window
    ).count()
    used_ip = rows.filter(ip_hash=ctx.ip_hash, created_at__gte=today).count()
    used_day = rows.filter(created_at__gte=today).count()
    return Left(
        visitor=int(settings.DEMO_QUESTIONS_PER_VISITOR) - used_visitor,
        ip=int(settings.DEMO_QUESTIONS_PER_IP_PER_DAY) - used_ip,
        day=int(settings.DEMO_QUESTIONS_PER_DAY) - used_day,
    )


def refusal(ctx, current: Left | None = None) -> Refusal | None:
    """Why ``ctx`` may not ask now, or ``None`` when it may."""
    current = current or left(ctx)
    if int(settings.DEMO_QUESTIONS_PER_DAY) <= 0:
        return Refusal(
            "demo_chat_off",
            "Mylo isn't answering questions in this demo.",
            "Sign up to ask Mylo about your own work.",
        )
    if current.visitor <= 0:
        return Refusal(
            "demo_question_used",
            "That was your demo question.",
            "Sign up to keep asking Mylo, about your own lab.",
        )
    if current.ip <= 0 or current.day <= 0:
        return Refusal(
            "demo_closed_today",
            "Mylo has answered all of today's demo questions.",
            "Come back tomorrow, or sign up to ask about your own lab.",
        )
    return None


def take(ctx, *, thread_id=None) -> DemoQuestion | Refusal:
    """Spend one question for ``ctx``, or say why not.

    The demo world's row is locked for the check-and-insert, so two questions
    sent at once cannot both squeeze into the last slot (on Postgres; SQLite
    serialises writes anyway).
    """
    with transaction.atomic():
        DemoWorld.objects.select_for_update().filter(key="default").first()
        why = refusal(ctx)
        if why is not None:
            return why
        DemoQuestion.objects.filter(
            created_at__lt=timezone.now() - VISITOR_WINDOW
        ).delete()
        return DemoQuestion.objects.create(
            visitor=ctx.visitor, ip_hash=ctx.ip_hash, thread_id=thread_id
        )


def refund(question: DemoQuestion | None) -> None:
    """Give back a question whose send failed before Mylo was asked."""
    if isinstance(question, DemoQuestion) and question.pk:
        question.delete()


def summary(ctx) -> dict:
    """The ``demo`` block the app reads from ``/me`` and the status route."""
    current = left(ctx)
    why = refusal(ctx, current)
    return {
        "questions_left": 0 if why else current.remaining,
        "question_max_chars": int(settings.DEMO_QUESTION_MAX_CHARS),
        "refusal": None
        if why is None
        else {"code": why.code, "detail": why.detail, "fix": why.fix},
    }
