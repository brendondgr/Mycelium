"""The Django side of a tool: the AppConfig every tool's ``apps.py`` uses."""

from __future__ import annotations

import importlib

from django.apps import AppConfig

from . import discovery, events


class ToolAppConfig(AppConfig):
    """Base for ``tools/<name>/apps.py``.

    Registers the tool's declared event subscriptions when Django is ready —
    and Django only installs loaded tools, so only they ever subscribe.
    """

    default_auto_field = "django.db.models.BigAutoField"

    def tool_class(self):
        package = self.name
        module = importlib.import_module(f"{package}.tool")
        for obj in vars(module).values():
            if (
                isinstance(obj, type)
                and obj.__module__ == module.__name__
                and getattr(obj, "name", None) == package.rsplit(".", 1)[-1]
            ):
                return obj
        raise LookupError(f"{package}.tool declares no Tool")

    def ready(self) -> None:
        for event, ref in self.tool_class().subscribes.items():
            events.subscribe(event, ref)


__all__ = ["ToolAppConfig", "discovery"]
