"""The recommendation read door: what other tools and the platform read about
how the corpus fits a person, lab, department or project.

The names below are the stable surface. The modules listed in the tool's
``exports`` are still imported directly by code that predates the doors (the
delivery code above all); new code reads through this module.
"""

from tools.recommendation.models import (
    TARGET_FIELDS,
    ItemComprehension,
    ProjectProfile,
    RelevanceEvent,
    RelevanceScore,
)
from tools.recommendation.slates import cluster_entries, slate_depth
from tools.recommendation.targets import (
    target_for_department,
    target_for_lab,
    target_for_project,
    target_for_user,
)
from tools.recommendation.top_feed import (
    entrant_ids,
    in_slate,
    is_entrant,
    order_by_slate,
    top_n,
)
from tools.recommendation.vectors import cosine, member_vector

__all__ = [
    "TARGET_FIELDS",
    "ItemComprehension",
    "ProjectProfile",
    "RelevanceEvent",
    "RelevanceScore",
    "cluster_entries",
    "cosine",
    "entrant_ids",
    "in_slate",
    "is_entrant",
    "member_vector",
    "order_by_slate",
    "slate_depth",
    "target_for_department",
    "target_for_lab",
    "target_for_project",
    "target_for_user",
    "top_n",
]
