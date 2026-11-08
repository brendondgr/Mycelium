"""A small in-process event bus between tools.

A tool publishes the events it declares in its ``events.py`` and calls nobody;
whoever needs to react subscribes. This is what lets a foundation tool
(retrieval) stay ignorant of what is built on it: a dependent registers a
handler instead of the foundation importing the dependent.

Subscriptions come from a tool's ``subscribes`` mapping (registered by its
``ToolAppConfig.ready``, so only loaded tools ever receive anything) or from
platform code calling :func:`subscribe` in its own ``AppConfig.ready``.

Handlers run synchronously, in subscription order, inside the publisher's call.
A failing handler is logged and does not stop the others or the publisher; set
``raise_errors=True`` on :func:`publish` when the caller needs to know.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

_handlers: dict[str, list[Callable[..., Any]]] = {}


def subscribe(event: str, handler: Callable[..., Any] | str) -> None:
    if isinstance(handler, str):
        from .host import resolve_ref

        handler = resolve_ref(handler)
    bucket = _handlers.setdefault(event, [])
    if handler not in bucket:
        bucket.append(handler)


def unsubscribe(event: str, handler: Callable[..., Any]) -> None:
    bucket = _handlers.get(event, [])
    if handler in bucket:
        bucket.remove(handler)


def subscribers(event: str) -> list[Callable[..., Any]]:
    return list(_handlers.get(event, []))


def publish(event: str, *, raise_errors: bool = False, **payload: Any) -> int:
    """Call every handler of ``event``; return how many ran without error."""
    ok = 0
    for handler in subscribers(event):
        try:
            handler(**payload)
            ok += 1
        except Exception:
            logger.exception("event handler %r for %s failed", handler, event)
            if raise_errors:
                raise
    return ok
