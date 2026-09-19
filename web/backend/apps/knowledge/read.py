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
| :func:`backing` | declared, demonstrated | active | the person themselves (Q2) |
| :func:`network_of` | — (co-authorship) | — | collaboration search (CN-07) |
| :func:`coauthor_distances` | — (co-authorship) | — | collaboration search (CN-07) |
| :func:`introduction_paths` | — (co-authorship) | — | collaboration search (CN-07) |
| :func:`evidence_texts` | declared, demonstrated | active | harm checks (CN-08) |
| :func:`privately_held_global_concepts` | — (a count) | active | harm checks (CN-08) |

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
    "Backing",
    "EdgeView",
    "backing",
    "WorkView",
    "coauthor_distances",
    "concept_vectors",
    "discoverable_edges",
    "discoverable_works",
    "evidence_texts",
    "introduction_paths",
    "lab_declared_edges",
    "network_of",
    "own_edges",
    "privately_held_global_concepts",
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


@dataclass(frozen=True)
class Backing:
    """One concept a person holds, and whether they said it, showed it, or both."""

    concept_id: int
    label: str
    surface: str
    declared: bool
    demonstrated: bool
    works: tuple[str, ...] = ()

    @property
    def declared_only(self) -> bool:
        return self.declared and not self.demonstrated


def backing(user) -> list[Backing]:
    """Q2: which of a person's declared concepts their own papers back.

    Every concept the person declares or their papers demonstrate, with the
    works that demonstrate it. Declared-only claims are cheap to make and are
    shown as visibly weaker (design §5.4); demonstrated-only ones are what
    their papers show that their profile does not say. For the person
    themselves, and for the preview of what a collaboration search could see.
    """
    rows = (
        Edge.objects.filter(
            user=user,
            status=EdgeStatus.ACTIVE,
            tier__in=[Tier.DECLARED, Tier.DEMONSTRATED],
        )
        .select_related("concept")
        .order_by("concept__label", "tier", "pk")
    )
    found: dict[int, dict] = {}
    for edge in rows:
        entry = found.setdefault(
            edge.concept_id,
            {
                "label": edge.concept.label,
                "surface": "",
                "declared": False,
                "demonstrated": False,
                "works": [],
            },
        )
        if edge.tier == Tier.DECLARED:
            entry["declared"] = True
            entry["surface"] = edge.surface or entry["surface"]
        else:
            entry["demonstrated"] = True
            entry["surface"] = entry["surface"] or edge.surface
            for item in edge.evidence or []:
                work = str(item).removeprefix("work:")
                if work not in entry["works"]:
                    entry["works"].append(work)
    return [
        Backing(
            concept_id=concept_id,
            label=entry["label"],
            surface=entry["surface"] or entry["label"],
            declared=entry["declared"],
            demonstrated=entry["demonstrated"],
            works=tuple(entry["works"]),
        )
        for concept_id, entry in found.items()
    ]


def concept_vectors(concept_ids: Iterable[int]) -> dict[int, list[float]]:
    """The embedding of each named concept, for comparing a phrase with it.

    A concept's vector says nothing about who holds it, so this carries no tier
    rule of its own: a caller only has concept ids from edges some other
    function here already let it see.
    """
    rows = Concept.objects.filter(
        pk__in=list(concept_ids), embedding__isnull=False
    ).values_list("pk", "embedding")
    return {pk: [float(v) for v in vector] for pk, vector in rows}


@dataclass(frozen=True)
class WorkView:
    """One of a person's own published works, as facets and vectors.

    What collaboration retrieval ranks (design §5.2): works first, then their
    authors. Published and public, so it carries no tier rule beyond "not
    thin" — but it is still read only through here.
    """

    work_id: str
    user_id: int
    year: int | None
    field: str
    problem: str
    method: str
    method_neutral: str
    setting: str
    reusable: str
    vectors: dict  # facet -> list[float]; missing facets are absent


_WORK_VECTORS = (
    ("problem", "problem_vec"),
    ("method", "method_vec"),
    ("method_neutral", "method_neutral_vec"),
    ("setting", "setting_vec"),
    ("reusable", "reusable_vec"),
)


def discoverable_works(users: Iterable) -> list[WorkView]:
    """The non-thin, read works of these people, with a vector per facet."""
    from .models import WorkFacets

    rows = WorkFacets.objects.filter(
        author_work__user__in=list(users), thin=False
    ).select_related("author_work")
    out = []
    for row in rows:
        work = row.author_work
        vectors = {
            name: [float(v) for v in getattr(row, field)]
            for name, field in _WORK_VECTORS
            if getattr(row, field) is not None
        }
        out.append(
            WorkView(
                work_id=str(work.pk),
                user_id=work.user_id,
                year=work.year,
                field=row.openalex_field_id or work.openalex_field_id or "",
                problem=row.problem,
                method=row.method,
                method_neutral=row.method_neutral,
                setting=row.setting,
                reusable=row.reusable,
                vectors=vectors,
            )
        )
    return out


# --- the co-authorship graph (plan CN-07) -----------------------------------
#
# Published co-authorship only: it holds no concept, tier or conversation, so
# nothing here can make a person findable. Who may be *named* on a path is the
# caller's decision (``through``); this module only walks.

_NEIGHBOURS = """
    SELECT b_id AS other FROM knowledge_coauthorship WHERE a_id = w.node
    UNION ALL
    SELECT a_id FROM knowledge_coauthorship WHERE b_id = w.node
"""


def network_of(user_id: int, hops: int = 2) -> set[int]:
    """Everyone within ``hops`` co-authorships of a person, themselves excluded."""
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            WITH RECURSIVE walk(node, depth) AS (
                SELECT %s::int, 0
                UNION
                SELECT nb.other, w.depth + 1
                FROM walk w CROSS JOIN LATERAL ({_NEIGHBOURS}) nb
                WHERE w.depth < %s
            )
            SELECT DISTINCT node FROM walk WHERE node <> %s
            """,
            [user_id, hops, user_id],
        )
        return {row[0] for row in cursor.fetchall()}


def coauthor_distances(user_id: int, max_hops: int = 3) -> dict[int, int]:
    """``{person: hops}`` for everyone within ``max_hops`` of a person."""
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            WITH RECURSIVE walk(node, depth) AS (
                SELECT %s::int, 0
                UNION
                SELECT nb.other, w.depth + 1
                FROM walk w CROSS JOIN LATERAL ({_NEIGHBOURS}) nb
                WHERE w.depth < %s
            )
            SELECT node, MIN(depth) FROM walk WHERE node <> %s GROUP BY node
            """,
            [user_id, max_hops, user_id],
        )
        return dict(cursor.fetchall())


def introduction_paths(
    source_id: int, targets: Iterable[int], through: Iterable[int], max_hops: int = 3
) -> dict[int, list[int]]:
    """The shortest co-authorship path from ``source_id`` to each reachable
    target, as ``[source, …intermediaries…, target]``.

    Every intermediary is in ``through``; a path that would pass anyone else is
    not taken. Among equally short paths the lowest ids win, so an answer is
    the same every time it is asked.
    """
    from django.db import connection

    targets = [int(t) for t in targets]
    if not targets:
        return {}
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            WITH RECURSIVE walk(node, path, depth) AS (
                SELECT %s::int, ARRAY[%s::int], 0
                UNION ALL
                SELECT nb.other, w.path || nb.other, w.depth + 1
                FROM walk w CROSS JOIN LATERAL ({_NEIGHBOURS}) nb
                WHERE w.depth < %s
                  AND NOT nb.other = ANY(w.path)
                  AND (w.depth = 0 OR w.node = ANY(%s::int[]))
            )
            SELECT DISTINCT ON (node) node, path
            FROM walk
            WHERE node = ANY(%s::int[])
            ORDER BY node, depth, path
            """,
            [source_id, source_id, max_hops, [int(t) for t in through], targets],
        )
        return {node: list(path) for node, path in cursor.fetchall()}


# --- harm checks (plan CN-08) --------------------------------------------------


def evidence_texts(users: Iterable) -> dict[int, set[str]]:
    """Everything a person's matches may legitimately quote, casefolded: the
    wording and labels of their active declared and demonstrated edges, and
    the facet sentences of their published works. A shown match whose words
    are not in here came from somewhere the matcher must not read."""
    from collections import defaultdict

    from .models import WorkFacets

    ids = [getattr(u, "pk", u) for u in users]
    out: dict[int, set[str]] = defaultdict(set)
    for user_id, surface, label in (
        Edge.objects.filter(user_id__in=ids, status=EdgeStatus.ACTIVE)
        .filter(_DISCOVERABLE)
        .values_list("user_id", "surface", "concept__label")
    ):
        out[user_id].update(t.casefold() for t in (surface, label) if t)
    for user_id, *texts in WorkFacets.objects.filter(
        author_work__user_id__in=ids, thin=False
    ).values_list(
        "author_work__user_id", "problem", "method", "method_neutral", "reusable"
    ):
        out[user_id].update(t.casefold() for t in texts if t)
    return dict(out)


def privately_held_global_concepts() -> int:
    """How many global concepts are held only through conversation or project
    state — none should be. Also counts a global concept whose declared
    holders have all left it, which is worth a look but not a leak."""
    from django.db.models import Count

    from .models import Scope

    public = Q(edges__tier=Tier.DEMONSTRATED) | Q(
        edges__tier=Tier.DECLARED, edges__project__isnull=True
    )
    active = Q(edges__status=EdgeStatus.ACTIVE)
    return (
        Concept.objects.filter(scope=Scope.GLOBAL, status=Concept.Status.ACTIVE)
        .annotate(
            held=Count("edges", filter=active),
            publicly=Count("edges", filter=active & public),
        )
        .filter(held__gt=0, publicly=0)
        .count()
    )
