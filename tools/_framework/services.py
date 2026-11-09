"""Reach a loaded tool without importing it statically.

The platform imports no tool (the boundary ratchet holds that). A surface such
as the Discord gateway still needs the agent when it is there, and a polite
refusal when it is not:

    from tools._framework import services
    agent = services.get("agent")
    if agent is None:
        return "Mylo chat isn't enabled on this instance."

Only a tool's declared ``service`` export is ever returned, and only while the
tool is ``LOADED``.
"""

from __future__ import annotations

import importlib
from types import ModuleType


def _report():
    from django.conf import settings

    return getattr(settings, "TOOLS_REPORT", None)


_classes: dict[int, dict] = {}


def _classes_of(report) -> dict:
    """Declaration classes, read once per load report (discovery reads files)."""
    from . import loader

    key = id(report)
    if key not in _classes:
        _classes.clear()
        _classes[key] = loader.tool_classes(report)
    return _classes[key]


def get(name: str, export: str = "service") -> ModuleType | None:
    """The tool's ``export`` module (``service`` by default), or ``None``."""
    from . import loader

    report = _report()
    if report is None or report.state(name) != loader.LOADED:
        return None
    cls = _classes_of(report).get(name)
    if cls is None or export not in cls.exports:
        return None
    return importlib.import_module(f"{report.tools[name].package}.{export}")


def agent_contributions() -> list[tuple[str, str]]:
    """``(tool name, module path)`` for every loaded tool that declares
    ``agent``, in dependency order."""

    report = _report()
    if report is None:
        return []
    classes = _classes_of(report)
    return [
        (name, classes[name].agent)
        for name in report.loaded()
        if getattr(classes.get(name), "agent", None)
    ]
