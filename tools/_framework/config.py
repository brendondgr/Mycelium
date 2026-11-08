"""Per-tool configuration: one section of ``mycelium.toml`` per tool.

The universal keys (``instance``, ``billing``, ``limits``, ``signup``,
``email``, ``features``, ``nightly`` and ``tools``) are defined and resolved by
``web/backend/config/instance.py``. This module adds a section per installed
tool, merged with the same rule — the tool's defaults, then the deployment
profile, then ``mycelium.toml``, then the environment — so an operator edits
one file and a tool's keys disappear with its folder.

What is deliberately *not* an error: a section for a tool that is not
installed (a warning — deleting a folder must never stop an instance from
starting). What fails only the tool it belongs to: an unknown key or a bad
value inside an installed tool's section. Standard library only.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .spec import SpecError, Tool

PREFIX = "tools."
#: Universal keys under ``[tools]`` itself, owned by ``instance.py``.
UNIVERSAL = frozenset({"tools.strict", "tools.disabled"})


@dataclass
class ToolConfig:
    name: str
    enabled: bool = True
    values: dict[str, Any] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)

    def __getitem__(self, key: str) -> Any:
        return self.values[key]


def split_tool_keys(
    flat: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Separate ``tools.<name>.<key>`` entries from everything else."""
    rest: dict[str, Any] = {}
    per_tool: dict[str, dict[str, Any]] = {}
    for key, value in flat.items():
        if key.startswith(PREFIX) and key not in UNIVERSAL:
            name, _, sub = key[len(PREFIX) :].partition(".")
            if sub:
                per_tool.setdefault(name, {})[sub] = value
                continue
        rest[key] = value
    return rest, per_tool


def resolve_tools(
    tools: Iterable[type[Tool]],
    *,
    file_values: Mapping[str, Mapping[str, Any]],
    profile_values: Mapping[str, Mapping[str, Any]],
    environ: Mapping[str, str],
    disabled: Iterable[str] = (),
) -> tuple[dict[str, ToolConfig], list[str]]:
    """Every installed tool's resolved section, plus warnings for the rest."""
    disabled = set(disabled)
    out: dict[str, ToolConfig] = {}
    for cls in tools:
        cfg = ToolConfig(cls.name)
        by_key = {s.key: s for s in cls.settings}
        layers = (
            ("profile", profile_values.get(cls.name, {})),
            ("mycelium.toml", file_values.get(cls.name, {})),
        )
        for setting in cls.settings:
            cfg.values[setting.key] = setting.default
            cfg.sources[setting.key] = "default"
        for source, values in layers:
            for key, raw in values.items():
                if key == "enabled":
                    try:
                        cfg.enabled = _bool(raw)
                    except ValueError:
                        cfg.problems.append(
                            f"tools.{cls.name}.enabled from {source} is {raw!r}, "
                            "not a bool."
                        )
                    continue
                setting = by_key.get(key)
                if setting is None:
                    cfg.problems.append(
                        f"tools.{cls.name}.{key} (from {source}) is not a setting of "
                        f"this tool. Known: {', '.join(sorted(by_key)) or 'none'}."
                    )
                    continue
                try:
                    cfg.values[key] = setting.parse(
                        raw, source=f"tools.{cls.name} in {source}"
                    )
                    cfg.sources[key] = source
                except SpecError as exc:
                    cfg.problems.append(str(exc))
        for setting in cls.settings:
            if setting.env and setting.env in environ:
                try:
                    cfg.values[setting.key] = setting.parse(
                        environ[setting.env], source=f"${setting.env}"
                    )
                    cfg.sources[setting.key] = f"env:{setting.env}"
                except SpecError as exc:
                    cfg.problems.append(str(exc))
        if cls.name in disabled:
            cfg.enabled = False
        out[cls.name] = cfg
    warnings = [
        f"mycelium.toml configures [tools.{name}], but no tool named {name!r} is "
        "installed; the section is ignored."
        for name in sorted(set(file_values) - set(out))
    ]
    return out, warnings


def _bool(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    text = str(raw).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    raise ValueError(raw)
