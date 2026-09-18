"""The one write door into the knowledge core from outside it.

Two kinds of writer use it. The projection keeps declared edges in step with
the profiles and projects they mirror. The ambient profile (Plans 04–06)
records what Mylo understood from conversation, as ``conversational`` edges
that stay ``pending`` until the person answers — and that nothing outside the
person's own view can ever read (:mod:`.read`).

Conversation is private to the person it is about: a concept minted from it is
born in their personal scope, and only ever reaches the shared vocabulary if a
shared source names the same thing (:mod:`.linker`).
"""

from __future__ import annotations

from collections.abc import Iterable

from django.db import transaction
from django.utils import timezone

from . import linker
from .linker import LinkRequest
from .models import Edge, EdgeStatus, Facet, Relation, Scope, Tier
from .projection import Projected, project_declared
from .read import EdgeView

__all__ = [
    "Projected",
    "confirm",
    "fade",
    "forget_conversational",
    "project_declared",
    "record_conversational",
    "reject",
]


def record_conversational(
    user,
    *,
    surface: str,
    relation: str,
    evidence: Iterable = (),
    facet: str | None = None,
    default_facet: str = Facet.AREA,
    weight: float = 1.0,
    half_life_days: float | None = None,
) -> EdgeView | None:
    """Record, or reinforce, something Mylo understood about this person.

    A new edge is ``pending``: it changes nothing until the person confirms it.
    An existing one is reinforced — its evidence grows and its clock restarts —
    and keeps its status, so a topic the person said no to stays said no to.
    Returns ``None`` when the wording could not be linked yet (the embedder is
    down, or it is not a term); the caller retries on its next run.
    """
    if relation not in Relation.values:
        raise ValueError(f"unknown relation {relation!r}")
    result = linker.link_many(
        [
            LinkRequest(
                surface=surface,
                facet=facet,
                default_facet=default_facet,
                scope=Scope.PERSONAL,
                owner=user,
            )
        ]
    )[0]
    if result.concept is None:
        return None
    now = timezone.now()
    with transaction.atomic():
        edge, created = Edge.objects.select_for_update().get_or_create(
            user=user,
            relation=relation,
            concept=result.concept,
            tier=Tier.CONVERSATIONAL,
            defaults={
                "status": EdgeStatus.PENDING,
                "surface": linker.clean(surface),
                "weight": weight,
                "half_life_days": half_life_days,
                "evidence": list(evidence),
                "first_seen": now,
                "last_reinforced": now,
            },
        )
        if not created:
            merged = list(edge.evidence or [])
            merged += [item for item in evidence if item not in merged]
            edge.evidence = merged
            edge.last_reinforced = now
            edge.save(update_fields=["evidence", "last_reinforced", "updated_at"])
    edge.concept = result.concept
    return EdgeView.of(edge)


def _set_status(user, concept_id: int, relation: str, status: str) -> bool:
    return bool(
        Edge.objects.filter(
            user=user,
            concept_id=concept_id,
            relation=relation,
            tier=Tier.CONVERSATIONAL,
        ).update(status=status, updated_at=timezone.now())
    )


def confirm(user, concept_id: int, relation: str) -> bool:
    """The person said yes: the edge may now shape their own recommendations."""
    return _set_status(user, concept_id, relation, EdgeStatus.ACTIVE)


def reject(user, concept_id: int, relation: str) -> bool:
    """The person said no. Kept, so the same thing is not raised again."""
    return _set_status(user, concept_id, relation, EdgeStatus.REJECTED)


def fade(user, concept_id: int, relation: str) -> bool:
    """An exploration ran its course; it stops ranking but stays visible."""
    return _set_status(user, concept_id, relation, EdgeStatus.FADED)


def forget_conversational(user) -> int:
    """Delete everything conversation taught the graph about this person.

    Called by the ambient opt-out and "forget me" paths. Declared edges are the
    person's own profile and stay; they leave when the profile says so.
    """
    deleted, _ = Edge.objects.filter(user=user, tier=Tier.CONVERSATIONAL).delete()
    return deleted
