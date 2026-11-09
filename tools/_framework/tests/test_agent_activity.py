"""Every agent function, from every tool that contributes one, says what Mylo
is doing while it runs (the activity view shows only that label; S-9)."""

from __future__ import annotations

import importlib

from tools._framework import discovery
from tools._framework.agentspec import AgentFunction, activity_problems


def _contributed():
    for name, found in sorted(discovery.discover().items()):
        module = getattr(found.cls, "agent", None) if found.cls else None
        if not module:
            continue
        for fn in getattr(importlib.import_module(module), "FUNCTIONS", ()):
            yield name, fn


def test_every_agent_function_has_an_activity_label():
    seen = {tool for tool, _ in _contributed()}
    assert {"agent", "files", "fulltext"} <= seen
    problems = [p for tool, fn in _contributed() for p in activity_problems(fn)]
    assert problems == []


def test_a_function_without_a_label_fails():
    fn = AgentFunction(
        name="x_thing",
        summary="",
        description="",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}, "n": {"type": "integer"}},
            "required": ["query"],
        },
        handler="m:f",
        risk="read",
        output="person",
        scopes=("personal",),
        min_role={},
    )
    assert activity_problems(fn) == ["x_thing: no activity label"]
    labelled = AgentFunction(**{**fn.__dict__, "activity": "Finding “{query}” {n}"})
    assert activity_problems(labelled) == ["x_thing: activity slot {n} is not required"]
    wrong = AgentFunction(**{**fn.__dict__, "activity": "Finding {nope}"})
    assert "is not a parameter" in activity_problems(wrong)[0]
