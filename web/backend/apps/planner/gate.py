"""The self-evaluation gate: deterministic code that grades the drafted plan.

This is the planner's core safety mechanism (briefing 4 and 8). The drafter
proposes; this gate disposes. It is *fully deterministic* — set membership
against card fields and the live-source view, never a model "does this look
right?" prompt (briefing 4.2) — so it cannot rubber-stamp an unroutable plan.

It checks structural validity, then, against ground truth: card consistency
(briefing 1.1), live targets and existing entities/edges (briefing 4.1),
declared canonical join keys (briefing 1.2), per-sub-question limits within the
card's safety bounds (briefing 3.5), no unnecessary source calls (briefing 3.2),
and non-degeneracy (briefing 5.3). It checks *structure*, not phrasing, so valid
plans are not bounced (briefing 4.3).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .cards import CardRegistry, validate_card_consistency
from .discovery import LiveSourceView
from .schema import Plan, SubQuestion, schema_errors


@dataclass(frozen=True)
class GateResult:
    """The gate's verdict and, if rejected, the specific reasons why."""

    accepted: bool
    reasons: tuple[str, ...] = ()

    def feedback(self) -> str:
        return "; ".join(self.reasons)


def sub_question_errors(
    sq: SubQuestion,
    target_sources: Iterable[str],
    registry: CardRegistry,
    live_view: LiveSourceView,
) -> list[str]:
    """Ground-truth problems with one sub-question (reused by loop degradation)."""

    errors: list[str] = []
    card = registry.get(sq.source)
    if card is None:
        errors.append(f"sub-question '{sq.id}': unknown source '{sq.source}'")
        return errors

    if sq.source not in set(target_sources):
        errors.append(
            f"sub-question '{sq.id}': source '{sq.source}' is not in target_sources"
        )
    if not live_view.is_live(sq.source):
        errors.append(
            f"sub-question '{sq.id}': source '{sq.source}' is not live"
        )

    for entity in sq.entities:
        if not card.has_entity(entity):
            errors.append(
                f"sub-question '{sq.id}': entity '{entity}' does not exist in "
                f"source '{sq.source}'"
            )

    for start, rel, end in sq.edge_patterns:
        if not card.allows_edge(start, rel, end):
            errors.append(
                f"sub-question '{sq.id}': edge ({start})-[{rel}]->({end}) is not an "
                f"allowed pattern in source '{sq.source}'"
            )

    if sq.max_traversal_depth > card.safety.max_traversal_depth:
        errors.append(
            f"sub-question '{sq.id}': max_traversal_depth {sq.max_traversal_depth} "
            f"exceeds card bound {card.safety.max_traversal_depth}"
        )
    if sq.max_result_rows > card.safety.max_result_rows:
        errors.append(
            f"sub-question '{sq.id}': max_result_rows {sq.max_result_rows} exceeds "
            f"card bound {card.safety.max_result_rows}"
        )

    for key in sq.join_keys:
        if card.join_key(key) is None:
            errors.append(
                f"sub-question '{sq.id}': join key '{key}' is not declared on "
                f"source '{sq.source}'"
            )

    return errors


def evaluate_plan(
    plan: Plan, registry: CardRegistry, live_view: LiveSourceView
) -> GateResult:
    """Decide whether a drafted plan may ship. Deterministic; no model judgment."""

    structural = schema_errors(plan)
    if structural:
        # A malformed plan cannot be safely checked against ground truth.
        return GateResult(accepted=False, reasons=tuple(structural))

    reasons: list[str] = []
    sources_used = plan.sources_used()

    for name in plan.target_sources:
        card = registry.get(name)
        if card is None:
            reasons.append(f"target source '{name}' is not a known source")
            continue
        if not live_view.is_live(name):
            reasons.append(f"target source '{name}' is not live")
        else:
            for issue in validate_card_consistency(card):
                reasons.append(f"source '{name}' card is inconsistent: {issue}")
        if name not in sources_used:
            reasons.append(
                f"target source '{name}' is declared but never used "
                f"(unnecessary source call)"
            )

    for sq in plan.sub_questions:
        reasons.extend(
            sub_question_errors(sq, plan.target_sources, registry, live_view)
        )

    # Cross-source joins must rest on a key declared canonical on every joined
    # source (briefing 1.2).
    key_sources: dict[str, set[str]] = {}
    for sq in plan.sub_questions:
        for key in sq.join_keys:
            key_sources.setdefault(key, set()).add(sq.source)
    for key, sources in key_sources.items():
        if len(sources) > 1 and not registry.supports_cross_source_join(key, sources):
            reasons.append(
                f"join key '{key}' is not declared canonical across all of "
                f"{sorted(sources)}"
            )

    # Non-degeneracy and honest partiality (briefing 5.3, 3.3, 3.4).
    if not plan.addresses_something():
        reasons.append("degenerate plan: it addresses no part of the request")
    if plan.unsupported_parts and not plan.partial:
        reasons.append(
            "plan declares unsupported parts but is not marked partial"
        )

    return GateResult(accepted=not reasons, reasons=tuple(reasons))
