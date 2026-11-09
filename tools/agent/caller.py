"""Who is asking, from where, about what, and who will see the answer.

Only a surface adapter (``surfaces/``) builds a :class:`Caller`, and only from
an identity it has authenticated. Nothing else decides access: the gate in
``permissions.py`` reads these facts and nothing the model has read.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from tools._framework.agentspec import WIDTHS


@dataclass(frozen=True)
class Scope:
    """Where the thread lives: ``personal`` or a lab, department or project."""

    kind: str = "personal"
    obj: Any = None

    @property
    def lab(self):
        if self.kind == "lab":
            return self.obj
        if self.kind == "project" and self.obj is not None:
            return self.obj.scope_lab
        return None

    @property
    def department(self):
        if self.kind == "department":
            return self.obj
        if self.kind == "project" and self.obj is not None:
            return self.obj.scope_department or (
                self.obj.scope_lab.department if self.obj.scope_lab_id else None
            )
        if self.kind == "lab" and self.obj is not None:
            return self.obj.department
        return None

    @property
    def project(self):
        return self.obj if self.kind == "project" else None

    def label(self) -> str:
        if self.kind == "personal" or self.obj is None:
            return "personal"
        return f"{self.kind}:{getattr(self.obj, 'slug', None) or self.obj.pk}"


@dataclass(frozen=True)
class Audience:
    """Who will see the reply. ``width`` is one of ``WIDTHS``."""

    width: str = "person"
    obj: Any = None

    def __post_init__(self) -> None:
        if self.width not in WIDTHS:
            raise ValueError(f"unknown audience width {self.width!r}")


@dataclass(frozen=True)
class Caller:
    user: Any
    surface: str
    scope: Scope = field(default_factory=Scope)
    audience: Audience = field(default_factory=Audience)
    thread_id: UUID | None = None
    via: Mapping[str, Any] = field(default_factory=dict)

    @property
    def thread(self):
        from .models import AgentThread

        if self.thread_id is None:
            return None
        return AgentThread.objects.filter(pk=self.thread_id).first()


def scope_of_thread(thread) -> Scope:
    return Scope(kind=thread.scope_kind, obj=thread.scope_object)


def for_thread(
    thread,
    *,
    surface: str | None = None,
    audience: Audience | None = None,
    via: Mapping[str, Any] | None = None,
) -> Caller:
    """The caller for the owner of ``thread`` (only its owner may use it)."""
    return Caller(
        user=thread.user,
        surface=surface or thread.surface,
        scope=scope_of_thread(thread),
        audience=audience or Audience("person"),
        thread_id=thread.pk,
        via=dict(via or {}),
    )
