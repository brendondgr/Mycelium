"""The declaration vocabulary every ``tools/<name>/tool.py`` is written in.

Standard library only, and so is every ``tool.py`` (an AST test holds both).
That is what lets code that must not start Django — ``config/instance.py``, the
host CLI ``ops/mycelium`` and the nightly runner — read every tool's identity,
dependencies, settings and stages from the same class Django loads.

A tool *declares* here and *acts* elsewhere: anything that needs Django
(models, views, tasks, health checks, event handlers) is referenced by a dotted
string and imported only once the tool has been allowed to load.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, ClassVar

NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")

#: The nightly run's phases, in the order they run. A stage names one; inside a
#: phase, stages run in tool dependency order (platform first), then in the
#: order each tool declares them, adjusted by ``after``.
PHASES: tuple[str, ...] = (
    "collect",
    "rank",
    "remind",
    "prune",
    "alert",
    "announce",
    "brief",
    "deliver",
    "weekly",
)

_TRUE = {"1", "true", "yes", "on", "y", "ok"}
_FALSE = {"0", "false", "no", "off", "n", ""}

SETTING_KINDS = ("bool", "int", "float", "str", "list", "choice")


class SpecError(ValueError):
    """A tool's declaration is invalid; the message names the tool and the fix."""


@dataclass(frozen=True)
class Setting:
    """One per-tool configuration key.

    ``key`` is relative to the tool (``scan_window_days`` is configured as
    ``[tools.retrieval] scan_window_days = 3``). ``env`` is the environment
    variable that overrides it — kept identical to the name the setting had
    before it moved into a tool, so existing ``.env`` files keep working.
    ``django`` is the ``django.conf.settings`` attribute the value is published
    under while the tool is loaded, so call sites and ``override_settings`` in
    tests are unchanged by the move.
    """

    key: str
    kind: str
    default: Any
    help: str
    env: str | None = None
    django: str | None = None
    choices: tuple[str, ...] = ()
    #: A secret (an API key) is read from the environment only: it may not be
    #: set in mycelium.toml and is never written there or shown by the CLI.
    secret: bool = False

    def parse(self, raw: Any, *, source: str) -> Any:
        """Coerce a file or environment value to this setting's kind."""
        kind = self.kind
        try:
            if kind == "bool":
                if isinstance(raw, bool):
                    return raw
                text = str(raw).strip().lower()
                if text in _TRUE:
                    return True
                if text in _FALSE:
                    return False
                raise ValueError(raw)
            if kind == "int":
                if isinstance(raw, bool):
                    raise ValueError(raw)
                return int(str(raw).strip())
            if kind == "float":
                if isinstance(raw, bool):
                    raise ValueError(raw)
                return float(str(raw).strip())
            if kind == "list":
                if isinstance(raw, (list, tuple)):
                    return [str(item).strip() for item in raw if str(item).strip()]
                return [item.strip() for item in str(raw).split(",") if item.strip()]
            if kind == "choice":
                value = str(raw).strip()
                if value not in self.choices:
                    raise ValueError(raw)
                return value
            return str(raw)
        except ValueError:
            expected = (
                f"one of {', '.join(self.choices)}" if kind == "choice" else f"a {kind}"
            )
            raise SpecError(
                f"{self.key} from {source} is {raw!r}, which is not {expected}."
            ) from None


@dataclass(frozen=True)
class Stage:
    """One step of the nightly run, a management command run in the container."""

    command: str
    phase: str
    intro: str
    args: tuple[str, ...] = ()
    after: tuple[str, ...] = ()


@dataclass(frozen=True)
class Beat:
    """One Celery Beat entry, published only while the tool is loaded."""

    name: str
    task: str
    #: Only ``"crontab"`` today; ``kwargs`` are ``crontab()``'s. A value
    #: ``"setting:<key>"`` reads one of the tool's own settings.
    schedule: str = "crontab"
    kwargs: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Mount:
    """Where the tool's ``urls`` module is included.

    URL order is resolution order, so a mount names the platform include it
    must follow (``after``). A tool that inherited a URL prefix keeps it; the
    URL table is held unchanged by a golden test.
    """

    prefix: str
    module: str = "urls"
    after: str | None = None


class Tool:
    """Subclass once per tool, in ``tools/<name>/tool.py``.

    Class attributes only — no ``__init__``, no imports beyond this module and
    the standard library.
    """

    #: Folder and package name, ``[a-z][a-z0-9_]*``.
    name: ClassVar[str] = ""
    #: The Django app label. Defaults to ``name``; a tool that inherited an
    #: app's tables and migration history keeps that app's label.
    label: ClassVar[str | None] = None
    version: ClassVar[str] = "1"
    summary: ClassVar[str] = ""
    #: Other tools this one imports (only their ``exports``) or keys to.
    depends_on: ClassVar[tuple[str, ...]] = ()
    #: The platform cannot run without this tool. A core tool that fails to
    #: load stops startup in every mode instead of being set aside.
    core: ClassVar[bool] = False
    #: Modules of this tool that other tools and the platform may import.
    exports: ClassVar[tuple[str, ...]] = ("read", "service", "events")
    settings: ClassVar[tuple[Setting, ...]] = ()
    #: ``.env`` names this tool needs. A missing required secret blocks it.
    secrets: ClassVar[tuple[str, ...]] = ()
    stages: ClassVar[tuple[Stage, ...]] = ()
    beat: ClassVar[tuple[Beat, ...]] = ()
    mounts: ClassVar[tuple[Mount, ...]] = ()
    #: ``"package.module:function"`` — run after import, no database writes;
    #: raise to fail the tool.
    health: ClassVar[str | None] = None
    #: ``{"tool.event": "package.module:handler"}``.
    subscribes: ClassVar[dict[str, str]] = {}
    #: Dotted path of a module exporting ``FUNCTIONS`` (``AgentFunction``s)
    #: and ``REFS`` (``RefKind``s) for the Mylo agent, declared with
    #: ``tools._framework.agentspec``. Read only while this tool is loaded, so
    #: a disabled tool's functions never reach the agent's catalog.
    agent: ClassVar[str | None] = None

    # ------------------------------------------------------------------ #

    @classmethod
    def app_label(cls) -> str:
        return cls.label or cls.name

    @classmethod
    def validate(cls) -> list[str]:
        """Problems with this declaration; empty when it is sound."""
        problems: list[str] = []
        where = cls.__module__
        if not NAME_RE.match(cls.name or ""):
            problems.append(f"{where}: name {cls.name!r} must match [a-z][a-z0-9_]*.")
        for dep in cls.depends_on:
            if dep == cls.name:
                problems.append(f"{cls.name}: depends on itself.")
        seen: set[str] = set()
        for setting in cls.settings:
            if not NAME_RE.match(setting.key):
                problems.append(
                    f"{cls.name}.{setting.key}: a setting key is one plain name "
                    "([a-z][a-z0-9_]*)."
                )
            if setting.kind not in SETTING_KINDS:
                problems.append(
                    f"{cls.name}.{setting.key}: unknown kind {setting.kind!r}."
                )
            if setting.key in seen or setting.key == "enabled":
                problems.append(f"{cls.name}.{setting.key}: duplicate or reserved key.")
            seen.add(setting.key)
            if setting.secret and not setting.env:
                problems.append(f"{cls.name}.{setting.key}: a secret needs env=.")
            if setting.kind == "choice" and setting.default not in setting.choices:
                problems.append(f"{cls.name}.{setting.key}: default not in choices.")
        commands = [stage.command for stage in cls.stages]
        for stage in cls.stages:
            if stage.phase not in PHASES:
                problems.append(
                    f"{cls.name}: stage {stage.command} has unknown phase "
                    f"{stage.phase!r}."
                )
        if len(commands) != len(set(commands)):
            problems.append(f"{cls.name}: a stage is declared twice.")
        if cls.agent is not None and not re.match(
            r"^[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)+$", cls.agent
        ):
            problems.append(
                f"{cls.name}: agent {cls.agent!r} must be a dotted module path."
            )
        for ref in [cls.health, *cls.subscribes.values()]:
            if ref is not None and ":" not in ref:
                problems.append(f"{cls.name}: {ref!r} must be 'module:function'.")
        return problems
