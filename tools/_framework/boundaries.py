"""The import rules that make a tool removable, checked by reading source (AST).

1. ``tool.py`` imports only the standard library and ``tools._framework.spec``.
2. A tool's ``__init__.py`` imports nothing.
3. A tool imports another tool only if it lists it in ``depends_on``, and only
   that tool's ``exports`` modules.
4. The platform (``web/backend``, ``mylo``, ``ops``, ``eval``) imports tools
   only where :data:`ALLOWLIST_FILE` says so, and only their ``exports``. The
   allowlist is a ratchet: the check fails on a new import *and* on an entry
   that no longer matches anything, so it can only be shrunk on purpose.

``tools._framework`` is the host: anyone may import it.
Standard library only.
"""

from __future__ import annotations

import ast
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from . import discovery

REPO_ROOT = discovery.REPO_ROOT
ALLOWLIST_FILE = Path(__file__).resolve().parent / "platform_imports.txt"
PLATFORM_ROOTS = ("web/backend", "mylo", "ops", "eval")
_SKIP_PARTS = {"__pycache__", ".venv", "node_modules", "migrations", "sandbox"}
_STDLIB = set(sys.stdlib_module_names) | {"__future__"}
#: Platform code that is itself waiting to be moved into tools. A tool may use
#: the platform freely, except this: depending on it would tie a tool to code
#: that is about to become another tool, by the back door.
LEGACY_PLATFORM = ("apps.content",)


@dataclass(frozen=True)
class Import:
    module: str
    line: int


def imports_of(path: Path, package: str | None = None) -> Iterator[Import]:
    """Absolute module names imported by ``path`` (relative imports resolved
    against ``package``, the file's own dotted package)."""
    try:
        tree = ast.parse(path.read_text(), filename=str(path))
    except SyntaxError:
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield Import(alias.name, node.lineno)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level and package:
                parts = package.split(".")
                parts = parts[: len(parts) - (node.level - 1)]
                base = ".".join([*parts, base] if base else parts)
            elif node.level:
                continue
            for alias in node.names:
                # ``from pkg import sub`` may name a submodule; keep both forms.
                yield Import(
                    f"{base}.{alias.name}" if base else alias.name, node.lineno
                )


def _py_files(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*.py")):
        if not _SKIP_PARTS.intersection(path.parts):
            yield path


def _owner(module: str, tool_pkg: str) -> tuple[str, str] | None:
    """``(tool, first submodule)`` if ``module`` is inside a tool package."""
    if not module.startswith(tool_pkg + "."):
        return None
    rest = module[len(tool_pkg) + 1 :].split(".")
    if rest[0] == "_framework":
        return None
    return rest[0], (rest[1] if len(rest) > 1 else "")


_DEPTH_RE = re.compile(
    r"__file__\)?(?:\.resolve\(\))?\.(?:parents\[\d+\]|parent\.parent)"
)


def check_tools(tools_dir: Path | None = None) -> list[str]:
    """Rules 1–3 for every tool in ``tools_dir``, plus: no tool locates the
    repository by counting its own parent directories (``parents[N]``) — a
    count that silently goes wrong when the tool moves. It imports
    ``tools._framework.discovery.REPO_ROOT`` instead. Host scripts (``host/``,
    run before anything is importable) and tests are exempt."""
    tools_dir = discovery.tools_dir() if tools_dir is None else tools_dir
    found = discovery.discover(tools_dir)
    tool_pkg = discovery.package_root(tools_dir)[1]
    problems: list[str] = []
    for name, item in found.items():
        cls = item.cls
        tool_py = item.path / "tool.py"
        for imp in imports_of(tool_py, item.package):
            top = imp.module.split(".")[0]
            ok = top in _STDLIB or imp.module.startswith("tools._framework.spec")
            if not ok:
                problems.append(
                    f"{_rel(tool_py)}:{imp.line}: tool.py may import only the "
                    f"standard library and tools._framework.spec, not {imp.module}"
                )
        init = item.path / "__init__.py"
        if init.exists() and any(True for _ in imports_of(init, item.package)):
            problems.append(
                f"{_rel(init)}: a tool's __init__.py must not import anything"
            )
        if cls is None:
            continue
        for path in _py_files(item.path):
            if path == tool_py:
                continue
            rel_parts = path.relative_to(item.path).parts
            if rel_parts[0] not in ("host", "tests") and _DEPTH_RE.search(
                path.read_text()
            ):
                problems.append(f"{_rel(path)}: locates the repository by counting "
                                "parent directories; import REPO_ROOT from "
                                "tools._framework.discovery")
            pkg = _module_package(path, item.path, item.package)
            for imp in imports_of(path, pkg):
                legacy = [p for p in LEGACY_PLATFORM
                          if imp.module == p or imp.module.startswith(p + ".")]
                if legacy:
                    problems.append(f"{_rel(path)}:{imp.line}: {name} imports "
                                    f"{imp.module}, platform code still being moved "
                                    "into tools; depend on the tool it becomes")
                    continue
                owner = _owner(imp.module, tool_pkg)
                if owner is None or owner[0] == name:
                    continue
                other, sub = owner
                if other not in found:
                    problems.append(
                        f"{_rel(path)}:{imp.line}: imports {imp.module}, but no "
                        f"tool {other!r} is installed"
                    )
                    continue
                if other not in cls.depends_on:
                    problems.append(
                        f"{_rel(path)}:{imp.line}: {name} imports {imp.module} "
                        f"but does not declare depends_on {other!r}"
                    )
                    continue
                exports = found[other].cls.exports if found[other].cls else ()
                if sub not in exports:
                    problems.append(
                        f"{_rel(path)}:{imp.line}: {imp.module} is internal to "
                        f"{other}; its exports are {', '.join(exports)}"
                    )
    return problems


def platform_imports(tools_dir: Path | None = None) -> dict[tuple[str, str], int]:
    """``{(file, tool.module): line}`` for every platform import of a tool."""
    tools_dir = discovery.tools_dir() if tools_dir is None else tools_dir
    tool_pkg = discovery.package_root(tools_dir)[1]
    out: dict[tuple[str, str], int] = {}
    for root in PLATFORM_ROOTS:
        base = REPO_ROOT / root
        if not base.is_dir():
            continue
        for path in _py_files(base):
            for imp in imports_of(path, _platform_package(path)):
                owner = _owner(imp.module, tool_pkg)
                if owner is None:
                    continue
                key = (_rel(path), f"{owner[0]}.{owner[1]}" if owner[1] else owner[0])
                out.setdefault(key, imp.line)
    return out


def read_allowlist(path: Path = ALLOWLIST_FILE) -> set[tuple[str, str]]:
    if not path.exists():
        return set()
    rows = set()
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            file, _, module = line.partition("\t")
            rows.add((file.strip(), module.strip()))
    return rows


def write_allowlist(entries: set[tuple[str, str]], path: Path = ALLOWLIST_FILE) -> None:
    header = (
        "# Platform files that still import a tool.\n"
        "# Tab-separated: file, tool.module.\n"
        "# A ratchet: tools/_framework/tests/test_boundaries.py fails on any import\n"
        "# not listed here AND on any entry that no longer matches, so this list only\n"
        "# shrinks, and only on purpose. Regenerate after removing an import with\n"
        "#   uv run --no-sync --project web/backend \\\n"
        "#     python -m tools._framework.boundaries --write\n"
    )
    body = "".join(f"{f}\t{m}\n" for f, m in sorted(entries))
    path.write_text(header + body)


def check_platform(tools_dir: Path | None = None) -> list[str]:
    """Rule 4: every platform import of a tool is allowlisted and exported."""
    tools_dir = discovery.tools_dir() if tools_dir is None else tools_dir
    found = discovery.discover(tools_dir)
    current = platform_imports(tools_dir)
    allowed = read_allowlist()
    problems = []
    for (file, module), line in sorted(current.items()):
        name, _, sub = module.partition(".")
        if (file, module) not in allowed:
            problems.append(
                f"{file}:{line}: the platform imports tool module {module}; "
                "the platform must not depend on a tool (not in "
                "tools/_framework/platform_imports.txt)"
            )
        cls = found[name].cls if name in found else None
        if cls is not None and sub not in cls.exports:
            problems.append(
                f"{file}:{line}: {module} is internal to {name}; its exports "
                f"are {', '.join(cls.exports)}"
            )
    for file, module in sorted(allowed - set(current)):
        problems.append(
            f"platform_imports.txt: stale entry {file} -> {module}; remove it "
            "(the allowlist only shrinks)"
        )
    return problems


def _module_package(path: Path, tool_path: Path, tool_package: str) -> str:
    rel = path.relative_to(tool_path).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    else:
        parts = parts[:-1]
    return ".".join([tool_package, *parts])


def _platform_package(path: Path) -> str | None:
    backend = REPO_ROOT / "web" / "backend"
    try:
        rel = path.relative_to(backend)
    except ValueError:
        try:
            rel = path.relative_to(REPO_ROOT)
        except ValueError:
            return None
    return ".".join(rel.parts[:-1]) or None


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    if "--write" in sys.argv:
        write_allowlist(set(platform_imports()))
        print(f"wrote {ALLOWLIST_FILE}")
    else:
        issues = check_tools() + check_platform()
        print("\n".join(issues) or "boundaries ok")
        raise SystemExit(1 if issues else 0)
