"""The import script, end to end on the fixture tools (real subprocess probes)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tools._framework import config, discovery, loader

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _configs(**file_values):
    found = discovery.discover(FIXTURES)
    classes = [d.cls for d in found.values() if d.cls is not None]
    configs, _ = config.resolve_tools(
        classes,
        file_values=file_values,
        profile_values={},
        environ={},
        disabled=["disabled_one"],
    )
    return configs


@pytest.fixture(scope="module")
def report():
    env = {k: v for k, v in os.environ.items() if not k.startswith("FIXTURE_")}
    return loader.preflight(
        tools_dir=FIXTURES,
        tool_configs=_configs(bad_config={"limit": "lots"}),
        environ=env,
    )


EXPECTED = {
    "ok_leaf": loader.LOADED,
    "ok_dependent": loader.LOADED,
    # forbidden_import loads fine; the boundary test is what rejects it.
    "forbidden_import": loader.LOADED,
    "broken_import": loader.FAILED,
    "blocked_by_broken": loader.BLOCKED,
    "broken_health": loader.FAILED,
    "missing_secret": loader.FAILED,
    "cycle_a": loader.FAILED,
    "cycle_b": loader.FAILED,
    "depends_on_absent": loader.MISSING,
    "disabled_one": loader.DISABLED,
    "bad_config": loader.FAILED,
    "bad_declaration": loader.FAILED,
}


def test_every_fixture_ends_in_its_expected_state(report):
    assert {n: t.state for n, t in report.tools.items()} == EXPECTED


def test_reasons_name_the_cause(report):
    r = report.tools
    assert "a_module_that_does_not_exist" in r["broken_import"].reason
    assert r["blocked_by_broken"].reason == "needs broken_import (FAILED)"
    assert "health says no" in r["broken_health"].reason
    assert "FIXTURE_SECRET_THAT_IS_NEVER_SET" in r["missing_secret"].reason
    assert "cycle" in r["cycle_a"].reason
    assert "no_such_tool" in r["depends_on_absent"].reason
    assert "configuration" in r["bad_config"].reason


def test_dependency_order_puts_dependencies_first(report):
    order = report.order
    assert order.index("ok_leaf") < order.index("ok_dependent")
    assert order.index("broken_import") < order.index("blocked_by_broken")


def test_enforce_strict_and_core(report):
    with pytest.raises(loader.ToolsLoadError, match="strict"):
        report.enforce(strict=True)
    report.enforce(strict=False)  # lenient: broken tools are set aside, not fatal
    core = loader.LoadReport.from_json(report.to_json())
    core.tools["broken_health"].core = True
    with pytest.raises(loader.ToolsLoadError, match="core"):
        core.enforce(strict=False)


def test_report_round_trips_and_caches(tmp_path, monkeypatch, report):
    monkeypatch.setenv("MYCELIUM_TOOLS_CACHE", str(tmp_path))
    report.fingerprint = "f" * 64
    loader.write_cached(report)
    again = loader.read_cached("f" * 64)
    assert again is not None and again.loaded() == report.loaded()
    assert loader.read_cached("0" * 64) is None


def test_fingerprint_changes_when_a_tool_file_changes(tmp_path):
    tools = tmp_path / "tools"
    (tools / "x").mkdir(parents=True)
    (tools / "x" / "tool.py").write_text("A = 1\n")
    before = loader.fingerprint(tools, {})
    (tools / "x" / "tool.py").write_text("A = 22\n")
    assert loader.fingerprint(tools, {}) != before
    assert loader.fingerprint(tools, {"strict": True}) != loader.fingerprint(tools, {})


def test_dependency_order_detects_cycles():
    order, cyclic = loader.dependency_order({"a": ("b",), "b": ("a",), "c": ()})
    assert cyclic == {"a", "b"} and set(order) == {"a", "b", "c"}
