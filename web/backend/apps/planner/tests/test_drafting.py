"""Tests for the heuristic drafter: card-grounded routing and honest gaps."""

from apps.planner.drafting import DraftContext, HeuristicDrafter, PlanRequest
from apps.planner.gate import evaluate_plan

from .support import default_setup, live_view_for


def _draft(text, registry, live, *, feedback=()):
    drafter = HeuristicDrafter()
    context = DraftContext(registry=registry, live_view=live, prior_feedback=feedback)
    return drafter.draft(PlanRequest(text), context)


def test_routes_evidence_question_to_evidence_graph_only():
    registry, live = default_setup()

    plan = _draft("Which findings support our claims?", registry, live)

    assert plan.target_sources == ("evidence_graph",)
    sq = plan.sub_questions[0]
    assert sq.source == "evidence_graph"
    assert sq.entities == ("Claim", "Finding", "SUPPORTS")
    assert sq.rationale  # source-selection rationale recorded (briefing 3.1)
    # Limits drawn from the card's safety block (briefing 3.5).
    assert (sq.max_traversal_depth, sq.max_result_rows) == (5, 300)
    # 'our' is ambiguous; the drafter states its assumption (briefing 3.4).
    assert any("our" in a for a in plan.assumptions)
    assert evaluate_plan(plan, registry, live).accepted


def test_cross_source_routing_uses_declared_join_keys():
    registry, live = default_setup()

    plan = _draft(
        "Which projects do the authors of supported claims work on?",
        registry,
        live,
    )

    assert plan.target_sources == ("evidence_graph", "lab_graph")
    for sq in plan.sub_questions:
        # Both sources declare paper-doi and topic-id; the join rests on them.
        assert sq.join_keys == ("paper-doi", "topic-id")
    assert any("canonical keys" in a for a in plan.assumptions)
    assert evaluate_plan(plan, registry, live).accepted


def test_out_of_scope_request_is_marked_unsupported():
    registry, live = default_setup()

    plan = _draft("What is the weather today?", registry, live)

    assert plan.target_sources == ()
    assert plan.sub_questions == ()
    assert plan.partial
    assert any(
        "no live source" in part.reason for part in plan.unsupported_parts
    )
    assert evaluate_plan(plan, registry, live).accepted


def test_down_source_part_is_marked_unsupported_not_fabricated():
    registry = default_setup()[0]
    live = live_view_for(registry, down=["opportunity_graph"])

    plan = _draft("Which grants and fellowships are available?", registry, live)

    assert "opportunity_graph" not in plan.target_sources
    assert plan.partial
    assert any(
        "opportunity_graph" in part.reason and "not live" in part.reason
        for part in plan.unsupported_parts
    )
    assert evaluate_plan(plan, registry, live).accepted


def test_drafter_excludes_sources_flagged_by_prior_feedback():
    registry, live = default_setup()
    feedback = ("source 'lab_graph' card is inconsistent: drift",)

    plan = _draft(
        "Which projects do authors of supported claims work on?",
        registry,
        live,
        feedback=feedback,
    )

    assert plan.target_sources == ("evidence_graph",)
    assert plan.partial
    assert any(
        "lab_graph" in part.reason and "self-eval gate" in part.reason
        for part in plan.unsupported_parts
    )
    assert evaluate_plan(plan, registry, live).accepted
