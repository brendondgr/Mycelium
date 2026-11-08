"""Finding tools on disk. Standard library only.

A tool is a folder under the tools directory whose name does not start with
``_`` and that contains a ``tool.py`` declaring exactly one :class:`Tool`
subclass named after the folder. Discovery imports nothing but those
``tool.py`` files, which may import nothing but the standard library and
:mod:`tools._framework.spec` — so it is safe to run before Django starts, on the
host, and in the stdlib-only configuration layer.
"""

from __future__ import annotations

import importlib
import os
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path

from .spec import Tool

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TOOLS_DIR = REPO_ROOT / "tools"

#: App labels the platform owns; a tool may not take one.
PLATFORM_LABELS = frozenset(
    {
        "admin",
        "auth",
        "contenttypes",
        "sessions",
        "messages",
        "staticfiles",
        "postgres",
        "rest_framework",
        "corsheaders",
        "tools",
        "core",
        "accounts",
        "research",
        "billing",
        "integrations",
        "adminpanel",
        "ambient",
        "knowledge",
        "collab",
    }
)


@dataclass
class Discovered:
    name: str
    path: Path
    package: str  # dotted package of the tool, e.g. "tools.retrieval"
    cls: type[Tool] | None = None
    error: str | None = None


def tools_dir(environ: dict | None = None) -> Path:
    env = os.environ if environ is None else environ
    override = (env.get("MYCELIUM_TOOLS_DIR") or "").strip()
    return Path(override).resolve() if override else DEFAULT_TOOLS_DIR


def package_root(directory: Path) -> tuple[Path, str]:
    """The ``sys.path`` entry and dotted package for a tools directory.

    Walks up while each folder is a package, so ``tools/`` is ``tools`` and a
    fixtures folder inside it is ``tools._framework.tests.fixtures``.
    """
    directory = directory.resolve()
    parts = [directory.name]
    parent = directory.parent
    while (parent / "__init__.py").exists():
        parts.insert(0, parent.name)
        parent = parent.parent
    return parent, ".".join(parts)


def ensure_importable(directory: Path) -> str:
    entry, package = package_root(directory)
    if str(entry) not in sys.path:
        sys.path.append(str(entry))
    return package


def candidate_folders(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        p
        for p in directory.iterdir()
        if p.is_dir() and not p.name.startswith(("_", ".")) and (p / "tool.py").exists()
    )


def discover(directory: Path | None = None) -> dict[str, Discovered]:
    """Every tool folder, with its class or the reason it could not be read."""
    directory = tools_dir() if directory is None else directory
    package = ensure_importable(directory)
    found: dict[str, Discovered] = {}
    for folder in candidate_folders(directory):
        item = Discovered(folder.name, folder, f"{package}.{folder.name}")
        try:
            module = importlib.import_module(f"{item.package}.tool")
            classes = [
                obj
                for obj in vars(module).values()
                if isinstance(obj, type)
                and issubclass(obj, Tool)
                and obj is not Tool
                and obj.__module__ == module.__name__
            ]
            if len(classes) != 1:
                raise ValueError(
                    "tool.py must declare exactly one Tool subclass, "
                    f"found {len(classes)}"
                )
            cls = classes[0]
            problems = cls.validate()
            if cls.name != folder.name:
                problems.append(
                    f"class {cls.__name__} has name {cls.name!r} but lives in "
                    f"tools/{folder.name}/"
                )
            if cls.app_label() in PLATFORM_LABELS:
                problems.append(
                    f"app label {cls.app_label()!r} belongs to the platform"
                )
            if problems:
                raise ValueError("; ".join(problems))
            item.cls = cls
        except Exception as exc:  # noqa: BLE001 — any failure is the tool's state
            item.error = (
                "tool.py: "
                + "".join(traceback.format_exception_only(type(exc), exc)).strip()
            )
        found[item.name] = item
    labels: dict[str, str] = {}
    for item in found.values():
        if item.cls is None:
            continue
        label = item.cls.app_label()
        if label in labels:
            item.error = f"app label {label!r} is also used by tool {labels[label]!r}"
            item.cls = None
        else:
            labels[label] = item.name
    return found
