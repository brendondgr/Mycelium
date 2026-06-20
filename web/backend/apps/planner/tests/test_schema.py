"""Tests for the plan schema: serialization round-trips and schema adherence."""

from apps.planner.schema import (
    Plan,
    PlanTraceEntry,
    SubQuestion,
    UnsupportedPart,
    schema_errors,
)


def _well_formed_plan() -> Plan:
    return Plan(
        request="Which papers support our claims and what grants fit those topics?",
        target_sources=("evidence_graph", "opportunity_graph"),
        sub_questions=(
            SubQuestion(
                id="q1",
                text="Which findings support claims about our topics?",
                source="evidence_graph",
                entities=("Finding", "Claim", "SUPPORTS"),
                rationale="Evidence graph holds claims and supporting findings.",
                max_traversal_depth=3,
                max_result_rows=100,
                join_keys=("topic-id",),
                edge_patterns=(("Finding", "SUPPORTS", "Claim"),),
            ),
            SubQuestion(
                id="q2",
                text="Which grants are about those topics?",
                source="opportunity_graph",
                entities=("Grant", "Topic", "ABOUT"),
                rationale="Opportunity graph holds grants and their topics.",
                max_traversal_depth=2,
                max_result_rows=50,
                join_keys=("topic-id",),
            ),
        ),
        unsupported_parts=(
            UnsupportedPart(
                description="ranking grants by award size",
                reason="award size is not in any live source's card",
            ),
        ),
        assumptions=("'our topics' means topics linked to the lab's projects.",),
        partial=True,
        trace=(
            PlanTraceEntry(iteration=1, thought="route to evidence + opportunity",
                           accepted=True),
        ),
    )


def test_plan_round_trips_through_dict():
    plan = _well_formed_plan()

    restored = Plan.from_dict(plan.to_dict())

    assert restored == plan


def test_well_formed_plan_has_no_schema_errors():
    assert schema_errors(_well_formed_plan()) == []


def test_sources_used_and_addresses_something():
    plan = _well_formed_plan()

    assert plan.sources_used() == {"evidence_graph", "opportunity_graph"}
    assert plan.addresses_something()

    empty = Plan(request="x", target_sources=(), sub_questions=())
    assert not empty.addresses_something()


def test_schema_errors_flags_structural_problems():
    bad = Plan(
        request="x",
        target_sources=("evidence_graph",),
        sub_questions=(
            SubQuestion(
                id="dup",
                text="ok",
                source="evidence_graph",
                entities=("Claim",),
                rationale="because",
                max_traversal_depth=1,
                max_result_rows=10,
            ),
            SubQuestion(
                id="dup",  # duplicate id
                text="   ",  # blank text
                source="",  # blank source
                entities=(),  # no entities
                rationale="",  # no rationale
                max_traversal_depth=0,  # invalid / omitted limit
                max_result_rows=0,  # invalid / omitted limit
            ),
        ),
        unsupported_parts=(UnsupportedPart(description="", reason=""),),
    )

    errors = " | ".join(schema_errors(bad))

    assert "duplicate id" in errors
    assert "missing text" in errors
    assert "missing source" in errors
    assert "at least one entity" in errors
    assert "missing source-selection rationale" in errors
    assert "max_traversal_depth" in errors
    assert "max_result_rows" in errors
    assert "unsupported part #0: missing description" in errors
    assert "unsupported part #0: missing reason" in errors


def test_empty_plan_is_schema_valid_but_addresses_nothing():
    # Structural validity is not the same as non-degeneracy (that is the gate's job).
    empty = Plan(request="x", target_sources=(), sub_questions=())

    assert schema_errors(empty) == []
    assert not empty.addresses_something()
