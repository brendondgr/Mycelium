"""The declaration vocabulary and the per-tool configuration layer."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools._framework import config, discovery
from tools._framework.spec import Setting, SpecError, Stage, Tool

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_setting_parses_like_django_environ():
    assert Setting("a", "bool", False, "").parse("yes", source="x") is True
    assert Setting("a", "bool", True, "").parse("0", source="x") is False
    assert Setting("a", "int", 1, "").parse(" 7 ", source="x") == 7
    assert Setting("a", "float", 1.0, "").parse("0.25", source="x") == 0.25
    assert Setting("a", "list", [], "").parse("a, b,,c", source="x") == ["a", "b", "c"]
    with pytest.raises(SpecError, match="not a int"):
        Setting("a", "int", 1, "").parse("seven", source="x")
    with pytest.raises(SpecError):
        Setting("a", "choice", "x", "", choices=("x", "y")).parse("z", source="x")


def test_validate_catches_bad_declarations():
    class Bad(Tool):
        name = "Bad-Name"
        depends_on = ("Bad-Name",)
        settings = (Setting("enabled", "bool", True, ""), Setting("k", "weird", 1, ""))
        stages = (Stage("x", "nonsense", "…"),)
        health = "no_colon"

    problems = " ".join(Bad.validate())
    for fragment in (
        "must match",
        "depends on itself",
        "reserved",
        "unknown kind",
        "unknown phase",
        "module:function",
    ):
        assert fragment in problems


def test_discovery_reads_every_fixture_and_reports_bad_ones():
    found = discovery.discover(FIXTURES)
    assert found["ok_leaf"].cls is not None
    assert found["ok_leaf"].package == "tools._framework.tests.fixtures.ok_leaf"
    assert found["bad_declaration"].cls is None
    assert "something_else" in found["bad_declaration"].error


def test_tool_config_layers_and_isolates_problems():
    found = discovery.discover(FIXTURES)
    classes = [found["ok_leaf"].cls, found["bad_config"].cls]
    configs, warnings = config.resolve_tools(
        classes,
        file_values={
            "ok_leaf": {"depth": 9},
            "bad_config": {"limit": "lots", "unknown_key": 1},
            "deleted_tool": {"x": 1},
        },
        profile_values={"ok_leaf": {"greeting": "from profile", "depth": 4}},
        environ={"FIXTURE_OK_LEAF_GREETING": "from env"},
    )
    leaf = configs["ok_leaf"]
    assert (
        leaf["greeting"] == "from env"
        and leaf.sources["greeting"] == "env:FIXTURE_OK_LEAF_GREETING"
    )
    assert leaf["depth"] == 9 and leaf.sources["depth"] == "mycelium.toml"
    assert leaf.problems == []
    bad = configs["bad_config"]
    assert (
        len(bad.problems) == 2
    )  # a bad value and an unknown key — the tool fails, nothing else
    assert warnings == [
        "mycelium.toml configures [tools.deleted_tool], but no tool named "
        "'deleted_tool' is installed; the section is ignored."
    ]


def test_disabled_list_and_enabled_key():
    found = discovery.discover(FIXTURES)
    configs, _ = config.resolve_tools(
        [found["ok_leaf"].cls, found["disabled_one"].cls],
        file_values={"ok_leaf": {"enabled": False}},
        profile_values={},
        environ={},
        disabled=["disabled_one"],
    )
    assert not configs["ok_leaf"].enabled
    assert not configs["disabled_one"].enabled


def test_instance_layer_accepts_tool_sections_and_warns_on_absent_tools():
    from config import instance

    resolved = instance.resolve(
        Path("/nonexistent"),
        {},
        file_values={"tools.strict": True, "tools.ghost.anything": 1},
    )
    assert resolved["tools.strict"] is True
    assert any("tools.ghost" in w for w in resolved.warnings)
    # An unknown universal key is still an error.
    with pytest.raises(instance.ConfigError):
        instance.resolve(Path("/nonexistent"), {}, file_values={"tools.bogus": 1})


def test_scaffold_writes_a_tool_discovery_accepts(tmp_path, monkeypatch):
    from tools._framework import scaffold

    root = tmp_path / "scaffoldpkg"
    root.mkdir()
    (root / "__init__.py").write_text("")
    monkeypatch.setattr(scaffold, "TOOLS", root)
    assert scaffold.main(["scaffold.py", "lab_notes"]) == 0
    found = discovery.discover(root)
    assert found["lab_notes"].cls is not None, found["lab_notes"].error
    assert found["lab_notes"].cls.summary
    assert scaffold.main(["scaffold.py", "lab_notes"]) == 1  # refuses to overwrite
    assert scaffold.main(["scaffold.py", "accounts"]) == 1  # a platform label
