"""Delete-each and break-each: every installed tool, removed or broken in turn.

For each real tool this copies ``tools/`` to a temporary directory without it
(or with an import error planted in it), points the import script there, and
checks the rest of the instance is exactly as predicted: the tool's dependents
are MISSING or BLOCKED, everything else LOADED — and, for a tool that is not
core, that Django starts and its system checks pass without it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tools._framework import discovery, loader

ROOT = Path(__file__).resolve().parents[3]
REAL = discovery.discover(discovery.DEFAULT_TOOLS_DIR)
NAMES = sorted(n for n, d in REAL.items() if d.cls is not None)


def _dependents(name: str) -> set[str]:
    out: set[str] = set()
    frontier = {name}
    while frontier:
        nxt = {n for n, d in REAL.items() if d.cls and set(d.cls.depends_on) & frontier}
        nxt -= out
        out |= nxt
        frontier = nxt
    return out


def _copy_without(tmp: Path, name: str, *, break_it: bool) -> Path:
    target = tmp / "tools"
    shutil.copytree(
        discovery.DEFAULT_TOOLS_DIR,
        target,
        ignore=shutil.ignore_patterns("__pycache__", "tests"),
    )
    if break_it:
        (target / name / "read.py").write_text(
            "import a_module_that_does_not_exist  # planted by the break-each test\n"
        )
    else:
        shutil.rmtree(target / name)
    return target


def _preflight(tools_dir: Path) -> loader.LoadReport:
    env = dict(os.environ)
    env["MYCELIUM_TOOLS_DIR"] = str(tools_dir)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(tools_dir.parent), env.get("PYTHONPATH", "")]
    )
    return loader.preflight(tools_dir=tools_dir, environ=env)


@pytest.mark.skipif(not NAMES, reason="no tools installed yet")
@pytest.mark.parametrize("name", NAMES)
def test_delete_each(tmp_path, name):
    report = _preflight(_copy_without(tmp_path, name, break_it=False))
    if REAL[name].cls.core:
        # The platform still imports it: nothing can start, and the report
        # names the missing folder.
        assert report.missing_required == [name]
        for other, item in report.tools.items():
            # MISSING when it also depends on the deleted tool directly.
            assert item.state in (loader.BLOCKED, loader.MISSING), (other, item)
            assert name in item.reason
        with pytest.raises(loader.ToolsLoadError, match=f"tools/{name}/"):
            report.enforce(strict=False)
        return
    dependents = _dependents(name)
    for other, item in report.tools.items():
        expected = (
            {loader.MISSING, loader.BLOCKED} if other in dependents else {loader.LOADED}
        )
        assert item.state in expected, (other, item.state, item.reason)
    if not REAL[name].cls.core and not any(REAL[d].cls.core for d in dependents):
        env = dict(os.environ)
        env.update(
            MYCELIUM_TOOLS_DIR=str(tmp_path / "tools"),
            MYCELIUM_TOOLS_CACHE=str(tmp_path / "cache"),
            MYCELIUM_TOOLS_STRICT="0",
        )
        env["PYTHONPATH"] = os.pathsep.join(
            [str(ROOT / "web" / "backend"), str(tmp_path), env.get("PYTHONPATH", "")]
        )
        proc = subprocess.run(
            [sys.executable, str(ROOT / "web" / "backend" / "manage.py"), "check"],
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr


@pytest.mark.skipif(not NAMES, reason="no tools installed yet")
@pytest.mark.parametrize("name", NAMES)
def test_break_each(tmp_path, name):
    report = _preflight(_copy_without(tmp_path, name, break_it=True))
    assert report.tools[name].state == loader.FAILED, report.tools[name].reason
    assert "a_module_that_does_not_exist" in report.tools[name].reason
    others = set(report.tools) - {name} if REAL[name].cls.core else _dependents(name)
    for other in others:
        assert report.tools[other].state == loader.BLOCKED, (other, report.tools[other])
