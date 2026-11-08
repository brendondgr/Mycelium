"""The import script: decide which tools may run, before anything runs them.

Every tool ends in exactly one state:

``LOADED``    every check passed; the tool is installed, routed and scheduled
``DISABLED``  switched off in configuration
``MISSING``   it depends on a tool whose folder does not exist
``BLOCKED``   it depends on a tool that is not LOADED (the reason names which)
``FAILED``    its own check failed: declaration, dependency cycle,
              configuration, missing secret, import error or health check

The checks run in dependency order. The last one, the *probe*, starts Django in
a subprocess with only the platform and the tool's dependency closure installed,
imports the tool's modules and runs its health check — so an import error in a
tool can never take the main process down with it. All candidates are probed in
one subprocess first (the common, healthy case costs one Django start); only if
that fails is each tool probed on its own to find the culprit.

The result is cached in ``data/tools/`` under a fingerprint of every Python
file the tools and the platform consist of plus the tool configuration, so a
process starts from the cached report unless something changed.

Standard library only: settings.py calls this before Django is configured.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from . import discovery

LOADED, DISABLED, MISSING, BLOCKED, FAILED = (
    "LOADED",
    "DISABLED",
    "MISSING",
    "BLOCKED",
    "FAILED",
)
STATES = (LOADED, DISABLED, MISSING, BLOCKED, FAILED)

REPORT_VERSION = 1
PROBE_ENV = "MYCELIUM_TOOLS_PROBE"
PROBE_TIMEOUT = int(os.environ.get("MYCELIUM_TOOLS_PROBE_TIMEOUT", "300"))
_KEEP_REPORTS = 8


class ToolsLoadError(RuntimeError):
    """A tool that must load did not (strict mode, or a core tool)."""


@dataclass
class ToolState:
    name: str
    state: str
    reason: str = ""
    label: str = ""
    package: str = ""
    core: bool = False
    depends_on: list[str] = field(default_factory=list)
    summary: str = ""


@dataclass
class LoadReport:
    fingerprint: str
    tools_dir: str
    package: str
    #: Dependency order (dependencies before dependents), every discovered tool.
    order: list[str]
    tools: dict[str, ToolState]
    warnings: list[str] = field(default_factory=list)
    created: float = field(default_factory=time.time)
    version: int = REPORT_VERSION

    def loaded(self) -> list[str]:
        return [n for n in self.order if self.tools[n].state == LOADED]

    def state(self, name: str) -> str | None:
        item = self.tools.get(name)
        return item.state if item else None

    def to_json(self, *, compact: bool = False) -> str:
        data = asdict(self)
        if compact:  # one line: the nightly runner reads the last line of output
            return json.dumps(data, sort_keys=True, separators=(",", ":"))
        return json.dumps(data, indent=1, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> LoadReport:
        data = json.loads(text)
        data["tools"] = {k: ToolState(**v) for k, v in data["tools"].items()}
        return cls(**data)

    def table(self) -> str:
        width = max([len(n) for n in self.order] + [4])
        lines = [f"{'tool':<{width}}  {'state':<8}  reason"]
        for name in self.order:
            item = self.tools[name]
            reason = item.reason.splitlines()[0] if item.reason else ""
            core = " (core)" if item.core else ""
            lines.append(f"{name + core:<{width}}  {item.state:<8}  {reason}")
        if not self.order:
            lines.append("(no tools installed)")
        return "\n".join(lines)

    def enforce(self, *, strict: bool) -> None:
        """Raise when a tool that must load did not."""
        bad = [
            t
            for n in self.order
            if (t := self.tools[n]).state != LOADED
            and (t.core or (strict and t.state != DISABLED))
        ]
        if bad:
            detail = "\n".join(
                f"  {t.name}: {t.state} — {_first_line(t.reason)}" for t in bad
            )
            why = (
                "strict mode"
                if strict and not any(t.core for t in bad)
                else "a core tool"
            )
            raise ToolsLoadError(
                f"Tools that must load did not ({why}):\n{detail}\n"
                "Run `make tools-check` for the full report."
            )


def _first_line(text: str) -> str:
    return text.splitlines()[0] if text else ""


# --------------------------------------------------------------------------- #
# Ordering
# --------------------------------------------------------------------------- #


def dependency_order(deps: dict[str, tuple[str, ...]]) -> tuple[list[str], set[str]]:
    """Topological order (alphabetical among equals) and the tools in cycles."""
    order: list[str] = []
    state: dict[str, int] = {}
    cyclic: set[str] = set()

    def visit(node: str, stack: list[str]) -> None:
        if state.get(node) == 2:
            return
        if state.get(node) == 1:
            cyclic.update(stack[stack.index(node) :])
            return
        state[node] = 1
        stack.append(node)
        for dep in sorted(deps.get(node, ())):
            if dep in deps:
                visit(dep, stack)
        stack.pop()
        state[node] = 2
        order.append(node)

    for node in sorted(deps):
        visit(node, [])
    return order, cyclic


# --------------------------------------------------------------------------- #
# Fingerprint and cache
# --------------------------------------------------------------------------- #


def _source_roots(tools_dir: Path) -> list[Path]:
    backend = discovery.REPO_ROOT / "web" / "backend"
    return [tools_dir, backend / "apps", backend / "config"]


def fingerprint(tools_dir: Path, config_snapshot: Any) -> str:
    digest = hashlib.sha256()
    digest.update(str(REPORT_VERSION).encode())
    digest.update(sys.executable.encode())
    digest.update(os.environ.get("DJANGO_SETTINGS_MODULE", "").encode())
    for root in _source_roots(tools_dir):
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            stat = path.stat()
            digest.update(f"{path}:{stat.st_mtime_ns}:{stat.st_size}".encode())
    digest.update(json.dumps(config_snapshot, sort_keys=True, default=str).encode())
    return digest.hexdigest()


def cache_dir() -> Path:
    override = os.environ.get("MYCELIUM_TOOLS_CACHE", "").strip()
    return Path(override) if override else discovery.REPO_ROOT / "data" / "tools"


def _cache_path(fp: str) -> Path:
    return cache_dir() / f"load-report-{fp[:16]}.json"


def read_cached(fp: str) -> LoadReport | None:
    path = _cache_path(fp)
    try:
        report = LoadReport.from_json(path.read_text())
    except (OSError, ValueError, TypeError, KeyError):
        return None
    return report if report.fingerprint == fp else None


def write_cached(report: LoadReport) -> None:
    """Best effort: a read-only data/ (a root-owned Docker dir) is not an error."""
    try:
        directory = cache_dir()
        directory.mkdir(parents=True, exist_ok=True)
        _cache_path(report.fingerprint).write_text(report.to_json())
        reports = sorted(
            directory.glob("load-report-*.json"), key=lambda p: p.stat().st_mtime
        )
        for old in reports[:-_KEEP_REPORTS]:
            old.unlink(missing_ok=True)
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# The preflight
# --------------------------------------------------------------------------- #


def preflight(
    *,
    tools_dir: Path | None = None,
    tool_configs: dict[str, Any] | None = None,
    environ: dict[str, str] | None = None,
    probe: bool = True,
    config_warnings: list[str] | None = None,
) -> LoadReport:
    """Run every check and return the report. Does not read or write the cache."""
    tools_dir = discovery.tools_dir(environ) if tools_dir is None else tools_dir
    env = dict(os.environ if environ is None else environ)
    tool_configs = tool_configs or {}
    found = discovery.discover(tools_dir)
    package = discovery.package_root(tools_dir)[1] if tools_dir.is_dir() else "tools"

    deps = {
        name: tuple(item.cls.depends_on) if item.cls else ()
        for name, item in found.items()
    }
    order, cyclic = dependency_order(deps)
    states: dict[str, ToolState] = {}
    for name in order:
        item = found[name]
        cls = item.cls
        states[name] = ToolState(
            name=name,
            state="",
            label=cls.app_label() if cls else "",
            package=item.package,
            core=bool(cls and cls.core),
            depends_on=list(deps[name]),
            summary=cls.summary if cls else "",
        )

    def fail(name: str, state: str, reason: str) -> None:
        states[name].state = state
        states[name].reason = reason

    pending: list[str] = []
    for name in order:
        item, current = found[name], states[name]
        cfg = tool_configs.get(name)
        if item.cls is None:
            fail(name, FAILED, item.error or "tool.py could not be read")
            continue
        if name in cyclic:
            fail(name, FAILED, "dependency cycle: " + " -> ".join(sorted(cyclic)))
            continue
        if cfg is not None and not cfg.enabled:
            if item.cls.core:
                fail(name, FAILED, "a core tool cannot be disabled")
            else:
                fail(name, DISABLED, "switched off in configuration")
            continue
        if cfg is not None and cfg.problems:
            fail(name, FAILED, "configuration: " + " ".join(cfg.problems))
            continue
        missing_secrets = [s for s in item.cls.secrets if not env.get(s, "").strip()]
        if missing_secrets:
            fail(name, FAILED, f"needs {', '.join(missing_secrets)} in .env")
            continue
        absent = [d for d in item.cls.depends_on if d not in found]
        if absent:
            fail(
                name, MISSING, f"depends on {', '.join(absent)}, which is not installed"
            )
            continue
        # Dependencies were visited first (dependency order): each is either
        # still a candidate ("") or already has a final state, which blocks.
        blocked = [d for d in item.cls.depends_on if states[d].state]
        if blocked:
            fail(
                name,
                BLOCKED,
                "needs " + ", ".join(f"{d} ({states[d].state})" for d in blocked),
            )
            continue
        current.state = ""  # still a candidate
        pending.append(name)

    if pending:
        if probe:
            _probe_all(pending, states, tools_dir, env)
        else:
            for name in pending:
                states[name].state = LOADED

    warnings = list(config_warnings or [])
    return LoadReport(
        fingerprint="",
        tools_dir=str(tools_dir),
        package=package,
        order=order,
        tools=states,
        warnings=warnings,
    )


def _probe_all(
    pending: list[str],
    states: dict[str, ToolState],
    tools_dir: Path,
    env: dict[str, str],
) -> None:
    ok, _detail = run_probe(pending, tools_dir, env)
    if ok:
        for name in pending:
            states[name].state = LOADED
        return
    # Something in the batch is broken: probe one by one, in dependency order,
    # each with only its already-loaded dependency closure.
    for name in pending:
        deps = states[name].depends_on
        blocked = [d for d in deps if states[d].state != LOADED]
        if blocked:
            states[name].state = BLOCKED
            states[name].reason = "needs " + ", ".join(
                f"{d} ({states[d].state})" for d in blocked
            )
            continue
        closure = _closure(name, states)
        ok, detail = run_probe(closure, tools_dir, env)
        if ok:
            states[name].state = LOADED
        else:
            states[name].state = FAILED
            states[name].reason = detail


def _closure(name: str, states: dict[str, ToolState]) -> list[str]:
    seen: list[str] = []

    def walk(n: str) -> None:
        for d in states[n].depends_on:
            walk(d)
        if n not in seen:
            seen.append(n)

    walk(name)
    return seen


def run_probe(
    names: list[str], tools_dir: Path, env: dict[str, str]
) -> tuple[bool, str]:
    """Start Django in a subprocess with exactly ``names`` installed."""
    backend = discovery.REPO_ROOT / "web" / "backend"
    child_env = dict(env)
    child_env[PROBE_ENV] = ",".join(names)
    child_env["MYCELIUM_TOOLS_DIR"] = str(tools_dir)
    child_env.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    entry, _package = discovery.package_root(tools_dir)
    # The tools directory's own root first, so a copied or test tools package
    # shadows the repository's.
    paths = [str(entry), str(backend), str(discovery.REPO_ROOT)]
    if child_env.get("PYTHONPATH"):
        paths.append(child_env["PYTHONPATH"])
    child_env["PYTHONPATH"] = os.pathsep.join(dict.fromkeys(paths))
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "tools._framework.probe"],
            env=child_env,
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT,
            cwd=str(backend),
        )
    except subprocess.TimeoutExpired:
        return False, f"probe timed out after {PROBE_TIMEOUT}s"
    if proc.returncode == 0:
        return True, ""
    lines = [
        ln for ln in (proc.stdout + proc.stderr).strip().splitlines() if ln.strip()
    ]
    marker = [ln for ln in lines if ln.startswith("PROBE-FAILED")]
    detail = (
        marker[-1].removeprefix("PROBE-FAILED").strip()
        if marker
        else (lines[-1] if lines else f"exit {proc.returncode}")
    )
    return False, detail


# --------------------------------------------------------------------------- #
# Boot: what settings.py calls
# --------------------------------------------------------------------------- #


def config_snapshot(tool_configs: dict[str, Any], strict: bool) -> dict:
    return {
        "strict": strict,
        "tools": {
            n: {"enabled": c.enabled, "values": c.values, "problems": c.problems}
            for n, c in sorted(tool_configs.items())
        },
    }


def boot(
    *,
    tool_configs: dict[str, Any],
    strict: bool,
    environ: dict[str, str] | None = None,
    config_warnings: list[str] | None = None,
) -> LoadReport:
    """The report this process runs on: cached when nothing changed, else fresh.

    In a probe subprocess, the probe's own tool list is used as-is.
    """
    env = os.environ if environ is None else environ
    tools_dir = discovery.tools_dir(env)
    probe_names = (env.get(PROBE_ENV) or "").strip()
    if probe_names:
        return _probe_report(tools_dir, probe_names.split(","))
    fp = fingerprint(tools_dir, config_snapshot(tool_configs, strict))
    report = read_cached(fp)
    if report is None:
        report = preflight(
            tools_dir=tools_dir,
            tool_configs=tool_configs,
            environ=dict(env),
            config_warnings=config_warnings,
        )
        report.fingerprint = fp
        write_cached(report)
    report.enforce(strict=strict)
    return report


def _probe_report(tools_dir: Path, names: list[str]) -> LoadReport:
    found = discovery.discover(tools_dir)
    package = discovery.package_root(tools_dir)[1]
    states = {}
    for name in names:
        item = found.get(name)
        if item is None or item.cls is None:
            print(f"PROBE-FAILED {name}: {item.error if item else 'not found'}")
            raise SystemExit(3)
        states[name] = ToolState(
            name=name,
            state=LOADED,
            label=item.cls.app_label(),
            package=item.package,
            core=item.cls.core,
            depends_on=list(item.cls.depends_on),
            summary=item.cls.summary,
        )
    return LoadReport(
        fingerprint="probe",
        tools_dir=str(tools_dir),
        package=package,
        order=list(names),
        tools=states,
    )


def tool_classes(report: LoadReport) -> dict[str, Any]:
    """The declaration class of every tool in the report that could be read."""
    found = discovery.discover(Path(report.tools_dir))
    return {n: found[n].cls for n in report.order if n in found and found[n].cls}
