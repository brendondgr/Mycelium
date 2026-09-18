"""Demonstrated edges: what a person's papers show, as edges.

Two levels, because retrieval and display want different things:

* **Per work.** Each non-thin work's terms are linked in the shared vocabulary
  (a published work is public) and become ``demonstrated`` edges on that work:
  ``works_on`` for its problem, ``uses_method`` for its methods,
  ``works_in_setting`` for its data, ``offers`` for what it makes reusable.
  Collaboration retrieval ranks works and credits their authors (design §5.2).
* **Per person.** A roll-up onto the person: one ``demonstrated`` edge per
  concept their works reach, weighted by how many works reach it, dated by the
  earliest and latest year. What the person sees ("your papers show this") and
  what their collaboration preview lists. Never averaged into one vector.

A thin work produces no edge at all. Demonstrated edges never shape the
person's own ranking (:func:`apps.knowledge.read.ranking_edges`).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from django.db import transaction
from django.db.models import Q

from .linker import clean
from .models import Concept, Edge, EdgeStatus, Facet, Relation, Scope, Tier
from .projection import Projected, _apply, _Want

#: Which relation and facet each extracted facet becomes.
_FACET_EDGES = {
    "problem": (Relation.WORKS_ON, Facet.PROBLEM),
    "method": (Relation.USES_METHOD, Facet.METHOD),
    "setting": (Relation.WORKS_IN_SETTING, Facet.SETTING),
    # What could be reused is sometimes a method and sometimes a dataset;
    # nobody said which, so it links to either and mints as unspecified.
    "reusable": (Relation.OFFERS, None),
}


def _wants(facets) -> list[_Want]:
    if facets is None or facets.thin:
        return []
    wants = []
    for name, (relation, facet) in _FACET_EDGES.items():
        for term in (facets.terms or {}).get(name, []):
            wants.append(_Want(relation, term, f"facets.{name}_terms", facet=facet))
    return wants


def record_work(work) -> Projected:
    """Make one work's demonstrated edges match its facets."""
    facets = getattr(work, "facets", None)
    result = _apply(
        {"author_work": work},
        _wants(facets),
        Scope.GLOBAL,
        None,
        tier=Tier.DEMONSTRATED,
    )
    if facets is not None and facets.method_neutral:
        _name_the_operation(work, facets.method_neutral)
    return result


def _name_the_operation(work, neutral: str) -> None:
    """Give the work's first method concept its field-neutral phrasing.

    Stored on the concept, not as an alias of it. An alias would send every
    other method with the same abstraction ("estimating a hidden state from
    noisy observations" is both a Kalman filter and data assimilation) to this
    one concept — exactly the over-merging the neutral phrase must not cause.
    The first phrasing wins; a later work does not overwrite it.
    """
    first = (
        Edge.objects.filter(
            author_work=work,
            tier=Tier.DEMONSTRATED,
            relation=Relation.USES_METHOD,
            concept__neutral_label="",
            concept__scope=Scope.GLOBAL,
        )
        .order_by("pk")
        .values_list("concept_id", flat=True)
        .first()
    )
    if first is not None:
        Concept.objects.filter(pk=first, neutral_label="").update(
            neutral_label=clean(neutral)
        )


def _year_start(year: int | None, fallback: datetime) -> datetime:
    return datetime(year, 1, 1, tzinfo=UTC) if year else fallback


@transaction.atomic
def rollup(user) -> Projected:
    """Rebuild the person's demonstrated edges from their works' edges."""
    result = Projected(subjects=1)
    groups: dict[tuple[str, int], dict] = defaultdict(
        lambda: {"works": [], "years": [], "surface": ""}
    )
    rows = (
        Edge.objects.filter(
            author_work__user=user,
            tier=Tier.DEMONSTRATED,
            status=EdgeStatus.ACTIVE,
        )
        .select_related("author_work")
        .order_by("author_work__year", "pk")
    )
    for edge in rows:
        group = groups[(edge.relation, edge.concept_id)]
        work = edge.author_work
        if f"work:{work.pk}" not in group["works"]:
            group["works"].append(f"work:{work.pk}")
            if work.year:
                group["years"].append(work.year)
        group["surface"] = group["surface"] or edge.surface

    existing = {
        (edge.relation, edge.concept_id): edge
        for edge in Edge.objects.select_for_update().filter(
            user=user, tier=Tier.DEMONSTRATED
        )
    }
    now = datetime.now(UTC)
    for key, group in groups.items():
        fields = {
            "surface": group["surface"],
            "weight": float(len(group["works"])),
            "evidence": sorted(group["works"]),
            "first_seen": _year_start(min(group["years"], default=None), now),
            "last_reinforced": _year_start(max(group["years"], default=None), now),
        }
        edge = existing.get(key)
        if edge is None:
            Edge.objects.create(
                user=user,
                relation=key[0],
                concept_id=key[1],
                tier=Tier.DEMONSTRATED,
                **fields,
            )
            result.created += 1
        elif any(getattr(edge, name) != value for name, value in fields.items()):
            for name, value in fields.items():
                setattr(edge, name, value)
            edge.save(update_fields=[*fields, "updated_at"])
            result.updated += 1
    stale = [edge.pk for key, edge in existing.items() if key not in groups]
    if stale:
        result.deleted = Edge.objects.filter(pk__in=stale).delete()[0]
    return result


def set_fields(concept_ids) -> int:
    """Give each concept the OpenAlex field its works agree on, or none.

    A concept every one of whose works sits in Computer Science is a Computer
    Science concept for measuring distance; one reached from two fields is not
    any single field's, and says so by having none. Used for distance only
    (design §5.6), never as a label.
    """
    fields: dict[int, set[str]] = defaultdict(set)
    for concept_id, field_id in Edge.objects.filter(
        concept_id__in=list(concept_ids),
        tier=Tier.DEMONSTRATED,
        author_work__isnull=False,
    ).values_list("concept_id", "author_work__facets__openalex_field_id"):
        if field_id:
            fields[concept_id].add(field_id)
    changed = 0
    for concept_id in set(concept_ids):
        seen = fields.get(concept_id, set())
        value = next(iter(seen)) if len(seen) == 1 else ""
        changed += Concept.objects.filter(
            ~Q(openalex_field_id=value), pk=concept_id
        ).update(openalex_field_id=value)
    return changed


def record_person(user) -> Projected:
    """Every work of one person, then their roll-up, then the field ruler."""
    total = Projected()
    for work in user.author_works.select_related("facets").order_by("pk"):
        total.add(record_work(work))
    total.add(rollup(user))
    set_fields(
        Edge.objects.filter(author_work__user=user, tier=Tier.DEMONSTRATED).values_list(
            "concept_id", flat=True
        )
    )
    return total
