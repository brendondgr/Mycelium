"""Evaluating the planner: score the plan directly, not the downstream answer.

The planner is judged on its plan output, isolated from any later phase
(briefing 6.1). A case pairs a request with the expected routing; scoring
measures source-selection accuracy, sub-question entity coverage,
unnecessary-source-call count, schema adherence, and honest partiality. The
dataset (``eval_dataset.py``) holds a fixed, manually reviewed set including
out-of-scope and partially-answerable requests (briefing 6.2), split into a
development set and a never-tuned holdout (briefing 6.3).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from .cards import CardRegistry
from .discovery import static_live_view
from .drafting import HeuristicDrafter, PlanDrafter, PlanRequest
from .loop import LoopConfig, run_react_loop
from .schema import Plan, schema_errors


@dataclass(frozen=True)
class EvaluationCase:
    """A request paired with its expected routing (the reference plan)."""

    request: str
    expected_sources: frozenset[str]
    expected_entities: Mapping[str, frozenset[str]] = field(default_factory=dict)
    down_sources: frozenset[str] = frozenset()
    expect_partial: bool = False
    expect_unsupported_sources: frozenset[str] = frozenset()
    notes: str = ""


@dataclass(frozen=True)
class PlanScore:
    """How well one plan matched its expected plan."""

    request: str
    source_precision: float
    source_recall: float
    source_selection_correct: bool
    entity_recall: float
    unnecessary_source_calls: int
    schema_adherent: bool
    partial_correct: bool
    unsupported_correct: bool

    @property
    def passed(self) -> bool:
        return (
            self.source_selection_correct
            and self.unnecessary_source_calls == 0
            and self.entity_recall == 1.0
            and self.schema_adherent
            and self.partial_correct
            and self.unsupported_correct
        )


def _ratio(numerator: int, denominator: int) -> float:
    return 1.0 if denominator == 0 else numerator / denominator


def score_plan(plan: Plan, case: EvaluationCase) -> PlanScore:
    """Score a plan against an expected case. Pure: no cards, no live view."""

    targeted = set(plan.target_sources)
    expected = set(case.expected_sources)
    overlap = targeted & expected

    entities_by_source: dict[str, set[str]] = {}
    for sq in plan.sub_questions:
        entities_by_source.setdefault(sq.source, set()).update(sq.entities)

    recalls = []
    for source, expected_entities in case.expected_entities.items():
        if not expected_entities:
            continue
        found = entities_by_source.get(source, set())
        recalls.append(_ratio(len(expected_entities & found), len(expected_entities)))
    entity_recall = sum(recalls) / len(recalls) if recalls else 1.0

    unsupported_text = " ".join(
        f"{part.description} {part.reason}" for part in plan.unsupported_parts
    )
    unsupported_correct = all(
        source in unsupported_text for source in case.expect_unsupported_sources
    )

    return PlanScore(
        request=case.request,
        source_precision=_ratio(len(overlap), len(targeted)),
        source_recall=_ratio(len(overlap), len(expected)),
        source_selection_correct=(targeted == expected),
        entity_recall=entity_recall,
        unnecessary_source_calls=len(targeted - expected),
        schema_adherent=(schema_errors(plan) == []),
        partial_correct=(plan.partial == case.expect_partial),
        unsupported_correct=unsupported_correct,
    )


@dataclass(frozen=True)
class EvaluationReport:
    """Aggregate scores across a dataset."""

    scores: tuple[PlanScore, ...]

    @property
    def pass_rate(self) -> float:
        if not self.scores:
            return 1.0
        return sum(1 for s in self.scores if s.passed) / len(self.scores)

    @property
    def mean_source_recall(self) -> float:
        if not self.scores:
            return 1.0
        return sum(s.source_recall for s in self.scores) / len(self.scores)

    @property
    def schema_adherence_rate(self) -> float:
        if not self.scores:
            return 1.0
        return sum(1 for s in self.scores if s.schema_adherent) / len(self.scores)

    @property
    def total_unnecessary_source_calls(self) -> int:
        return sum(s.unnecessary_source_calls for s in self.scores)

    def failures(self) -> tuple[PlanScore, ...]:
        return tuple(s for s in self.scores if not s.passed)


def plan_for_case(
    case: EvaluationCase,
    registry: CardRegistry,
    drafter: PlanDrafter,
    *,
    config: LoopConfig | None = None,
) -> Plan:
    """Produce the planner's plan for a case under that case's liveness."""

    live_view = static_live_view(registry, down=case.down_sources)
    outcome = run_react_loop(
        PlanRequest(case.request),
        registry,
        live_view,
        drafter,
        config=config,
    )
    return outcome.plan


def evaluate_dataset(
    cases: Iterable[EvaluationCase],
    registry: CardRegistry,
    drafter: PlanDrafter | None = None,
    *,
    config: LoopConfig | None = None,
) -> EvaluationReport:
    """Run and score the planner across a set of cases."""

    drafter = drafter or HeuristicDrafter()
    scores = tuple(
        score_plan(plan_for_case(case, registry, drafter, config=config), case)
        for case in cases
    )
    return EvaluationReport(scores=scores)
