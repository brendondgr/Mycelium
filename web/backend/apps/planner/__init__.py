"""Planning agent for routing research questions across lab knowledge graphs.

The planner reads source cards, learns which graphs are live, classifies a
request, and emits a machine-readable plan (target sources, sub-questions,
join keys, traversal limits, unsupported parts). It routes; it never queries.

See ``docs/plans/planning-agent.md`` for the failure-mode briefing this app
implements. The load-bearing principle: the drafter proposes a plan, a
deterministic self-evaluation gate decides whether it ships.
"""
