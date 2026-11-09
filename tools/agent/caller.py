"""Who is asking, from where, about what, and who will see the answer.

Only a surface adapter (``surfaces/``) builds a :class:`Caller`, and only from
an identity it has authenticated. Nothing else decides access: the gate in
``permissions.py`` reads these facts and nothing the model has read.
"""

from __future__ import annotations

import re
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


#: Characters a speaker's name may not carry (Discord markup, mentions,
#: escapes), and its length cap. A name is a label, never an instruction.
_NAME_STRIP = re.compile(r"[@<>\\`|\x00-\x1f\x7f]")
NAME_CAP = 64


def clean_name(name: str) -> str:
    """A display name made safe to store and to show the model."""
    text = _NAME_STRIP.sub("", str(name or ""))
    text = " ".join(text.split())[:NAME_CAP].strip()
    return text or "someone"


@dataclass(frozen=True)
class Guest:
    """Someone in a bound Discord server with no Mycelium account (S-11).

    Being in the server is their permission; they stand where a ``member`` of
    the place's lab or department stands, narrowed by the guest level."""

    discord_user_id: str
    name: str = "someone"


@dataclass(frozen=True)
class Caller:
    #: The Mycelium account, or ``None`` for a guest.
    user: Any
    surface: str
    scope: Scope = field(default_factory=Scope)
    audience: Audience = field(default_factory=Audience)
    thread_id: UUID | None = None
    via: Mapping[str, Any] = field(default_factory=dict)
    guest: Guest | None = None

    @property
    def is_guest(self) -> bool:
        return self.user is None and self.guest is not None

    @property
    def name(self) -> str:
        if self.user is not None:
            return clean_name(self.user.get_full_name() or self.user.username)
        if self.guest is not None:
            return clean_name(self.guest.name)
        return "someone"

    def speaker(self) -> dict:
        """Who is speaking, as stored on the ``user`` event (plan D)."""
        discord_id = str(self.via.get("discord_user_id") or "")
        if self.is_guest:
            return {
                "kind": "guest",
                "user_id": None,
                "discord_user_id": self.guest.discord_user_id,
                "name": self.name,
            }
        return {
            "kind": "member",
            "user_id": getattr(self.user, "pk", None),
            "discord_user_id": discord_id,
            "name": self.name,
        }

    def turn(self) -> dict:
        """From where and to whom: enough to rebuild this caller in the
        worker (:func:`for_turn`)."""
        return {
            "surface": self.surface,
            "audience_width": self.audience.width,
            "audience_ref": _org_ref(self.audience.obj),
            "via": {k: v for k, v in dict(self.via).items() if _plain(v)},
        }

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


def _plain(value) -> bool:
    return value is None or isinstance(value, str | int | float | bool)


def _org_ref(obj) -> str:
    """``lab:<slug>`` / ``department:<uuid>`` / ``project:<uuid>`` / ``""``."""
    if obj is None:
        return ""
    from apps.accounts.models import Department, Lab

    if isinstance(obj, Lab):
        return f"lab:{obj.slug}"
    if isinstance(obj, Department):
        return f"department:{obj.pk}"
    return f"project:{obj.pk}"


def _org_from_ref(ref: str):
    if not ref or ":" not in ref:
        return None
    from apps.accounts.models import Department, Lab
    from apps.research.models import Project

    kind, key = ref.split(":", 1)
    model = {"lab": Lab, "department": Department, "project": Project}.get(kind)
    if model is None:
        return None
    field_ = "slug" if kind == "lab" else "pk"
    return model.objects.filter(**{field_: key}).first()


def for_turn(thread, event=None) -> Caller:
    """The caller of one turn: who asked the newest ``user`` event, from where
    (plan D). A thread whose ``user`` event has no ``turn`` (every web and CLI
    thread) gets its owner, exactly as :func:`for_thread` builds it."""
    if event is None:
        from .models import AgentEvent

        event = (
            AgentEvent.objects.filter(thread=thread, type="user")
            .order_by("-seq")
            .first()
        )
    payload = (event.payload if event is not None else None) or {}
    turn, speaker = payload.get("turn"), payload.get("speaker") or {}
    if not turn:
        return for_thread(thread)
    from django.contrib.auth import get_user_model

    user, guest = None, None
    if speaker.get("kind") == "guest":
        guest = Guest(
            discord_user_id=str(speaker.get("discord_user_id") or ""),
            name=clean_name(speaker.get("name") or ""),
        )
    else:
        user = get_user_model().objects.filter(pk=speaker.get("user_id")).first()
        if user is None and thread.user_id is not None:
            user = thread.user
    width = turn.get("audience_width") or "person"
    return Caller(
        user=user,
        surface=turn.get("surface") or thread.surface,
        scope=scope_of_thread(thread),
        audience=Audience(width, _org_from_ref(turn.get("audience_ref") or "")),
        thread_id=thread.pk,
        via=dict(turn.get("via") or {}),
        guest=guest,
    )
