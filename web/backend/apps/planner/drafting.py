"""Drafting: turning a request into a candidate plan.

The drafter is the part the briefing assigns to "the LLM" (briefing 0, 8). It
is a seam: :class:`PlanDrafter` is the protocol an LLM-backed drafter would
implement. :class:`HeuristicDrafter` is a deterministic, card-grounded default
that works offline and serves as a test double — it routes only over
introspected card fields (briefing 1.1), records a source-selection rationale
on every sub-question (briefing 3.1), marks down or out-of-scope parts
unsupported instead of fabricating a path (briefing 2.1, 3.3), and only
proposes joins on declared canonical keys (briefing 1.2). Whatever drafter is
used, the deterministic gate decides whether its draft ships.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from .cards import CardRegistry
from .discovery import LiveSourceView
from .schema import Plan, SubQuestion, UnsupportedPart


@dataclass(frozen=True)
class PlanRequest:
    """A natural-language request to be routed into a plan."""

    text: str


@dataclass(frozen=True)
class DraftContext:
    """What the drafter sees: ground truth plus the gate's last feedback."""

    registry: CardRegistry
    live_view: LiveSourceView
    prior_feedback: tuple[str, ...] = ()
    iteration: int = 1


class PlanDrafter(Protocol):
    """Anything that can propose a plan for a request (LLM-backed in production)."""

    def draft(self, request: PlanRequest, context: DraftContext) -> Plan: ...


_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Surface forms that map a request word onto card entities. The values are
# entity names; the drafter keeps only those that actually exist on a card, so
# routing stays grounded in introspected fields rather than this table.
DEFAULT_SYNONYMS: dict[str, frozenset[str]] = {
    "paper": frozenset({"Paper"}),
    "papers": frozenset({"Paper"}),
    "publication": frozenset({"Paper"}),
    "publications": frozenset({"Paper"}),
    "person": frozenset({"Person"}),
    "people": frozenset({"Person"}),
    "member": frozenset({"Person"}),
    "members": frozenset({"Person"}),
    "researcher": frozenset({"Person"}),
    "researchers": frozenset({"Person"}),
    "author": frozenset({"Person", "AUTHORED_BY"}),
    "authors": frozenset({"Person", "AUTHORED_BY"}),
    "wrote": frozenset({"AUTHORED_BY"}),
    "authored": frozenset({"AUTHORED_BY"}),
    "student": frozenset({"Person"}),
    "students": frozenset({"Person"}),
    "project": frozenset({"Project"}),
    "projects": frozenset({"Project"}),
    "work": frozenset({"WORKS_ON"}),
    "works": frozenset({"WORKS_ON"}),
    "working": frozenset({"WORKS_ON"}),
    "lab": frozenset({"Lab"}),
    "labs": frozenset({"Lab"}),
    "topic": frozenset({"Topic"}),
    "topics": frozenset({"Topic"}),
    "area": frozenset({"ResearchArea"}),
    "areas": frozenset({"ResearchArea"}),
    "interested": frozenset({"INTERESTED_IN"}),
    "interests": frozenset({"INTERESTED_IN"}),
    "claim": frozenset({"Claim"}),
    "claims": frozenset({"Claim"}),
    "finding": frozenset({"Finding"}),
    "findings": frozenset({"Finding"}),
    "result": frozenset({"Finding"}),
    "results": frozenset({"Finding"}),
    "evidence": frozenset({"Finding", "SUPPORTS"}),
    "support": frozenset({"SUPPORTS"}),
    "supports": frozenset({"SUPPORTS"}),
    "supported": frozenset({"SUPPORTS"}),
    "contradict": frozenset({"CONTRADICTS"}),
    "contradicts": frozenset({"CONTRADICTS"}),
    "contradicted": frozenset({"CONTRADICTS"}),
    "conflicting": frozenset({"CONTRADICTS"}),
    "method": frozenset({"Method"}),
    "methods": frozenset({"Method"}),
    "dataset": frozenset({"Dataset"}),
    "datasets": frozenset({"Dataset"}),
    "grant": frozenset({"Grant"}),
    "grants": frozenset({"Grant"}),
    "funding": frozenset({"Grant"}),
    "fellowship": frozenset({"Fellowship"}),
    "fellowships": frozenset({"Fellowship"}),
    "agency": frozenset({"Agency"}),
    "agencies": frozenset({"Agency"}),
    "deadline": frozenset({"Deadline"}),
    "deadlines": frozenset({"Deadline"}),
    "eligibility": frozenset({"EligibilityRule"}),
    "eligible": frozenset({"EligibilityRule"}),
}

_AMBIGUOUS_REFERENCES = {"our", "their", "these", "those", "its"}


def _tokenize(text: str) -> frozenset[str]:
    return frozenset(_TOKEN_RE.findall(text.lower()))


class HeuristicDrafter:
    """Deterministic, card-grounded drafter. Default drafter and test double."""

    def __init__(self, synonyms: Mapping[str, frozenset[str]] | None = None):
        self._synonyms = dict(DEFAULT_SYNONYMS)
        if synonyms:
            self._synonyms.update(synonyms)

    # -- entity matching -------------------------------------------------------

    def _resolved_entities(self, tokens: frozenset[str]) -> frozenset[str]:
        resolved: set[str] = set()
        for token in tokens:
            resolved |= self._synonyms.get(token, frozenset())
        return frozenset(resolved)

    def _match_entities(self, card, tokens, resolved) -> frozenset[str]:
        matched: set[str] = set()
        for label in card.node_labels:
            if label.lower() in tokens or label in resolved:
                matched.add(label)
        for rel in card.relationship_types:
            if rel in resolved:  # relationships match only via synonyms
                matched.add(rel)
        return frozenset(matched)

    def _excluded_sources(self, feedback: tuple[str, ...], registry) -> set[str]:
        """Sources the last gate run flagged unusable, to drop on revise."""

        excluded: set[str] = set()
        flagged = ("is not live", "card is inconsistent", "not a known source")
        for reason in feedback:
            if any(flag in reason for flag in flagged):
                for name in registry.names():
                    if f"'{name}'" in reason:
                        excluded.add(name)
        return excluded

    # -- drafting --------------------------------------------------------------

    def draft(self, request: PlanRequest, context: DraftContext) -> Plan:
        registry = context.registry
        live = context.live_view
        tokens = _tokenize(request.text)
        resolved = self._resolved_entities(tokens)
        excluded = self._excluded_sources(context.prior_feedback, registry)

        matched_live: dict[str, frozenset[str]] = {}
        matched_dead: dict[str, frozenset[str]] = {}
        for card in registry:
            entities = self._match_entities(card, tokens, resolved)
            if not entities:
                continue
            if live.is_live(card.name) and card.name not in excluded:
                matched_live[card.name] = entities
            else:
                matched_dead[card.name] = entities

        selected = sorted(matched_live)
        shared = self._shared_join_keys(selected, registry)

        sub_questions = tuple(
            self._build_sub_question(
                index=index,
                source=source,
                entities=matched_live[source],
                join_keys=tuple(sorted(shared.get(source, set()))),
                registry=registry,
                request=request,
            )
            for index, source in enumerate(selected, start=1)
        )

        unsupported = self._unsupported_parts(matched_dead, excluded, request)
        if not sub_questions and not unsupported:
            unsupported = (
                UnsupportedPart(
                    description=request.text,
                    reason="no live source covers this request",
                ),
            )

        assumptions = self._assumptions(tokens, shared)

        return Plan(
            request=request.text,
            target_sources=tuple(selected),
            sub_questions=sub_questions,
            unsupported_parts=unsupported,
            assumptions=assumptions,
            partial=bool(unsupported),
        )

    def _shared_join_keys(
        self, selected: list[str], registry
    ) -> dict[str, set[str]]:
        shared: dict[str, set[str]] = {source: set() for source in selected}
        if len(selected) < 2:
            return shared
        all_keys: set[str] = set()
        for source in selected:
            all_keys |= registry.require(source).join_key_names()
        for key in all_keys:
            users = [
                source
                for source in selected
                if registry.require(source).join_key(key) is not None
            ]
            if len(users) > 1:
                for source in users:
                    shared[source].add(key)
        return shared

    def _build_sub_question(
        self, *, index, source, entities, join_keys, registry, request
    ) -> SubQuestion:
        card = registry.require(source)
        labelled = ", ".join(sorted(entities))
        return SubQuestion(
            id=f"q{index}",
            text=f"In the {card.title}, address: {request.text}",
            source=source,
            entities=tuple(sorted(entities)),
            rationale=(
                f"{card.title} holds {labelled}, which the request asks about."
            ),
            max_traversal_depth=card.safety.max_traversal_depth,
            max_result_rows=card.safety.max_result_rows,
            join_keys=join_keys,
        )

    def _unsupported_parts(
        self, matched_dead, excluded, request
    ) -> tuple[UnsupportedPart, ...]:
        parts: list[UnsupportedPart] = []
        for source, entities in sorted(matched_dead.items()):
            if source in excluded:
                reason = (
                    f"source '{source}' was rejected by the self-eval gate and "
                    f"cannot be used"
                )
            else:
                reason = f"source '{source}' that holds it is not live"
            parts.append(
                UnsupportedPart(
                    description=(
                        f"the part of the request about {sorted(entities)}"
                    ),
                    reason=reason,
                )
            )
        return tuple(parts)

    def _assumptions(self, tokens, shared) -> tuple[str, ...]:
        assumptions: list[str] = []
        joined_keys = sorted({key for keys in shared.values() for key in keys})
        if joined_keys:
            assumptions.append(
                "Sources are joined on their declared canonical keys: "
                + ", ".join(joined_keys)
                + "."
            )
        if tokens & _AMBIGUOUS_REFERENCES:
            assumptions.append(
                "Ambiguous references such as 'our' or 'these' are read as the "
                "requesting lab's own entities."
            )
        return tuple(assumptions)


class StaticDrafter:
    """Returns a fixed sequence of pre-built drafts; for loop tests."""

    def __init__(self, drafts):
        self._drafts = list(drafts)
        self.contexts: list[DraftContext] = []

    def draft(self, request: PlanRequest, context: DraftContext) -> Plan:
        self.contexts.append(context)
        index = min(len(self.contexts) - 1, len(self._drafts) - 1)
        return self._drafts[index]
