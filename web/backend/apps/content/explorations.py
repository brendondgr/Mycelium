"""Confirmed explorations as extra themes in a person's paper search.

Ambient Plan 05, step 8. When a person says yes to "include it in my reports"
(Plan 06), the topic becomes an active conversational edge in the knowledge
core — an **exploration**. Here, and only behind ``AMBIENT_DRIFT_ENABLED``, each
exploration joins the person's paper search as **its own theme**:

* **Per concept, never averaged.** Each exploration is a separate theme with
  its own query and its own slate, scored and ranked on its own — never folded
  into one blended vector, which would flatten mixed interests into a query
  that represents none of them (collaboration-network design §5.3).
* **Beside, never instead.** Declared areas, clusters and budget are untouched;
  an exploration spends no cluster or topic cap. Its themes come after the
  declared ones, so a tie always goes to what the person declared.
* **Capped.** In the global ranking an exploration theme's score counts at
  ``AMBIENT_DRIFT_WEIGHT`` of a declared theme's (``fusion.combine_clusters``'s
  ``cluster_weights``), so it cannot push a declared theme's paper out of the
  feed; its own slate still lists its best papers in their own order.

Off, this module returns the interests unchanged and no weights: byte-identical
ranking.
"""

from __future__ import annotations

from django.conf import settings

from apps.content.clustering import IMPLICIT_CLUSTER_ID, IMPLICIT_CLUSTER_LABEL

EXPLORE_PREFIX = "explore-"
EXPLORE_LABEL = "Exploring: {label}"


def for_user(user) -> list[tuple[int, str]]:
    """``[(concept id, the person's wording)]`` of what they confirmed exploring.

    Empty unless ``AMBIENT_DRIFT_ENABLED``. The person's own wording
    (``surface``) is used, never the shared concept label.
    """
    if not getattr(settings, "AMBIENT_DRIFT_ENABLED", False):
        return []
    from apps.knowledge.read import confirmed_explorations

    return [
        (edge.concept_id, edge.surface or edge.label)
        for edge in confirmed_explorations(user)
    ]


def is_exploration(cluster_id: str) -> bool:
    return str(cluster_id).startswith(EXPLORE_PREFIX)


def with_explorations(
    interests: dict, explorations: list[tuple[int, str]]
) -> tuple[dict, dict[str, float]]:
    """``(interests with exploration themes appended, their ranking weights)``.

    With no explorations, the very same dict and no weights.
    """
    if not explorations:
        return interests, {}
    areas = [str(a) for a in (interests.get("areas") or [])]
    declared = {a.casefold() for a in areas}
    clusters = list(interests.get("clusters") or [])
    if not clusters and areas:
        # An unclustered profile is one implicit theme; name it explicitly so
        # the declared theme stays first and the exploration themes follow.
        clusters = [
            {"id": IMPLICIT_CLUSTER_ID, "label": IMPLICIT_CLUSTER_LABEL, "areas": areas}
        ]
    weight = float(getattr(settings, "AMBIENT_DRIFT_WEIGHT", 0.15))
    weights: dict[str, float] = {}
    extra_areas: list[str] = []
    for concept_id, label in explorations:
        text = " ".join(str(label).split())
        if not text or text.casefold() in declared:
            continue  # already declared: the declared theme already searches it
        declared.add(text.casefold())
        cluster_id = f"{EXPLORE_PREFIX}{concept_id}"
        extra_areas.append(text)
        clusters.append(
            {
                "id": cluster_id,
                "label": EXPLORE_LABEL.format(label=text),
                "areas": [text],
            }
        )
        weights[cluster_id] = weight
    if not weights:
        return interests, {}
    return {**interests, "areas": areas + extra_areas, "clusters": clusters}, weights
