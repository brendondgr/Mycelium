"""Intake asks for broad interests and ships a plan-sized cluster grouping.

Two guards behind the same report — onboarding produced hyper-specific research
areas (résumé bullets restated verbatim), and the synthesised grouping overflowed
the user's plan so the surplus landed in the organizer's Unsorted tray.
"""

from __future__ import annotations

import json

from apps.accounts.intake.extract import _SYSTEM_PROMPT as EXTRACT_PROMPT
from apps.accounts.intake.lab import _LAB_SYSTEM_PROMPT
from apps.accounts.intake.synthesize import synthesize_interests

_COMPOSED = json.dumps(
    {
        "clusters": [
            {"label": f"Theme {i}", "areas": [f"topic {i}a", f"topic {i}b"]}
            for i in range(5)
        ]
    }
)


def test_extraction_prompts_ask_for_broad_areas() -> None:
    for prompt in (EXTRACT_PROMPT, _LAB_SYSTEM_PROMPT):
        assert "BROAD research areas" in prompt
        assert "Generalise up" in prompt
        # Fine-grained detail is explicitly routed to keywords instead.
        assert "belongs here, not in areas" in prompt


def test_synthesis_clamps_clusters_to_the_plan() -> None:
    _draft, interests = synthesize_interests(
        resume_text="Built agentic pipelines over security knowledge graphs.",
        complete=lambda _p: _COMPOSED,
        max_clusters=3,
        max_areas_per_cluster=2,
    )
    clusters = interests["clusters"]
    assert len(clusters) == 3
    assert all(len(c["areas"]) <= 2 for c in clusters)
    # Areas are exactly the clusters' union, so nothing spills into Unsorted.
    assert interests["areas"] == [a for c in clusters for a in c["areas"]]


def test_synthesis_defaults_stay_uncapped_per_cluster() -> None:
    _draft, interests = synthesize_interests(
        resume_text="Built agentic pipelines over security knowledge graphs.",
        complete=lambda _p: _COMPOSED,
    )
    assert len(interests["clusters"]) == 5
