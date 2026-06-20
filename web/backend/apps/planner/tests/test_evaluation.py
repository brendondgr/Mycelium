"""Tests for the evaluation harness: the scorer and the frozen dataset."""

from dataclasses import replace

from apps.planner.eval_dataset import DEVELOPMENT_CASES, HOLDOUT_CASES
from apps.planner.evaluation import EvaluationCase, evaluate_dataset, score_plan
from apps.planner.fixtures import default_registry

from .support import valid_plan


def test_score_plan_rewards_a_perfect_match():
    plan = valid_plan()
    case = EvaluationCase(
        request=plan.request,
        expected_sources=frozenset({"lab_graph", "evidence_graph"}),
        expected_entities={
            "lab_graph": frozenset({"Person", "Project", "WORKS_ON"}),
            "evidence_graph": frozenset({"Claim", "Finding", "SUPPORTS"}),
        },
    )

    score = score_plan(plan, case)

    assert score.passed
    assert score.source_selection_correct
    assert score.source_precision == 1.0
    assert score.source_recall == 1.0
    assert score.entity_recall == 1.0
    assert score.unnecessary_source_calls == 0


def test_score_plan_penalizes_misrouting_and_unnecessary_calls():
    plan = valid_plan()  # targets lab_graph + evidence_graph
    case = EvaluationCase(
        request=plan.request,
        expected_sources=frozenset({"evidence_graph"}),
    )

    score = score_plan(plan, case)

    assert not score.passed
    assert not score.source_selection_correct
    assert score.unnecessary_source_calls == 1  # lab_graph was not expected
    assert score.source_recall == 1.0  # evidence_graph still covered
    assert score.source_precision == 0.5


def test_score_plan_flags_schema_violations():
    plan = valid_plan()
    broken_sq = replace(plan.sub_questions[0], rationale="")
    broken = replace(plan, sub_questions=(broken_sq, plan.sub_questions[1]))
    case = EvaluationCase(
        request=plan.request,
        expected_sources=frozenset({"lab_graph", "evidence_graph"}),
    )

    score = score_plan(broken, case)

    assert not score.schema_adherent
    assert not score.passed


def test_score_plan_checks_partial_and_unsupported_expectations():
    plan = valid_plan()
    # Plan is not partial, but the case expects partiality.
    mismatched = EvaluationCase(
        request=plan.request,
        expected_sources=frozenset({"lab_graph", "evidence_graph"}),
        expect_partial=True,
    )
    assert not score_plan(plan, mismatched).partial_correct


def test_development_set_passes_and_is_clean():
    report = evaluate_dataset(DEVELOPMENT_CASES, default_registry())

    assert report.pass_rate == 1.0
    assert report.schema_adherence_rate == 1.0
    assert report.total_unnecessary_source_calls == 0
    assert report.failures() == ()


def test_holdout_set_passes_as_regression_check():
    report = evaluate_dataset(HOLDOUT_CASES, default_registry())

    assert report.pass_rate == 1.0
    assert report.mean_source_recall == 1.0


def test_dataset_exercises_unsupported_and_out_of_scope_paths():
    # The dataset must test honest degradation, not just the happy path.
    assert any(c.expect_partial and not c.expected_sources
               for c in DEVELOPMENT_CASES)  # out-of-scope
    assert any(c.down_sources for c in DEVELOPMENT_CASES)  # down-source
    assert any(c.expect_unsupported_sources for c in HOLDOUT_CASES)
