"""Tests for the ReAct loop: convergence, feedback-driven revise, degradation."""

from dataclasses import replace

import pytest

from apps.planner.drafting import HeuristicDrafter, PlanRequest, StaticDrafter
from apps.planner.gate import evaluate_plan
from apps.planner.loop import LoopConfig, run_react_loop
from apps.planner.schema import Plan, SubQuestion

from .support import default_setup, live_view_for, valid_plan


def _opportunity_only_draft() -> Plan:
    return Plan(
        request="x",
        target_sources=("opportunity_graph",),
        sub_questions=(
            SubQuestion(
                id="q1",
                text="Which grants are available?",
                source="opportunity_graph",
                entities=("Grant",),
                rationale="opportunity graph holds grants",
                max_traversal_depth=2,
                max_result_rows=10,
            ),
        ),
    )


def test_loop_converges_on_first_accepted_draft():
    registry, live = default_setup()
    drafter = StaticDrafter([valid_plan()])

    outcome = run_react_loop(PlanRequest("anything"), registry, live, drafter)

    assert outcome.converged
    assert outcome.iterations == 1
    assert len(outcome.plan.trace) == 1
    assert outcome.plan.trace[0].accepted
    assert evaluate_plan(outcome.plan, registry, live).accepted


def test_loop_revises_using_gate_feedback():
    registry, live = default_setup()
    # First draft declares an unused (live) source -> rejected; second is valid.
    bad = replace(
        valid_plan(),
        target_sources=("lab_graph", "evidence_graph", "opportunity_graph"),
    )
    drafter = StaticDrafter([bad, valid_plan()])

    outcome = run_react_loop(PlanRequest("anything"), registry, live, drafter)

    assert outcome.converged
    assert outcome.iterations == 2
    # The gate's rejection reason was fed into the second draft (briefing 5.2).
    assert drafter.contexts[1].prior_feedback
    assert any(
        "unnecessary source call" in r
        for r in drafter.contexts[1].prior_feedback
    )
    assert outcome.plan.trace[0].accepted is False
    assert outcome.plan.trace[1].accepted is True


def test_loop_degrades_to_partial_after_iteration_cap():
    registry = default_setup()[0]
    live = live_view_for(registry, down=["opportunity_graph"])
    drafter = StaticDrafter([_opportunity_only_draft()])  # always unroutable

    outcome = run_react_loop(
        PlanRequest("Which grants are available?"),
        registry,
        live,
        drafter,
        config=LoopConfig(max_iterations=3),
    )

    assert not outcome.converged
    assert outcome.iterations == 3
    assert len(drafter.contexts) == 3  # drafted on every iteration
    plan = outcome.plan
    assert plan.partial
    assert plan.sub_questions == ()  # the dead-source sub-question was dropped
    assert any(
        "not live" in part.reason for part in plan.unsupported_parts
    )
    # The loop's invariant: whatever it emits passes the gate.
    assert evaluate_plan(plan, registry, live).accepted
    # Trace records each rejected iteration plus the degradation step.
    assert len(plan.trace) == 4
    assert plan.trace[-1].accepted


def test_degradation_keeps_valid_sub_questions_and_drops_invalid_ones():
    registry = default_setup()[0]
    live = live_view_for(registry, down=["opportunity_graph"])
    good = valid_plan().sub_questions[0]  # on lab_graph (live), valid
    good = replace(good, join_keys=())  # drop cross-source key (single source now)
    bad = _opportunity_only_draft().sub_questions[0]  # on dead opportunity_graph
    mixed = Plan(
        request="x",
        target_sources=("lab_graph", "opportunity_graph"),
        sub_questions=(good, bad),
    )
    drafter = StaticDrafter([mixed])

    outcome = run_react_loop(
        PlanRequest("mixed"), registry, live, drafter, config=LoopConfig(2)
    )

    plan = outcome.plan
    assert not outcome.converged
    assert plan.target_sources == ("lab_graph",)
    assert [sq.id for sq in plan.sub_questions] == ["q1"]
    assert any(part.description == bad.text for part in plan.unsupported_parts)
    assert evaluate_plan(plan, registry, live).accepted


def test_loop_integrates_with_heuristic_drafter():
    registry, live = default_setup()

    outcome = run_react_loop(
        PlanRequest("Which findings support our claims?"),
        registry,
        live,
        HeuristicDrafter(),
    )

    assert outcome.converged
    assert outcome.iterations == 1
    assert outcome.plan.target_sources == ("evidence_graph",)
    assert evaluate_plan(outcome.plan, registry, live).accepted


def test_loop_config_rejects_zero_iterations():
    with pytest.raises(ValueError, match="max_iterations"):
        LoopConfig(max_iterations=0)
