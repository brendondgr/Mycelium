"""The agent's settings, read through their Django names so tests can use
``override_settings`` (``AGENT_MAX_STEPS`` and so on)."""

from __future__ import annotations

from django.conf import settings

from .tool import AgentTool


def values() -> dict:
    out = {}
    for setting in AgentTool.settings:
        out[setting.key] = getattr(settings, setting.django, setting.default)
    return out


def get(key: str):
    for setting in AgentTool.settings:
        if setting.key == key:
            return getattr(settings, setting.django, setting.default)
    raise KeyError(key)
