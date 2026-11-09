"""Every function and reference kind the agent may use, from every loaded tool.

Each loaded tool that declares ``agent = "<module>"`` exports ``FUNCTIONS`` and
``REFS`` from that module (the agent's own come from ``tools.agent.functions``
the same way). A disabled tool's module is never imported, so its functions
never reach the catalog.

Only ``read`` functions load in this release: anything else is refused here,
at registration, and reported (``refused``), so no later check can be skipped.
"""

from __future__ import annotations

import importlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from tools._framework import services
from tools._framework.agentspec import (
    GUEST_LEVELS,
    RISKS,
    ROLES,
    SCOPES,
    SURFACES,
    WIDTHS,
    AgentFunction,
    RefKind,
)

logger = logging.getLogger(__name__)

#: The risks this release may load.
LOADABLE_RISKS = ("read",)
#: Schema properties that name an object and so must carry ``x-ref``.
_ID_LIKE = re.compile(r"(^|_)(id|ids|ref|refs|slug|username)$")


@dataclass
class Registry:
    functions: dict[str, AgentFunction] = field(default_factory=dict)
    owner: dict[str, str] = field(default_factory=dict)
    refs: dict[str, RefKind] = field(default_factory=dict)
    ref_owner: dict[str, str] = field(default_factory=dict)
    skill_dirs: list[tuple[str, Path]] = field(default_factory=list)
    refused: dict[str, str] = field(default_factory=dict)

    def get(self, name: str) -> AgentFunction | None:
        return self.functions.get(name)

    def groups(self) -> dict[str, list[AgentFunction]]:
        out: dict[str, list[AgentFunction]] = {}
        for fn in self.functions.values():
            out.setdefault(fn.group, []).append(fn)
        return out


def declaration_problems(fn: AgentFunction) -> list[str]:
    """Why a function's declaration is incomplete; empty when it is sound."""
    out = []
    if not re.match(r"^[a-z][a-z0-9_]*$", fn.name or ""):
        out.append("name must be lower_snake_case")
    if fn.risk not in RISKS:
        out.append(f"risk {fn.risk!r} is not one of {RISKS}")
    if fn.output not in WIDTHS:
        out.append(f"output {fn.output!r} is not one of {WIDTHS}")
    if not fn.scopes or any(s not in SCOPES for s in fn.scopes):
        out.append(f"scopes {fn.scopes!r} must name at least one of {SCOPES}")
    if not isinstance(fn.min_role, dict):
        out.append("min_role must be a dict (empty means any member)")
    else:
        for kind, role in fn.min_role.items():
            if role not in ROLES.get(kind, ()):
                out.append(f"min_role {kind}={role!r} is not a {kind} role")
    if any(s not in SURFACES for s in fn.surfaces):
        out.append(f"surfaces {fn.surfaces!r} must be among {SURFACES}")
    if ":" not in (fn.handler or ""):
        out.append("handler must be 'module:function'")
    if fn.guest is not None and fn.guest not in GUEST_LEVELS[1:]:
        out.append(f"guest {fn.guest!r} must be None or one of {GUEST_LEVELS[1:]}")
    params = fn.parameters or {}
    if params.get("type") != "object":
        out.append("parameters must be a JSON Schema object")
    for key, prop in (params.get("properties") or {}).items():
        marked = prop.get("x-ref") or (prop.get("items") or {}).get("x-ref")
        if _ID_LIKE.search(key) and not marked:
            out.append(f"parameter {key!r} looks like an id and needs x-ref")
    return out


def build() -> Registry:
    reg = Registry()
    for tool, module_path in services.agent_contributions():
        try:
            module = importlib.import_module(module_path)
        except Exception:  # a broken contribution must not take the agent down
            logger.exception("agent functions of %s failed to import", tool)
            continue
        for fn in getattr(module, "FUNCTIONS", ()):
            problems = declaration_problems(fn)
            if problems:
                reg.refused[fn.name] = "; ".join(problems)
                continue
            if fn.risk not in LOADABLE_RISKS:
                reg.refused[fn.name] = f"risk {fn.risk} cannot load in this release"
                continue
            if fn.name in reg.functions:
                reg.refused[fn.name] = f"declared twice ({reg.owner[fn.name]}, {tool})"
                continue
            reg.functions[fn.name] = fn
            reg.owner[fn.name] = tool
        for kind in getattr(module, "REFS", ()):
            if kind.kind not in reg.refs:
                reg.refs[kind.kind] = kind
                reg.ref_owner[kind.kind] = tool
        skills = getattr(module, "SKILLS_DIR", None)
        if skills:
            reg.skill_dirs.append((tool, Path(skills)))
    if reg.refused:
        logger.warning("agent functions refused: %s", reg.refused)
    return reg


_cached: Registry | None = None


def registry() -> Registry:
    global _cached
    if _cached is None:
        _cached = build()
    return _cached


def reset() -> None:
    """Forget the cached registry (tests that change what is loaded)."""
    global _cached
    _cached = None
