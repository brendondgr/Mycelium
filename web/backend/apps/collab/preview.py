"""Exactly what a seeker would see about a person (plan CN-04, design §9.4).

A coarse pointer: their name, the institution their verified email places
them at, and — per facet — the concepts a search could match them on, each
tagged with where it comes from. Nothing else: no email, no papers, no
projects. It reads only :func:`apps.knowledge.read.discoverable_edges`, which
cannot return anything conversation taught the graph and never a project's
edges, so the preview can only ever list what a search could.
"""

from __future__ import annotations

from collections import defaultdict

from apps.core.people import display_name
from apps.knowledge.read import discoverable_edges

from .affiliation import refresh

FACET_ORDER = ("problem", "method", "setting", "area")
TIER_LABEL = {"declared": "from your profile", "demonstrated": "from your papers"}
PER_FACET = 12


def preview(user) -> dict:
    affiliation = refresh(user)
    grouped: dict[str, dict[int, dict]] = defaultdict(dict)
    for edge in discoverable_edges([user]):
        entry = grouped[edge.facet].setdefault(
            edge.concept_id,
            {"label": edge.surface or edge.label, "sources": [], "weight": 0.0},
        )
        label = TIER_LABEL.get(edge.tier)
        if label and label not in entry["sources"]:
            entry["sources"].append(label)
        entry["weight"] = max(entry["weight"], edge.weight)
    facets = {
        facet: [
            {"label": item["label"], "sources": sorted(item["sources"])}
            for item in sorted(
                grouped[facet].values(),
                key=lambda item: (
                    -len(item["sources"]),
                    -item["weight"],
                    item["label"],
                ),
            )[:PER_FACET]
        ]
        for facet in FACET_ORDER
        if grouped.get(facet)
    }
    return {
        "name": display_name(user),
        "institution": affiliation.institution if affiliation else "",
        "facets": facets,
    }
