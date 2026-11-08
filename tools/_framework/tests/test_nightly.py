"""The nightly plan: phase order, dependency order, ``after``, and skipping."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools._framework import discovery, loader, nightly
from tools._framework.spec import Stage, Tool

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _fixture_classes(*names):
    found = discovery.discover(FIXTURES)
    deps = {n: tuple(found[n].cls.depends_on) for n in names}
    order, _ = loader.dependency_order(deps)
    return [found[n].cls for n in order]


def test_phases_then_dependency_order_then_after():
    platform = (
        Stage("platform_brief", "brief", "…"),
        Stage("platform_rank", "rank", "…"),
    )
    plan = nightly.order_stages(_fixture_classes("ok_dependent", "ok_leaf"), platform)
    assert [(p.owner, p.stage.command) for p in plan] == [
        ("platform", "platform_rank"),
        ("ok_leaf", "fixture_leaf_stage"),
        ("ok_dependent", "fixture_dependent_late"),
        ("platform", "platform_brief"),
        ("ok_dependent", "fixture_dependent_brief"),
    ]


def test_after_reorders_within_a_phase():
    class A(Tool):
        name = "a"
        stages = (
            Stage("second", "rank", "…", after=("first",)),
            Stage("first", "rank", "…"),
        )

    assert [p.stage.command for p in nightly.order_stages([A], ())] == [
        "first",
        "second",
    ]


def test_duplicates_and_cycles_are_errors():
    class A(Tool):
        name = "a"
        stages = (
            Stage("x", "rank", "…", after=("y",)),
            Stage("y", "rank", "…", after=("x",)),
        )

    with pytest.raises(nightly.PlanError, match="cycle"):
        nightly.order_stages([A], ())

    class B(Tool):
        name = "b"
        stages = (Stage("x", "rank", "…"),)

    with pytest.raises(nightly.PlanError, match="twice"):
        nightly.order_stages([B], (Stage("x", "brief", "…"),))


def test_the_assembled_plan_matches_the_golden_stage_list():
    golden = (
        Path(nightly.__file__).parent / "golden" / "nightly_stages.txt"
    ).read_text()
    planned = "".join(
        f"{cmd}\t{' '.join(args)}\n"
        for cmd, args, _ in nightly.as_tuples(nightly.plan_for()[0])
    )
    assert planned == golden


def test_unloaded_tools_stages_are_skipped(monkeypatch):
    monkeypatch.setenv("MYCELIUM_TOOLS_DIR", str(FIXTURES))
    run, skipped = nightly.plan_for(["ok_leaf"])
    owners_run = {p.owner for p in run}
    assert "ok_leaf" in owners_run and "ok_dependent" not in owners_run
    assert {"fixture_dependent_late", "fixture_dependent_brief"} <= {
        p.stage.command for p in skipped
    }
