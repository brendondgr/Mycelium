"""The top-level planning agent: discovery + drafting + gate, wired together.

``PlanningAgent.plan`` re-probes liveness per request (briefing 2.4), then runs
the self-evaluating ReAct loop over that fresh live-source view. It routes; it
never queries. The agent is built from an injectable inspector so it runs
fully offline in tests and against Neo4j in production.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from .cards import CardRegistry
from .discovery import GraphInspector, Neo4jInspector, SourceProber
from .drafting import HeuristicDrafter, PlanDrafter, PlanRequest
from .fixtures import default_registry
from .loop import LoopConfig, PlanningOutcome, run_react_loop


@dataclass
class PlanningAgent:
    """Routes a request into a validated, bounded plan."""

    registry: CardRegistry
    prober: SourceProber
    drafter: PlanDrafter
    config: LoopConfig

    def plan(self, request: str | PlanRequest) -> PlanningOutcome:
        req = request if isinstance(request, PlanRequest) else PlanRequest(request)
        live_view = self.prober.live_view()  # re-probe per request (briefing 2.4)
        return run_react_loop(
            req, self.registry, live_view, self.drafter, config=self.config
        )


def build_planning_agent(
    inspector: GraphInspector,
    *,
    registry: CardRegistry | None = None,
    drafter: PlanDrafter | None = None,
    config: LoopConfig | None = None,
    probe_timeout: float = 2.0,
    cache_ttl: float = 3.0,
    clock: Callable[[], float] = time.monotonic,
) -> PlanningAgent:
    """Wire a planning agent from an inspector, defaulting the rest."""

    registry = registry or default_registry()
    prober = SourceProber(
        registry,
        inspector,
        timeout=probe_timeout,
        cache_ttl=cache_ttl,
        clock=clock,
    )
    return PlanningAgent(
        registry=registry,
        prober=prober,
        drafter=drafter or HeuristicDrafter(),
        config=config or LoopConfig(),
    )


def neo4j_inspector_from_settings(settings) -> Neo4jInspector:
    """Production seam: a Neo4j-backed inspector built from Django settings.

    All Mycelium graphs currently share one Neo4j backend, so every source maps
    to the same driver. Lazily imports the driver so importing this module never
    requires a live database.
    """

    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD),
    )
    return Neo4jInspector(driver_for=lambda _name: driver)
