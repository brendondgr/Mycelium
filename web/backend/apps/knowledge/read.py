"""The one read door into the knowledge core.

Every function here decides for itself which tiers it may return; none takes
the tier as an argument. That is the point: "conversation never makes a person
findable" is true because :func:`discoverable_edges` cannot be asked for
conversational edges, not because every caller remembers not to ask. The
boundary test pins which of these the collaboration app may import at all.

| Function | Tiers | Statuses | For |
|---|---|---|---|
| :func:`own_edges` | all | all | the person, about themselves |
| :func:`ranking_edges` | declared, conversational | active | the person's own ranking |
| :func:`lab_declared_edges` | declared | active | a lab's view of its members |
| :func:`discoverable_edges` | declared, demonstrated | active | collaboration search |
| :func:`project_edges` | declared | active | a viewer who can see the project |
| :func:`undeclared_project_concepts` | declared | active | the same viewer (Q1) |

Demonstrated edges (a person's papers) are deliberately absent from
:func:`ranking_edges`: letting them shape recommendations is a ranking change,
and a ranking change is made with an evaluation run behind it, not in passing.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from django.db.models import Q, QuerySet

from apps.research.models import Project

from .models import Concept, Edge, EdgeStatus, Relation, Tier

__all__ = [
    "EdgeView",
    "discoverable_edges",
    "lab_declared_edges",
    "own_edges",
    "project_edges",
    "ranking_edges",
    "undeclared_project_concepts",
]

_RANKING = Q(tier=Tier.DECLARED) | Q(tier=Tier.CONVERSATIONAL)
_DISCOVERABLE = Q(tier=Tier.DECLARED) | Q(tier=Tier.DEMONSTRATED)


@dataclass(frozen=True)
class EdgeView:
    """One edge as a reader sees it. No model instance leaves this module."""

    concept_id: int
    label: str
    facet: str
    relation: str
    tier: str
    status: str
    surface: str
    weight: float
    first_seen: datetime
    last_reinforced: datetime
    evidence: tuple
    user_id: int | None = None
    project_id: str | None = None
    lab_id: int | None = None

    @classmethod
    def of(cls, edge: Edge) -> EdgeView:
        return cls(
            concept_id=edge.concept_id,
            label=edge.concept.label,
            facet=edge.concept.facet,
            relation=edge.relation,
            tier=edge.tier,
            status=edge.status,
            surface=edge.surface,
            weight=edge.weight,
            first_seen=edge.first_seen,
            last_reinforced=edge.last_reinforced,
            evidence=tuple(edge.evidence or ()),
            user_id=edge.user_id,
            project_id=str(edge.project_id) if edge.project_id else None,
            lab_id=edge.lab_id,
        )


def _views(queryset: QuerySet) -> list[EdgeView]:
    return [
        EdgeView.of(edge)
        for edge in queryset.select_related("concept").order_by("concept__label", "pk")
    ]


def own_edges(user) -> list[EdgeView]:
    """Everything the graph holds about this person, for this person."""
    return _views(Edge.objects.filter(user=user))


def ranking_edges(user) -> list[EdgeView]:
    """What may shape this person's own recommendations.

    Declared edges, and conversational ones the person confirmed. A pending
    suggestion never ranks anything (ambient principle 9).
    """
    return _views(
        Edge.objects.filter(user=user, status=EdgeStatus.ACTIVE).filter(_RANKING)
    )


def lab_declared_edges(users: Iterable) -> list[EdgeView]:
    """Declared edges only, for a lab reading its own members.

    A lab-mate is named for something on the strength of what their profile
    states, because that is what they control (`team_gap.py`'s rule).
    """
    return _views(
        Edge.objects.filter(
            user__in=list(users), tier=Tier.DECLARED, status=EdgeStatus.ACTIVE
        )
    )


def discoverable_edges(users: Iterable) -> list[EdgeView]:
    """What collaboration search may know about people: never conversation.

    People only — a project's edges are that project's secret and never make
    anyone discoverable (design §9.2). Consent to be found is the caller's
    check (plan CN-04); this function only bounds what can be known.
    """
    return _views(
        Edge.objects.filter(
            user__in=list(users), user__isnull=False, status=EdgeStatus.ACTIVE
        ).filter(_DISCOVERABLE)
    )


def _visible_project(project, viewer) -> Project | None:
    pk = getattr(project, "pk", project)
    return Project.objects.visible_to(viewer).filter(pk=pk).first()


def project_edges(project, viewer) -> list[EdgeView]:
    """A project's declared edges, to a viewer who can already see the project."""
    visible = _visible_project(project, viewer)
    if visible is None:
        return []
    return _views(
        Edge.objects.filter(
            project=visible, tier=Tier.DECLARED, status=EdgeStatus.ACTIVE
        )
    )


#: The project relations a member could be expected to declare.
_PROJECT_CONTENT = (
    Relation.WORKS_ON,
    Relation.USES_METHOD,
    Relation.WORKS_IN_SETTING,
    Relation.NEEDS,
)


def _project_people(project: Project) -> list[int]:
    people = set(project.members.values_list("pk", flat=True))
    if project.scope_user_id:
        people.add(project.scope_user_id)
    return sorted(people)


def undeclared_project_concepts(project, viewer) -> list[EdgeView]:
    """Q1: which of this project's concepts does none of its people declare?

    The project's problem, method, setting, and need edges whose concept no
    member (nor the owner of a personal project) holds a declared edge to. It is
    the proof query for the graph (``docs/goals.md``, Next 1), and the shape
    plan CN-03's coverage marking generalises to requirement slots.
    """
    visible = _visible_project(project, viewer)
    if visible is None:
        return []
    declared_by_people = Concept.objects.filter(
        edges__user__in=_project_people(visible),
        edges__tier=Tier.DECLARED,
        edges__status=EdgeStatus.ACTIVE,
    )
    return _views(
        Edge.objects.filter(
            project=visible,
            tier=Tier.DECLARED,
            status=EdgeStatus.ACTIVE,
            relation__in=_PROJECT_CONTENT,
        ).exclude(concept__in=declared_by_people)
    )
