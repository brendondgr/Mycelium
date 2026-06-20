"""Fixed (request -> expected plan) cases for scoring the planner.

Manually reviewed reference plans over the built-in Mycelium graphs
(briefing 6.2). The set deliberately includes single-source, cross-source,
out-of-scope, and down-source requests so the "mark unsupported" behavior is
tested, not just the happy path. ``DEVELOPMENT_CASES`` may be used while
tuning; ``HOLDOUT_CASES`` are frozen regression checks never used for tuning
(briefing 6.3).
"""

from __future__ import annotations

from .evaluation import EvaluationCase

DEVELOPMENT_CASES: tuple[EvaluationCase, ...] = (
    EvaluationCase(
        request="Which findings support our claims?",
        expected_sources=frozenset({"evidence_graph"}),
        expected_entities={
            "evidence_graph": frozenset({"Claim", "Finding", "SUPPORTS"})
        },
        notes="Single-source evidence routing.",
    ),
    EvaluationCase(
        request="Which lab members work on which projects?",
        expected_sources=frozenset({"lab_graph"}),
        expected_entities={
            "lab_graph": frozenset({"Lab", "Person", "Project", "WORKS_ON"})
        },
        notes="Single-source lab routing.",
    ),
    EvaluationCase(
        request="Which grants and fellowships are open, and what are their "
        "deadlines?",
        expected_sources=frozenset({"opportunity_graph"}),
        expected_entities={
            "opportunity_graph": frozenset({"Grant", "Fellowship", "Deadline"})
        },
        notes="Single-source opportunity routing with an ambiguous 'their'.",
    ),
    EvaluationCase(
        request="Which datasets are used by papers that our members authored?",
        expected_sources=frozenset({"evidence_graph", "lab_graph"}),
        expected_entities={
            "evidence_graph": frozenset({"Dataset", "USES", "Paper"}),
            "lab_graph": frozenset({"Paper", "Person", "AUTHORED_BY"}),
        },
        notes="Cross-source join bridged by papers.",
    ),
    EvaluationCase(
        request="What is the weather today?",
        expected_sources=frozenset(),
        expect_partial=True,
        notes="Out-of-scope: no live source covers it.",
    ),
    EvaluationCase(
        request="Which grants are available?",
        expected_sources=frozenset(),
        down_sources=frozenset({"opportunity_graph"}),
        expect_partial=True,
        expect_unsupported_sources=frozenset({"opportunity_graph"}),
        notes="Answerable in principle, but the only relevant source is down.",
    ),
)

HOLDOUT_CASES: tuple[EvaluationCase, ...] = (
    EvaluationCase(
        request="What evidence contradicts our claims?",
        expected_sources=frozenset({"evidence_graph"}),
        expected_entities={
            "evidence_graph": frozenset(
                {"Claim", "CONTRADICTS", "Finding", "SUPPORTS"}
            )
        },
        notes="Holdout: evidence routing, different phrasing.",
    ),
    EvaluationCase(
        request="Which fellowships have approaching deadlines and eligibility "
        "rules?",
        expected_sources=frozenset({"opportunity_graph"}),
        expected_entities={
            "opportunity_graph": frozenset(
                {"Fellowship", "Deadline", "EligibilityRule"}
            )
        },
        notes="Holdout: opportunity routing.",
    ),
    EvaluationCase(
        request="Which research areas do our projects cover?",
        expected_sources=frozenset({"lab_graph"}),
        expected_entities={
            "lab_graph": frozenset({"Project", "ResearchArea"})
        },
        notes="Holdout: lab routing.",
    ),
    EvaluationCase(
        request="Which findings support our claims?",
        expected_sources=frozenset(),
        down_sources=frozenset({"evidence_graph"}),
        expect_partial=True,
        expect_unsupported_sources=frozenset({"evidence_graph"}),
        notes="Holdout: relevant source down, must degrade honestly.",
    ),
)
