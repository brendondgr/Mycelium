"""Planning agent for routing research questions across lab knowledge graphs.

The planner reads source cards, learns which graphs are live, classifies a
request, and emits a machine-readable plan (target sources, sub-questions,
join keys, traversal limits, unsupported parts). It routes; it never queries.

See ``docs/plans/planning-agent.md`` for the failure-mode briefing this app
implements. The load-bearing principle: the drafter proposes a plan, a
deterministic self-evaluation gate decides whether it ships.
"""


def __getattr__(name: str):
    # Lazy public API so importing the Django app package stays cheap and
    # side-effect free while callers still get a flat import surface.
    if name in _LAZY_EXPORTS:
        module = __import__(
            f"apps.planner.{_LAZY_EXPORTS[name]}", fromlist=[name]
        )
        return getattr(module, name)
    raise AttributeError(f"module 'apps.planner' has no attribute '{name}'")


_LAZY_EXPORTS = {
    "PlanningAgent": "planner",
    "build_planning_agent": "planner",
    "neo4j_inspector_from_settings": "planner",
    "PlanRequest": "drafting",
    "HeuristicDrafter": "drafting",
    "LoopConfig": "loop",
    "PlanningOutcome": "loop",
    "default_registry": "fixtures",
}

__all__ = sorted(_LAZY_EXPORTS)
