"""The subprocess half of the import script (see :mod:`tools._framework.loader`).

Run as ``python -m tools._framework.probe`` with ``MYCELIUM_TOOLS_PROBE`` set
to a comma-separated tool list. settings.py installs exactly those tools; this
module then starts Django, imports every module a running process would import
from them (models, apps, the declared exports, URL modules, Celery tasks,
management commands) and runs each health check. Exit 0 means every listed
tool can run. Anything else prints one ``PROBE-FAILED <tool>: <error>`` line.

Nothing here touches the database.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys
import traceback


def _summary(exc: BaseException) -> str:
    text = "".join(traceback.format_exception_only(type(exc), exc)).strip()
    return text.replace("\n", " ")[:600]


def _culprit(exc: BaseException, names: list[str]) -> str:
    """The tool whose own code raised: the innermost traceback frame inside a
    tool's folder. Falls back to the probed names when no frame is."""
    from tools._framework import discovery

    roots = {}
    for directory in {discovery.tools_dir(), discovery.DEFAULT_TOOLS_DIR}:
        for folder in discovery.candidate_folders(directory):
            roots[str(folder.resolve()) + os.sep] = folder.name
    culprit = None
    for frame in traceback.extract_tb(exc.__traceback__):
        path = os.path.realpath(frame.filename)
        for root, name in roots.items():
            if path.startswith(root):
                culprit = name
    return culprit or (names[-1] if len(names) == 1 else ",".join(names))


def _resolve(ref: str):
    module, _, attr = ref.partition(":")
    return getattr(importlib.import_module(module), attr)


def main() -> int:
    names = [n for n in os.environ.get("MYCELIUM_TOOLS_PROBE", "").split(",") if n]
    try:
        import django

        django.setup()
    except BaseException as exc:  # noqa: BLE001 — report, never raise
        culprit = _culprit(exc, names)
        print(f"PROBE-FAILED {culprit}: Django could not start: {_summary(exc)}")
        return 1

    from tools._framework import discovery

    found = discovery.discover(discovery.tools_dir())
    for name in names:
        item = found[name]
        cls = item.cls
        modules = ["models", "apps", "tasks", *cls.exports]
        modules += [m.module for m in cls.mounts]
        commands_dir = item.path / "management" / "commands"
        if commands_dir.is_dir():
            modules += [
                f"management.commands.{p.stem}"
                for p in sorted(commands_dir.glob("*.py"))
                if p.stem != "__init__"
            ]
        try:
            for module in dict.fromkeys(modules):
                dotted = f"{item.package}.{module}"
                if importlib.util.find_spec(dotted) is None:
                    if module in [m.module for m in cls.mounts]:
                        raise ImportError(
                            f"declared mount module {dotted} does not exist"
                        )
                    continue
                importlib.import_module(dotted)
            for ref in cls.subscribes.values():
                _resolve(ref)
            if cls.health:
                _resolve(cls.health)()
        except BaseException as exc:  # noqa: BLE001
            print(f"PROBE-FAILED {_culprit(exc, [name])}: {_summary(exc)}")
            return 1
    print("PROBE-OK " + ",".join(names))
    return 0


if __name__ == "__main__":
    sys.exit(main())
