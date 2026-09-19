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
from .models import Concept, Edge, EdgeStatus, Facet, Relation, Scope, Tier
from .projection import Projected, project_declared
from .read import EdgeView

__all__ = [
    "Projected",
    "delete_conversational",
    "drop_evidence",
    "due_for_review",
    "edit_conversational",
    "keep",
    "link_conversation",
    "unreinforced_since",
    "queue_work_facets",
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
    concept_id: int | None = None,
    qualifier: str = "",
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
    if concept_id is not None:
        # The caller already linked this wording (the ambient ledger links
        # every topic when it is read); following a merge keeps it current.
        concept = Concept.objects.filter(pk=concept_id).first()
        while concept is not None and concept.merged_into_id:
            concept = Concept.objects.filter(pk=concept.merged_into_id).first()
    else:
        concept = linker.link_many(
            [
                LinkRequest(
                    surface=surface,
                    facet=facet,
                    default_facet=default_facet,
                    scope=Scope.PERSONAL,
                    owner=user,
                )
            ]
        )[0].concept
    if concept is None:
        return None
    now = timezone.now()
    with transaction.atomic():
        edge, created = Edge.objects.select_for_update().get_or_create(
            user=user,
            relation=relation,
            concept=concept,
            tier=Tier.CONVERSATIONAL,
            defaults={
                "status": EdgeStatus.PENDING,
                "surface": linker.clean(surface),
                "weight": weight,
                "half_life_days": half_life_days,
                "evidence": list(evidence),
                "first_seen": now,
                "last_reinforced": now,
                "qualifier": qualifier,
            },
        )
        if not created:
            merged = list(edge.evidence or [])
            merged += [item for item in evidence if item not in merged]
            fields = ["evidence", "updated_at"]
            if merged != list(edge.evidence or []):
                # Reinforced only by new evidence; rerunning the night is not
                # the person coming back to it.
                edge.last_reinforced = now
                fields.append("last_reinforced")
            edge.evidence = merged
            edge.save(update_fields=fields)
    edge.concept = concept
    return EdgeView.of(edge)


def link_conversation(requests: list[tuple[str, str, object]]) -> list[int | None]:
    """Which concept each topic from conversation names, as concept ids.

    ``requests`` are ``(surface, facet, owner)``: ``owner`` is the person the
    topic is about, or the lab whose project it concerns. A concept minted here
    is born in that owner's scope and never in the shared vocabulary — only a
    shared source can put a word there (:mod:`.linker`). ``area`` means "no
    particular facet": it matches a concept of any facet and mints as an area,
    the way a person's own keyword does. ``None`` in the result means the topic
    could not be linked yet (the embedder is down) or is not a term.
    """
    from apps.accounts.models import Lab

    batch = []
    for surface, facet, owner in requests:
        scope = Scope.LAB if isinstance(owner, Lab) else Scope.PERSONAL
        specific = (
            facet if facet in (Facet.PROBLEM, Facet.METHOD, Facet.SETTING) else None
        )
        batch.append(
            LinkRequest(
                surface=surface,
                facet=specific,
                default_facet=Facet.AREA,
                scope=scope,
                owner=owner,
            )
        )
    if not batch:
        return []
    return [
        result.concept.pk if result.concept is not None else None
        for result in linker.link_many(batch)
    ]


def _set_status(user, concept_id: int, relation: str, status: str) -> bool:
    return bool(
        Edge.objects.filter(
            user=user,
            concept_id=concept_id,
            relation=relation,
            tier=Tier.CONVERSATIONAL,
        ).update(status=status, updated_at=timezone.now())
    )


def confirm(user, concept_id: int, relation: str, *, review_on=None) -> bool:
    """The person said yes: the edge may now shape their own recommendations.

    ``review_on`` makes it an exploration with a date to ask "keep this?".
    """
    updated = _set_status(user, concept_id, relation, EdgeStatus.ACTIVE)
    if updated and review_on is not None:
        Edge.objects.filter(
            user=user,
            concept_id=concept_id,
            relation=relation,
            tier=Tier.CONVERSATIONAL,
        ).update(review_on=review_on)
    return updated


def keep(user, concept_id: int, relation: str, *, review_on) -> bool:
    """An exploration kept at its review: active again, reviewed later."""
    return bool(
        Edge.objects.filter(
            user=user,
            concept_id=concept_id,
            relation=relation,
            tier=Tier.CONVERSATIONAL,
        ).update(
            status=EdgeStatus.ACTIVE,
            review_on=review_on,
            last_reinforced=timezone.now(),
            updated_at=timezone.now(),
        )
    )


def edit_conversational(user, concept_id: int, relation: str, *, surface: str) -> bool:
    """The person reworded what Mylo understood; it is their word now."""
    return bool(
        Edge.objects.filter(
            user=user,
            concept_id=concept_id,
            relation=relation,
            tier=Tier.CONVERSATIONAL,
        ).update(
            surface=linker.clean(surface),
            edited_by_person=True,
            updated_at=timezone.now(),
        )
    )


def delete_conversational(user, concept_id: int, relation: str) -> int:
    """The person deleted one thing Mylo understood. Gone, not rejected."""
    deleted, _ = Edge.objects.filter(
        user=user,
        concept_id=concept_id,
        relation=relation,
        tier=Tier.CONVERSATIONAL,
    ).delete()
    return deleted


def unreinforced_since(cutoff, *, qualifier: str) -> list[EdgeView]:
    """Active conversational edges of one kind not reinforced since ``cutoff``
    — what the nightly fade reads. People's own edges only; no other reader."""
    return [
        EdgeView.of(edge)
        for edge in Edge.objects.filter(
            tier=Tier.CONVERSATIONAL,
            status=EdgeStatus.ACTIVE,
            qualifier=qualifier,
            last_reinforced__lt=cutoff,
        ).select_related("concept")
    ]


def due_for_review(today) -> list[tuple[EdgeView, object]]:
    """Confirmed explorations whose review date has come: ``(edge, person)``.

    Plan 06 asks each person "keep this?" about their own; no other reader.
    """
    return [
        (EdgeView.of(edge), edge.user)
        for edge in Edge.objects.filter(
            tier=Tier.CONVERSATIONAL,
            status=EdgeStatus.ACTIVE,
            review_on__isnull=False,
            review_on__lte=today,
        ).select_related("concept", "user")
    ]


def drop_evidence(user, items: Iterable) -> int:
    """Take retracted evidence out of this person's conversational edges.

    A pending edge left with no evidence at all is deleted — nothing supports
    asking any more. A confirmed one stays (the person said yes; the yes is the
    evidence now) with the retracted pointers removed.
    """
    gone = set(items)
    touched = 0
    for edge in Edge.objects.filter(user=user, tier=Tier.CONVERSATIONAL):
        kept = [item for item in (edge.evidence or []) if item not in gone]
        if kept == list(edge.evidence or []):
            continue
        touched += 1
        if not kept and edge.status == EdgeStatus.PENDING:
            edge.delete()
            continue
        edge.evidence = kept
        edge.save(update_fields=["evidence", "updated_at"])
    return touched


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


def queue_work_facets(user_id) -> None:
    """Read a person's newly imported papers soon, without making them wait.

    Called by the author import once its works are stored. Queued after the
    import's transaction commits; a broker outage costs a night's delay (the
    nightly pass reads whatever is still unread), never the import.
    """
    from django.conf import settings

    if not settings.KNOWLEDGE_FACET_ON_IMPORT:
        return

    def _send() -> None:
        from .tasks import facet_user_works

        try:
            facet_user_works.delay(str(user_id))
        except Exception:  # noqa: BLE001 - the nightly pass catches up
            import logging

            logging.getLogger(__name__).warning(
                "could not queue reading %s's papers", user_id
            )

    transaction.on_commit(_send)
