"""Merging two concepts into one, promoting a private one, and undoing a merge.

Three operations, all logged in :class:`~apps.knowledge.models.ConceptMerge`:

* **merge** — staff decide two concepts are one idea. Every edge and alias of
  the source moves to the target; an edge that would duplicate one the target
  already has collapses into it. Kept exactly enough to reverse.
* **promote** — a concept born in one lab's or one person's scope turns out to
  name something a shared source also names. It becomes global, and its label
  is replaced by the shared source's wording, so the private phrasing that
  minted it stops existing. Nothing about the private source is logged beyond
  row ids. Not reversible, on purpose: reversing would need the private wording.
* **unmerge** — reverse a staff merge.

A merge never crosses owners: two labs' private concepts are never merged into
each other, and a shared concept is never merged into a private one, because
either would point one owner's edges at another owner's words.
"""

from __future__ import annotations

from django.db import transaction

from .models import (
    SUBJECT_FIELDS,
    Concept,
    ConceptAlias,
    ConceptMerge,
    Edge,
    Scope,
)


class MergeRefused(ValueError):
    """The requested merge would break a rule; nothing was changed."""


def _same_owner(a: Concept, b: Concept) -> bool:
    return (a.scope, a.scope_user_id, a.scope_lab_id, a.scope_department_id) == (
        b.scope,
        b.scope_user_id,
        b.scope_lab_id,
        b.scope_department_id,
    )


def _check(source: Concept, target: Concept) -> None:
    if source.pk == target.pk:
        raise MergeRefused("a concept cannot be merged into itself")
    if Concept.Status.ACTIVE != source.status or Concept.Status.ACTIVE != target.status:
        raise MergeRefused("only active concepts can be merged")
    if source.facet != target.facet:
        raise MergeRefused(
            f"a {source.facet} cannot be merged into a {target.facet}; "
            "facets are part of what a concept means"
        )
    if target.scope == Scope.GLOBAL:
        return  # anything may join the shared vocabulary
    if source.scope == Scope.GLOBAL:
        raise MergeRefused("a shared concept cannot be merged into a private one")
    if not _same_owner(source, target):
        raise MergeRefused("private concepts of two different owners never merge")


def _subject(edge: Edge) -> dict:
    return {
        f"{field}_id": getattr(edge, f"{field}_id")
        for field in SUBJECT_FIELDS
        if getattr(edge, f"{field}_id") is not None
    }


def _serialise(edge: Edge) -> dict:
    return {
        "id": edge.pk,
        "subject": _subject(edge),
        "relation": edge.relation,
        "tier": edge.tier,
        "status": edge.status,
        "surface": edge.surface,
        "weight": edge.weight,
        "first_seen": edge.first_seen.isoformat(),
        "last_reinforced": edge.last_reinforced.isoformat(),
        "half_life_days": edge.half_life_days,
        "evidence": edge.evidence,
    }


def _move_edges(source: Concept, target: Concept, *, keep_collapsed: bool):
    """Re-point the source's edges at the target, collapsing duplicates."""
    moved: list[int] = []
    collapsed: list[dict] = []
    for edge in Edge.objects.filter(concept=source).select_for_update():
        twin = Edge.objects.filter(
            concept=target, relation=edge.relation, tier=edge.tier, **_subject(edge)
        ).first()
        if twin is None:
            edge.concept = target
            edge.save(update_fields=["concept", "updated_at"])
            moved.append(edge.pk)
            continue
        evidence = list(twin.evidence or [])
        for item in edge.evidence or []:
            if item not in evidence:
                evidence.append(item)
        twin.evidence = evidence
        twin.weight = max(twin.weight, edge.weight)
        twin.first_seen = min(twin.first_seen, edge.first_seen)
        twin.last_reinforced = max(twin.last_reinforced, edge.last_reinforced)
        twin.save(
            update_fields=[
                "evidence",
                "weight",
                "first_seen",
                "last_reinforced",
                "updated_at",
            ]
        )
        if keep_collapsed:
            collapsed.append(_serialise(edge))
        edge.delete()
    return moved, collapsed


@transaction.atomic
def merge(
    source: Concept,
    target: Concept,
    *,
    actor=None,
    kind: str = ConceptMerge.Kind.MERGE,
) -> ConceptMerge:
    """Fold ``source`` into ``target``. Staff merges keep the source row."""
    source = Concept.objects.select_for_update().get(pk=source.pk)
    target = Concept.objects.select_for_update().get(pk=target.pk)
    _check(source, target)
    promoting = kind == ConceptMerge.Kind.PROMOTE
    moved, collapsed = _move_edges(source, target, keep_collapsed=not promoting)
    aliases = list(
        ConceptAlias.objects.filter(concept=source).values_list("pk", flat=True)
    )
    ConceptAlias.objects.filter(pk__in=aliases).update(concept=target)
    record = ConceptMerge.objects.create(
        kind=kind,
        source=None if promoting else source,
        target=target,
        moved_edges=moved,
        collapsed_edges=collapsed,
        moved_aliases=aliases,
        actor=actor,
    )
    if promoting:
        # The private concept's wording goes with it; its edges and aliases now
        # hang off the shared concept.
        source.delete()
    else:
        source.status = Concept.Status.MERGED
        source.merged_into = target
        source.save(update_fields=["status", "merged_into", "updated_at"])
    return record


@transaction.atomic
def promote(concept: Concept, *, label: str, embedding=None) -> Concept:
    """Make a private concept shared, under the shared source's wording."""
    concept = Concept.objects.select_for_update().get(pk=concept.pk)
    if concept.scope == Scope.GLOBAL:
        return concept
    concept.scope = Scope.GLOBAL
    concept.scope_user = None
    concept.scope_lab = None
    concept.scope_department = None
    concept.label = label
    fields = [
        "scope",
        "scope_user",
        "scope_lab",
        "scope_department",
        "label",
        "updated_at",
    ]
    if embedding is not None:
        concept.embedding = embedding
        fields.append("embedding")
    concept.save(update_fields=fields)
    ConceptMerge.objects.create(kind=ConceptMerge.Kind.PROMOTE, target=concept)
    return concept


@transaction.atomic
def unmerge(record: ConceptMerge, *, actor=None) -> ConceptMerge:
    """Reverse a staff merge: moved edges, collapsed edges, and aliases.

    Evidence ids that were copied into a surviving twin edge stay there too.
    They are ids, not text, and for declared edges the next projection
    reconciles them against the source of truth anyway.
    """
    record = ConceptMerge.objects.select_for_update().get(pk=record.pk)
    if record.kind != ConceptMerge.Kind.MERGE:
        raise MergeRefused("only a staff merge can be reversed")
    if record.reversed_by_id is not None:
        raise MergeRefused("this merge has already been reversed")
    if record.source is None or record.target is None:
        raise MergeRefused("a concept in this merge no longer exists")
    source, target = record.source, record.target
    if source.status != Concept.Status.MERGED or source.merged_into_id != target.pk:
        raise MergeRefused("the source has changed since it was merged")

    Edge.objects.filter(pk__in=record.moved_edges, concept=target).update(
        concept=source
    )
    for row in record.collapsed_edges:
        Edge.objects.get_or_create(
            concept=source,
            relation=row["relation"],
            tier=row["tier"],
            **row["subject"],
            defaults={
                "status": row["status"],
                "surface": row["surface"],
                "weight": row["weight"],
                "first_seen": row["first_seen"],
                "last_reinforced": row["last_reinforced"],
                "half_life_days": row["half_life_days"],
                "evidence": row["evidence"],
            },
        )
    ConceptAlias.objects.filter(pk__in=record.moved_aliases).update(concept=source)
    source.status = Concept.Status.ACTIVE
    source.merged_into = None
    source.save(update_fields=["status", "merged_into", "updated_at"])
    reversal = ConceptMerge.objects.create(
        kind=ConceptMerge.Kind.UNMERGE, source=source, target=target, actor=actor
    )
    record.reversed_by = reversal
    record.save(update_fields=["reversed_by"])
    return reversal
