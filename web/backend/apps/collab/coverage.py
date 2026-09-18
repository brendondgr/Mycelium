"""Which of a call's slots the reader, or their own lab, already covers.

Deterministic and model-free. For each slot of a call:

* **covered by you** — the reader holds a matching concept: their declared
  profile, what their papers show, or conversation they confirmed. It is their
  own card, shown only to them.
* **covered by your lab** — a lab-mate holds a matching **declared** concept.
  A lab-mate is named on the strength of what their profile states, because
  that is what they control (``team_gap.py``'s rule, the knowledge core's
  ``lab_declared_edges``); their papers and anything Mylo understood from
  conversation never name them here.
* **gap** — neither.

A **role** slot is shown and never matched: no profile can supply "a border
authority as a partner". The candidate people are exactly the ones the rest of
the product already names for a target (``member_fit.scope_members``): a lab's
members, a lab project's lab, a project's own members; a personal reader has no
lab view here.

A slot matches a concept when their cosine is at least
``COLLAB_COVERAGE_COSINE`` or when the words are the same after normalising.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field

from django.conf import settings

from apps.content.member_fit import scope_members
from apps.knowledge.read import (
    EdgeView,
    concept_vectors,
    lab_declared_edges,
    own_edges,
)

from .models import RequirementSlots, SlotFacet

YOU = "you"
LAB = "lab"


@dataclass(frozen=True)
class SlotCoverage:
    text: str
    facet: str
    required: bool
    covered_by: str | None = None  # "you", "lab", or None (a gap)
    people: tuple[str, ...] = ()  # usernames, for a lab
    matched: str = ""  # the holder's own wording that matched

    @property
    def is_role(self) -> bool:
        return self.facet == SlotFacet.ROLE

    @property
    def is_gap(self) -> bool:
        return not self.is_role and self.covered_by is None

    def as_dict(self) -> dict:
        return {
            "text": self.text,
            "facet": self.facet,
            "required": self.required,
            "covered_by": self.covered_by,
            "people": list(self.people),
            "matched": self.matched,
        }


@dataclass
class TeamFit:
    content_id: str
    slots: list[SlotCoverage] = field(default_factory=list)

    @property
    def matchable(self) -> list[SlotCoverage]:
        return [slot for slot in self.slots if not slot.is_role]

    @property
    def covered(self) -> int:
        return sum(1 for slot in self.matchable if slot.covered_by)

    @property
    def gaps(self) -> list[SlotCoverage]:
        return [slot for slot in self.matchable if slot.is_gap]

    @property
    def roles(self) -> list[SlotCoverage]:
        return [slot for slot in self.slots if slot.is_role]

    def as_dict(self) -> dict:
        return {
            "covered": self.covered,
            "total": len(self.matchable),
            "gaps": [slot.text for slot in self.gaps],
            "roles": [slot.text for slot in self.roles],
            "slots": [slot.as_dict() for slot in self.slots],
        }


def _norm(text: str) -> str:
    return " ".join(str(text or "").casefold().replace("-", " ").split())


def _cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def _best(slot: dict, edges: list[EdgeView], vectors: dict[int, list[float]]):
    """The edge that best matches a slot, and whether it clears the bar."""
    floor = settings.COLLAB_COVERAGE_COSINE
    words = _norm(slot["text"])
    best, best_score = None, 0.0
    for edge in edges:
        if words in (_norm(edge.surface), _norm(edge.label)):
            return edge
        vector = vectors.get(edge.concept_id)
        if slot.get("vector") and vector:
            score = _cosine(slot["vector"], vector)
            if score > best_score:
                best, best_score = edge, score
    return best if best is not None and best_score >= floor else None


def _active(edges: list[EdgeView]) -> list[EdgeView]:
    return [edge for edge in edges if edge.status == "active"]


def assess(
    row: RequirementSlots,
    *,
    own: list[EdgeView] = (),
    lab: dict[str, list[EdgeView]] | None = None,
    vectors: dict[int, list[float]] | None = None,
) -> TeamFit:
    """Coverage of one call's slots against the reader's and their lab's edges."""
    lab = lab or {}
    if vectors is None:
        ids = {e.concept_id for e in own} | {
            e.concept_id for edges in lab.values() for e in edges
        }
        vectors = concept_vectors(ids)
    fit = TeamFit(content_id=str(row.content_id))
    for slot in row.slots:
        base = {
            "text": slot["text"],
            "facet": slot["facet"],
            "required": bool(slot.get("required")),
        }
        if slot["facet"] == SlotFacet.ROLE:
            fit.slots.append(SlotCoverage(**base))
            continue
        mine = _best(slot, list(own), vectors)
        if mine is not None:
            fit.slots.append(SlotCoverage(**base, covered_by=YOU, matched=mine.surface))
            continue
        people, matched = [], ""
        for username, edges in lab.items():
            hit = _best(slot, edges, vectors)
            if hit is not None:
                people.append(username)
                matched = matched or hit.surface
        if people:
            fit.slots.append(
                SlotCoverage(
                    **base, covered_by=LAB, people=tuple(people), matched=matched
                )
            )
        else:
            fit.slots.append(SlotCoverage(**base))
    return fit


def _lab_edges(members) -> dict[str, list[EdgeView]]:
    by_user: dict[int, list[EdgeView]] = defaultdict(list)
    for edge in lab_declared_edges(members):
        by_user[edge.user_id].append(edge)
    names = {member.pk: member.get_username() for member in members}
    return {names[pk]: edges for pk, edges in by_user.items() if pk in names}


def _rows(calls) -> list[RequirementSlots]:
    return [
        row
        for row in RequirementSlots.objects.filter(
            content__in=[getattr(c, "pk", c) for c in calls],
            status=RequirementSlots.Status.OK,
        )
    ]


def _assess_all(rows, own, lab) -> dict[str, TeamFit]:
    ids = {e.concept_id for e in own} | {
        e.concept_id for edges in lab.values() for e in edges
    }
    vectors = concept_vectors(ids)
    return {
        str(row.content_id): assess(row, own=own, lab=lab, vectors=vectors)
        for row in rows
    }


def for_user(user, calls) -> dict[str, TeamFit]:
    """A reader's own cards: what they cover; no lab view (a personal target
    names nobody else)."""
    return _assess_all(_rows(calls), _active(own_edges(user)), {})


def for_lab(lab, calls) -> dict[str, TeamFit]:
    """A lab's cards: which members' profiles cover each slot."""
    members = scope_members({"target_lab": lab})
    return _assess_all(_rows(calls), [], _lab_edges(members))


def for_project(project, calls) -> dict[str, TeamFit]:
    """A project's cards: the people who could pick the work up."""
    members = scope_members({"target_project": project})
    return _assess_all(_rows(calls), [], _lab_edges(members))


def for_call(lab, call) -> TeamFit | None:
    """Q3: for this call, which slots the lab covers, by whom, and which are
    gaps. The third of the four cross-entity queries (``docs/goals.md``)."""
    return for_lab(lab, [call]).get(str(getattr(call, "pk", call)))
