"""End-to-end tests for the wired PlanningAgent (discovery + loop + gate)."""

from apps.planner.discovery import FixedClock
from apps.planner.fixtures import default_registry
from apps.planner.gate import evaluate_plan
from apps.planner.planner import build_planning_agent

from .support import healthy_inspector


def test_agent_plans_an_evidence_question_end_to_end():
    registry = default_registry()
    agent = build_planning_agent(healthy_inspector(registry), registry=registry)

    outcome = agent.plan("Which findings support our claims?")

    assert outcome.converged
    assert outcome.plan.target_sources == ("evidence_graph",)
    assert evaluate_plan(outcome.plan, registry, agent.prober.live_view()).accepted


def test_agent_reprobes_liveness_each_request():
    registry = default_registry()
    inspector = healthy_inspector(registry)
    # cache_ttl=0 forces a fresh probe on every request (briefing 2.4).
    agent = build_planning_agent(
        inspector, registry=registry, cache_ttl=0.0, clock=FixedClock()
    )

    agent.plan("Which findings support our claims?")
    first = inspector.calls["evidence_graph"]
    agent.plan("Which findings support our claims?")
    second = inspector.calls["evidence_graph"]

    assert second > first


def test_agent_marks_down_source_unsupported_end_to_end():
    registry = default_registry()
    agent = build_planning_agent(
        healthy_inspector(registry, down=["opportunity_graph"]),
        registry=registry,
    )

    outcome = agent.plan("Which grants and fellowships are available?")

    assert outcome.plan.partial
    assert "opportunity_graph" not in outcome.plan.target_sources
    assert any(
        "opportunity_graph" in part.reason and "not live" in part.reason
        for part in outcome.plan.unsupported_parts
    )


def test_agent_handles_out_of_scope_request_end_to_end():
    registry = default_registry()
    agent = build_planning_agent(healthy_inspector(registry), registry=registry)

    outcome = agent.plan("What is the weather today?")

    assert outcome.plan.partial
    assert outcome.plan.sub_questions == ()
    assert any(
        "no live source" in part.reason
        for part in outcome.plan.unsupported_parts
    )


def test_public_api_is_importable_from_package_root():
    import apps.planner as planner

    assert hasattr(planner, "PlanningAgent")
    assert hasattr(planner, "build_planning_agent")
    assert hasattr(planner, "default_registry")
