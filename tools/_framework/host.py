"""How the platform takes in loaded tools. Called from settings.py and urls.py.

Everything a tool contributes — its Django app, its settings, its Beat entries,
its URL mount — is published only for tools the load report marks ``LOADED``.
A tool that is disabled, missing a dependency, or broken contributes nothing.
"""

from __future__ import annotations

import importlib
import os
from typing import Any

from . import loader
from .loader import LoadReport

#: The framework's own Django app (management command, ``/api/tools/``).
FRAMEWORK_APP = "tools._framework"


def boot(instance: Any) -> LoadReport:
    strict = bool(instance["tools.strict"])
    return loader.boot(
        tool_configs=instance.tools,
        strict=strict,
        config_warnings=list(instance.warnings),
    )


def installed_apps(report: LoadReport) -> list[str]:
    return [report.tools[name].package for name in report.loaded()]


def _values(cls, instance: Any) -> dict[str, Any]:
    """A loaded tool's resolved settings.

    A core tool taken from the default tools directory while another directory
    is being probed has no section in ``instance.tools``; it gets its defaults
    and environment overrides, resolved the same way.
    """
    cfg = instance.tools.get(cls.name)
    if cfg is None:
        from .config import resolve_tools

        cfg = resolve_tools(
            [cls], file_values={}, profile_values={}, environ=dict(os.environ)
        )[0][cls.name]
    return cfg.values


def publish_settings(
    namespace: dict[str, Any], report: LoadReport, instance: Any
) -> None:
    """Expose each loaded tool's settings under their Django names.

    A tool's own code reads ``tools._framework.settings_of(name)`` or the
    Django name; tests keep using ``override_settings`` on the Django name.
    """
    classes = loader.tool_classes(report)
    for name in report.loaded():
        cls = classes[name]
        values = _values(cls, instance)
        for setting in cls.settings:
            if setting.django:
                namespace[setting.django] = values[setting.key]


def beat_schedule(report: LoadReport, instance: Any) -> dict[str, dict]:
    from celery.schedules import crontab

    classes = loader.tool_classes(report)
    out: dict[str, dict] = {}
    for name in report.loaded():
        values = _values(classes[name], instance)
        for beat in classes[name].beat:
            kwargs = {
                key: (
                    values[value.removeprefix("setting:")]
                    if isinstance(value, str) and value.startswith("setting:")
                    else value
                )
                for key, value in beat.kwargs.items()
            }
            if beat.schedule != "crontab":
                raise ValueError(f"{name}: unsupported Beat schedule {beat.schedule!r}")
            out[beat.name] = {"task": beat.task, "schedule": crontab(**kwargs)}
    return out


def url_mounts(report: LoadReport) -> list[tuple[str, str, str | None]]:
    """``(prefix, dotted urls module, platform include it follows)`` per mount."""
    classes = loader.tool_classes(report)
    out = []
    for name in report.loaded():
        for mount in classes[name].mounts:
            out.append(
                (
                    mount.prefix,
                    f"{report.tools[name].package}.{mount.module}",
                    mount.after,
                )
            )
    return out


def splice_urls(platform: list, mounts: list[tuple[str, str, str | None]]) -> list:
    """Insert tool URL includes after the platform include each one names.

    URL order is resolution order, so a moved app's routes go exactly where
    its include used to be. A mount naming no anchor goes last.
    """
    from django.urls import include, path

    out = list(platform)
    for prefix, module, after in mounts:
        entry = path(prefix, include(module))
        index = len(out)
        if after:
            for i, existing in enumerate(out):
                urlconf = getattr(existing, "urlconf_name", None)
                name = getattr(urlconf, "__name__", urlconf)
                if name == after or getattr(existing, "_tool_module", None) == after:
                    index = i + 1
        entry._tool_module = module  # lets a later mount anchor on this one
        out.insert(index, entry)
    return out


def settings_of(name: str) -> dict[str, Any]:
    """A loaded tool's resolved settings, by key (for tool code)."""
    from django.conf import settings

    cfg = settings.INSTANCE.tools.get(name)
    if cfg is None:
        raise LookupError(f"tool {name!r} is not installed")
    return dict(cfg.values)


def is_loaded(name: str) -> bool:
    from django.conf import settings

    report = getattr(settings, "TOOLS_REPORT", None)
    return bool(report and report.state(name) == loader.LOADED)


def resolve_ref(ref: str):
    module, _, attr = ref.partition(":")
    return getattr(importlib.import_module(module), attr)


def probe_mode() -> bool:
    return bool(os.environ.get(loader.PROBE_ENV))
