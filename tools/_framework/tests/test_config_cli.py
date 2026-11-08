"""``ops/mycelium config`` reads and writes per-tool sections (fixture tools)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _cli(tmp_path, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith("FIXTURE_")}
    env.update(
        MYCELIUM_TOOLS_DIR=str(FIXTURES),
        MYCELIUM_CONFIG=str(tmp_path / "m.toml"),
        NO_COLOR="1",
    )
    return subprocess.run(
        [sys.executable, str(ROOT / "ops" / "setup" / "config_cli.py"), *args],
        env=env, capture_output=True, text=True, timeout=120,
    )


def test_set_get_explain_and_reject_unknown(tmp_path):
    (tmp_path / "m.toml").write_text('[instance]\nprofile = "lab"\n')
    assert _cli(tmp_path, "set", "tools.ok_leaf.depth", "7").returncode == 0
    text = (tmp_path / "m.toml").read_text()
    assert "[tools.ok_leaf]" in text and "depth = 7" in text
    got = _cli(tmp_path, "get", "tools.ok_leaf.depth", "--json")
    assert json.loads(got.stdout)["value"] == 7
    assert _cli(tmp_path, "set", "tools.ok_leaf.enabled", "false").returncode == 0
    assert "enabled = false" in (tmp_path / "m.toml").read_text()
    bad = _cli(tmp_path, "set", "tools.ok_leaf.nonexistent", "1")
    assert bad.returncode != 0
    bad = _cli(tmp_path, "set", "tools.ok_leaf.depth", "deep")
    assert bad.returncode != 0
    explain = _cli(tmp_path, "explain", "tools.ok_leaf", "--json")
    keys = {row["key"] for row in json.loads(explain.stdout)}
    assert {"tools.ok_leaf.greeting", "tools.ok_leaf.depth"} <= keys


def test_validate_reports_a_bad_tool_value_and_absent_tool_sections(tmp_path):
    (tmp_path / "m.toml").write_text(
        '[tools.bad_config]\nlimit = "lots"\n\n[tools.long_gone]\nx = 1\n'
    )
    out = _cli(tmp_path, "validate", "--json")
    data = json.loads(out.stdout)
    assert not data["ok"]
    assert any("limit" in p for p in data["problems"])
    assert any("long_gone" in w for w in data["warnings"])
