"""The self-evaluating ReAct loop: draft, grade, revise, or degrade.

Each iteration drafts a plan and runs it through the deterministic gate. An
accepted plan ships. A rejected plan's specific reasons are fed into the next
iteration so the revise step is informed, not a blind re-roll (briefing 5.2).
The loop is bounded by a max-iterations cap (briefing 5.1); on exhaustion it
degrades to an honest partial plan — keeping the sub-questions that pass and
recording the rest as unsupported — and never fabricates a plan to escape the
gate. The emitted plan always passes the gate; that is the loop's invariant.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .cards import CardRegistry
from .discovery import LiveSourceView
from .drafting import DraftContext, PlanDrafter, PlanRequest
from .gate import GateResult, evaluate_plan, sub_question_errors
from .schema import Plan, PlanTraceEntry, UnsupportedPart


@dataclass(frozen=True)
class LoopConfig:
    """Bounds for the ReAct loop."""

    max_iterations: int = 3

    def __post_init__(self) -> None:
        if self.max_iterations < 1:
            raise ValueError("max_iterations must be >= 1")


@dataclass(frozen=True)
class PlanningOutcome:
    """What the loop produced and how it got there."""

    plan: Plan
    converged: bool
    iterations: int


def _thought(draft: Plan, context: DraftContext) -> str:
    return (
        f"iteration {context.iteration}: routed to "
        f"{sorted(draft.sources_used())}; {len(draft.sub_questions)} "
        f"sub-question(s), {len(draft.unsupported_parts)} unsupported part(s)"
    )


def degrade_plan(
    draft: Plan | None,
    request: PlanRequest,
    registry: CardRegistry,
    live_view: LiveSourceView,
) -> Plan:
    """Coerce a non-converged draft into an honest, gate-valid partial plan.

    Keeps only sub-questions that pass the gate's ground-truth checks; every
    dropped sub-question becomes an unsupported part. If the result still does
    not pass the gate (or there is no usable draft), falls back to a plan that
    plainly says the request could not be resolved. Never fabricates.
    """

    if draft is not None:
        survivors = []
        unsupported = list(draft.unsupported_parts)
        seen_ids: set[str] = set()
        for sq in draft.sub_questions:
            errors = sub_question_errors(
                sq, draft.target_sources, registry, live_view
            )
            if not errors and sq.id not in seen_ids:
                survivors.append(sq)
                seen_ids.add(sq.id)
            else:
                reason = "; ".join(errors) or f"duplicate sub-question id '{sq.id}'"
                unsupported.append(
                    UnsupportedPart(description=sq.text, reason=reason)
                )

        candidate = Plan(
            request=request.text,
            target_sources=tuple(sorted({sq.source for sq in survivors})),
            sub_questions=tuple(survivors),
            unsupported_parts=tuple(unsupported),
            assumptions=draft.assumptions,
            partial=True,
        )
        if evaluate_plan(candidate, registry, live_view).accepted:
            return candidate

    return Plan(
        request=request.text,
        target_sources=(),
        sub_questions=(),
        unsupported_parts=(
            UnsupportedPart(
                description=request.text,
                reason=(
                    "the planner could not resolve a valid plan within the "
                    "iteration cap"
                ),
            ),
        ),
        partial=True,
    )


def run_react_loop(
    request: PlanRequest,
    registry: CardRegistry,
    live_view: LiveSourceView,
    drafter: PlanDrafter,
    *,
    config: LoopConfig | None = None,
) -> PlanningOutcome:
    """Drive the draft/grade/revise loop to an accepted or degraded plan."""

    config = config or LoopConfig()
    feedback: tuple[str, ...] = ()
    trace: list[PlanTraceEntry] = []
    last_draft: Plan | None = None

    for iteration in range(1, config.max_iterations + 1):
        context = DraftContext(
            registry=registry,
            live_view=live_view,
            prior_feedback=feedback,
            iteration=iteration,
        )
        draft = drafter.draft(request, context)
        last_draft = draft
        result: GateResult = evaluate_plan(draft, registry, live_view)
        trace.append(
            PlanTraceEntry(
                iteration=iteration,
                thought=_thought(draft, context),
                accepted=result.accepted,
                gate_feedback=result.reasons,
            )
        )
        if result.accepted:
            emitted = replace(draft, request=request.text, trace=tuple(trace))
            return PlanningOutcome(
                plan=emitted, converged=True, iterations=iteration
            )
        feedback = result.reasons

    degraded = degrade_plan(last_draft, request, registry, live_view)
    final = evaluate_plan(degraded, registry, live_view)
    trace.append(
        PlanTraceEntry(
            iteration=config.max_iterations + 1,
            thought="degraded to an honest partial plan after the iteration cap",
            accepted=final.accepted,
            gate_feedback=final.reasons,
        )
    )
    emitted = replace(degraded, trace=tuple(trace))
    return PlanningOutcome(
        plan=emitted, converged=False, iterations=config.max_iterations
    )
