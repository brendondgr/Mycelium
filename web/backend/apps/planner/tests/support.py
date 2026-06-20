"""Shared test builders (not a test module — no ``test_`` prefix)."""

from collections.abc import Iterable

from apps.planner.cards import CardRegistry
from apps.planner.discovery import (
    GraphSnapshot,
    LiveSourceView,
    ProbeUnreachable,
    StaticInspector,
    static_live_view,
)
from apps.planner.fixtures import default_registry
from apps.planner.schema import Plan, SubQuestion


def live_view_for(
    registry: CardRegistry, down: Iterable[str] = ()
) -> LiveSourceView:
    """An all-live view for a registry, optionally marking some sources down."""

    return static_live_view(registry, down=down)


def valid_plan() -> Plan:
    """A plan the gate accepts against the default registry, all sources live.

    Exercises a real cross-source join on the canonical ``paper-doi`` key,
    which both lab_graph and evidence_graph declare.
    """

    return Plan(
        request="Which projects do authors of our supported claims work on?",
        target_sources=("lab_graph", "evidence_graph"),
        sub_questions=(
            SubQuestion(
                id="q1",
                text="Which people work on which projects?",
                source="lab_graph",
                entities=("Person", "Project", "WORKS_ON"),
                rationale="Lab graph holds people and the projects they work on.",
                max_traversal_depth=3,
                max_result_rows=100,
                join_keys=("paper-doi",),
                edge_patterns=(("Person", "WORKS_ON", "Project"),),
            ),
            SubQuestion(
                id="q2",
                text="Which findings support which claims?",
                source="evidence_graph",
                entities=("Claim", "Finding", "SUPPORTS"),
                rationale="Evidence graph holds claims and supporting findings.",
                max_traversal_depth=4,
                max_result_rows=100,
                join_keys=("paper-doi",),
                edge_patterns=(("Finding", "SUPPORTS", "Claim"),),
            ),
        ),
    )


def healthy_inspector(
    registry: CardRegistry, down: Iterable[str] = ()
) -> StaticInspector:
    """A StaticInspector where every source passes its content probe.

    Sources named in ``down`` instead raise to simulate a dead backend.
    """

    down_set = set(down)
    snapshots: dict = {}
    for card in registry:
        if card.name in down_set:
            snapshots[card.name] = ProbeUnreachable("down for test")
        else:
            snapshots[card.name] = GraphSnapshot(
                present_labels=card.node_labels,
                node_count=card.probe.min_node_count + 5,
            )
    return StaticInspector(snapshots)


def default_setup():
    """Return ``(registry, live_view)`` with all default sources live."""

    registry = default_registry()
    return registry, live_view_for(registry)
