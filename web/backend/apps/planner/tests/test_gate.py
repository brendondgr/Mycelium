"""Tests for the deterministic self-eval gate: accept good, reject unroutable."""

from dataclasses import replace

from apps.planner.cards import (
    CardRegistry,
    EdgePattern,
    ProbeExpectations,
    SafetyLimits,
    SourceCard,
)
from apps.planner.gate import evaluate_plan, sub_question_errors
from apps.planner.schema import Plan, SubQuestion, UnsupportedPart

from .support import default_setup, live_view_for, valid_plan


def test_gate_accepts_a_valid_plan():
    registry, live = default_setup()

    result = evaluate_plan(valid_plan(), registry, live)

    assert result.accepted
    assert result.reasons == ()


def test_gate_rejects_dead_target_source():
    registry = default_setup()[0]
    live = live_view_for(registry, down=["evidence_graph"])

    result = evaluate_plan(valid_plan(), registry, live)

    assert not result.accepted
    assert any("is not live" in r for r in result.reasons)


def test_gate_rejects_unknown_source():
    registry, live = default_setup()
    plan = valid_plan()
    bad_sq = replace(plan.sub_questions[1], source="ghost_graph")
    plan = replace(
        plan,
        target_sources=("lab_graph", "ghost_graph"),
        sub_questions=(plan.sub_questions[0], bad_sq),
    )

    result = evaluate_plan(plan, registry, live)

    assert not result.accepted
    assert any("not a known source" in r for r in result.reasons)


def test_gate_rejects_nonexistent_entity():
    registry, live = default_setup()
    plan = valid_plan()
    bad_sq = replace(plan.sub_questions[0], entities=("Person", "Grant"))
    plan = replace(plan, sub_questions=(bad_sq, plan.sub_questions[1]))

    result = evaluate_plan(plan, registry, live)

    assert not result.accepted
    assert any("entity 'Grant' does not exist" in r for r in result.reasons)


def test_gate_rejects_disallowed_edge_pattern():
    registry, live = default_setup()
    plan = valid_plan()
    bad_sq = replace(
        plan.sub_questions[0], edge_patterns=(("Person", "WORKS_ON", "Paper"),)
    )
    plan = replace(plan, sub_questions=(bad_sq, plan.sub_questions[1]))

    result = evaluate_plan(plan, registry, live)

    assert not result.accepted
    assert any("not an allowed pattern" in r for r in result.reasons)


def test_gate_rejects_limits_over_card_bounds():
    registry, live = default_setup()
    plan = valid_plan()
    # lab_graph allows depth 4 / rows 200.
    bad_sq = replace(
        plan.sub_questions[0], max_traversal_depth=9, max_result_rows=9999
    )
    plan = replace(plan, sub_questions=(bad_sq, plan.sub_questions[1]))

    result = evaluate_plan(plan, registry, live)

    assert not result.accepted
    assert any("max_traversal_depth 9 exceeds" in r for r in result.reasons)
    assert any("max_result_rows 9999 exceeds" in r for r in result.reasons)


def test_gate_rejects_join_key_not_declared_on_source():
    registry, live = default_setup()
    plan = valid_plan()
    # person-orcid is only declared on lab_graph, not evidence_graph.
    bad_sq = replace(plan.sub_questions[1], join_keys=("person-orcid",))
    plan = replace(plan, sub_questions=(plan.sub_questions[0], bad_sq))

    result = evaluate_plan(plan, registry, live)

    assert not result.accepted
    assert any(
        "join key 'person-orcid' is not declared" in r for r in result.reasons
    )


def test_gate_rejects_cross_source_join_not_present_in_both():
    registry, live = default_setup()
    # paper-doi exists on lab_graph + evidence_graph but NOT opportunity_graph.
    plan = Plan(
        request="link papers to grants by doi",
        target_sources=("lab_graph", "opportunity_graph"),
        sub_questions=(
            SubQuestion(
                id="q1",
                text="papers about topics",
                source="lab_graph",
                entities=("Paper", "Topic"),
                rationale="lab graph has papers",
                max_traversal_depth=2,
                max_result_rows=50,
                join_keys=("paper-doi",),
            ),
            SubQuestion(
                id="q2",
                text="grants by paper doi",
                source="opportunity_graph",
                entities=("Grant",),
                rationale="opportunity graph has grants",
                max_traversal_depth=2,
                max_result_rows=50,
                join_keys=("paper-doi",),
            ),
        ),
    )

    result = evaluate_plan(plan, registry, live)

    assert not result.accepted
    # Fails both the per-source declaration check and the cross-source check.
    assert any("paper-doi" in r and "not declared" in r for r in result.reasons)
    assert any("not declared canonical across" in r for r in result.reasons)


def test_gate_rejects_degenerate_plan():
    registry, live = default_setup()
    empty = Plan(request="anything", target_sources=(), sub_questions=())

    result = evaluate_plan(empty, registry, live)

    assert not result.accepted
    assert any("degenerate plan" in r for r in result.reasons)


def test_gate_rejects_unsupported_parts_without_partial_flag():
    registry, live = default_setup()
    plan = replace(
        valid_plan(),
        unsupported_parts=(
            UnsupportedPart(description="award sizes", reason="not in any card"),
        ),
        partial=False,
    )

    result = evaluate_plan(plan, registry, live)

    assert not result.accepted
    assert any("not marked partial" in r for r in result.reasons)


def test_gate_accepts_honest_partial_plan():
    registry, live = default_setup()
    plan = replace(
        valid_plan(),
        unsupported_parts=(
            UnsupportedPart(
                description="rank grants by award size",
                reason="award size is not in any live source's card",
            ),
        ),
        assumptions=("'our claims' means claims linked to lab projects.",),
        partial=True,
    )

    result = evaluate_plan(plan, registry, live)

    assert result.accepted


def test_gate_rejects_unused_target_source():
    registry, live = default_setup()
    plan = replace(valid_plan(), target_sources=("lab_graph", "opportunity_graph"))

    result = evaluate_plan(plan, registry, live)

    assert not result.accepted
    assert any("unnecessary source call" in r for r in result.reasons)


def test_gate_rejects_source_not_in_target_sources():
    registry, live = default_setup()
    plan = replace(valid_plan(), target_sources=("lab_graph",))

    result = evaluate_plan(plan, registry, live)

    assert not result.accepted
    assert any("is not in target_sources" in r for r in result.reasons)


def test_gate_short_circuits_on_schema_errors():
    registry, live = default_setup()
    plan = valid_plan()
    # Blank rationale is a structural problem, not a ground-truth one.
    bad_sq = replace(plan.sub_questions[0], rationale="")
    plan = replace(plan, sub_questions=(bad_sq, plan.sub_questions[1]))

    result = evaluate_plan(plan, registry, live)

    assert not result.accepted
    assert any("missing source-selection rationale" in r for r in result.reasons)


def test_gate_rechecks_card_consistency_before_trusting_it():
    # A live source whose card prose drifts from its structure (briefing 1.1):
    # the edge pattern references label 'B' that is not in node_labels.
    inconsistent = SourceCard(
        name="bad_graph",
        title="Bad Graph",
        description="card drift",
        node_labels=frozenset({"A"}),
        relationship_types=frozenset({"R"}),
        allowed_edge_patterns=(EdgePattern("A", "R", "B"),),
        safety=SafetyLimits(max_traversal_depth=2, max_result_rows=10),
        probe=ProbeExpectations(expected_labels=frozenset({"A"})),
    )
    registry = CardRegistry([inconsistent])
    live = live_view_for(registry)
    plan = Plan(
        request="x",
        target_sources=("bad_graph",),
        sub_questions=(
            SubQuestion(
                id="q1",
                text="touch A",
                source="bad_graph",
                entities=("A",),
                rationale="A exists in the card",
                max_traversal_depth=1,
                max_result_rows=5,
            ),
        ),
    )

    result = evaluate_plan(plan, registry, live)

    assert not result.accepted
    assert any("card is inconsistent" in r for r in result.reasons)


def test_sub_question_errors_isolates_one_sub_question():
    registry, live = default_setup()
    good = valid_plan().sub_questions[0]
    assert sub_question_errors(good, ("lab_graph",), registry, live) == []

    bad = replace(good, entities=("Grant",), source="lab_graph")
    errors = sub_question_errors(bad, ("lab_graph",), registry, live)
    assert any("entity 'Grant' does not exist" in e for e in errors)
