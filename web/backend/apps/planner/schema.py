"""The machine-readable plan the planner emits.

A plan routes a request: which live sources to use, the sub-questions to ask
each (every one carrying its own traversal limits — briefing 3.5 — and a
source-selection rationale — briefing 3.1), which canonical join keys bridge
sources, what the planner could not answer (briefing 3.3), what it assumed
(briefing 3.4), whether the plan is partial, and the ReAct trace behind it.

This module is pure data plus *intrinsic* structural validation
(:func:`schema_errors`). Validation against ground truth — live sources and
source cards — is the self-eval gate's job, kept separate on purpose.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SubQuestion:
    """One routed sub-question against exactly one source."""

    id: str
    text: str
    source: str
    entities: tuple[str, ...]
    rationale: str
    max_traversal_depth: int
    max_result_rows: int
    join_keys: tuple[str, ...] = ()
    edge_patterns: tuple[tuple[str, str, str], ...] = ()

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> SubQuestion:
        return cls(
            id=str(data["id"]),
            text=str(data["text"]),
            source=str(data["source"]),
            entities=tuple(str(e) for e in data.get("entities", [])),  # type: ignore[union-attr]
            rationale=str(data.get("rationale", "")),
            max_traversal_depth=int(data.get("max_traversal_depth", 0)),  # type: ignore[arg-type]
            max_result_rows=int(data.get("max_result_rows", 0)),  # type: ignore[arg-type]
            join_keys=tuple(str(k) for k in data.get("join_keys", [])),  # type: ignore[union-attr]
            edge_patterns=tuple(
                (str(p[0]), str(p[1]), str(p[2]))
                for p in data.get("edge_patterns", [])  # type: ignore[union-attr]
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "text": self.text,
            "source": self.source,
            "entities": list(self.entities),
            "rationale": self.rationale,
            "max_traversal_depth": self.max_traversal_depth,
            "max_result_rows": self.max_result_rows,
            "join_keys": list(self.join_keys),
            "edge_patterns": [list(p) for p in self.edge_patterns],
        }


@dataclass(frozen=True)
class UnsupportedPart:
    """A part of the request the planner honestly cannot answer."""

    description: str
    reason: str

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> UnsupportedPart:
        return cls(
            description=str(data["description"]),
            reason=str(data["reason"]),
        )

    def to_dict(self) -> dict[str, object]:
        return {"description": self.description, "reason": self.reason}


@dataclass(frozen=True)
class PlanTraceEntry:
    """One ReAct iteration: what was drafted and how the gate judged it."""

    iteration: int
    thought: str
    accepted: bool
    gate_feedback: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> PlanTraceEntry:
        return cls(
            iteration=int(data["iteration"]),  # type: ignore[arg-type]
            thought=str(data.get("thought", "")),
            accepted=bool(data["accepted"]),
            gate_feedback=tuple(
                str(f) for f in data.get("gate_feedback", [])  # type: ignore[union-attr]
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "iteration": self.iteration,
            "thought": self.thought,
            "accepted": self.accepted,
            "gate_feedback": list(self.gate_feedback),
        }


@dataclass(frozen=True)
class Plan:
    """A complete, machine-readable routing plan for one request."""

    request: str
    target_sources: tuple[str, ...]
    sub_questions: tuple[SubQuestion, ...]
    unsupported_parts: tuple[UnsupportedPart, ...] = ()
    assumptions: tuple[str, ...] = ()
    partial: bool = False
    trace: tuple[PlanTraceEntry, ...] = field(default=())

    def sources_used(self) -> frozenset[str]:
        return frozenset(sq.source for sq in self.sub_questions)

    def addresses_something(self) -> bool:
        """True if the plan answers or honestly declines part of the request."""

        return bool(self.sub_questions or self.unsupported_parts)

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> Plan:
        return cls(
            request=str(data.get("request", "")),
            target_sources=tuple(
                str(s) for s in data.get("target_sources", [])  # type: ignore[union-attr]
            ),
            sub_questions=tuple(
                SubQuestion.from_dict(sq)
                for sq in data.get("sub_questions", [])  # type: ignore[union-attr]
            ),
            unsupported_parts=tuple(
                UnsupportedPart.from_dict(up)
                for up in data.get("unsupported_parts", [])  # type: ignore[union-attr]
            ),
            assumptions=tuple(
                str(a) for a in data.get("assumptions", [])  # type: ignore[union-attr]
            ),
            partial=bool(data.get("partial", False)),
            trace=tuple(
                PlanTraceEntry.from_dict(t)
                for t in data.get("trace", [])  # type: ignore[union-attr]
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "request": self.request,
            "target_sources": list(self.target_sources),
            "sub_questions": [sq.to_dict() for sq in self.sub_questions],
            "unsupported_parts": [up.to_dict() for up in self.unsupported_parts],
            "assumptions": list(self.assumptions),
            "partial": self.partial,
            "trace": [t.to_dict() for t in self.trace],
        }


def schema_errors(plan: Plan) -> list[str]:
    """Intrinsic structural problems with a plan, independent of ground truth.

    This is the "schema adherence" check (briefing 6.1): required values are
    present and well-formed. It does not consult cards or the live-source view;
    that is the gate's role.
    """

    errors: list[str] = []

    seen_ids: set[str] = set()
    for index, sq in enumerate(plan.sub_questions):
        where = sq.id or f"#{index}"
        if not sq.id.strip():
            errors.append(f"sub-question {where}: missing id")
        elif sq.id in seen_ids:
            errors.append(f"sub-question {where}: duplicate id")
        else:
            seen_ids.add(sq.id)
        if not sq.text.strip():
            errors.append(f"sub-question {where}: missing text")
        if not sq.source.strip():
            errors.append(f"sub-question {where}: missing source")
        if not sq.entities:
            errors.append(f"sub-question {where}: must reference at least one entity")
        if not sq.rationale.strip():
            errors.append(f"sub-question {where}: missing source-selection rationale")
        if sq.max_traversal_depth < 1:
            errors.append(f"sub-question {where}: missing/invalid max_traversal_depth")
        if sq.max_result_rows < 1:
            errors.append(f"sub-question {where}: missing/invalid max_result_rows")

    for index, part in enumerate(plan.unsupported_parts):
        if not part.description.strip():
            errors.append(f"unsupported part #{index}: missing description")
        if not part.reason.strip():
            errors.append(f"unsupported part #{index}: missing reason")

    return errors


def coerce_sequence(value: Sequence[str]) -> tuple[str, ...]:
    """Helper for drafters: normalize a sequence of strings to a tuple."""

    return tuple(str(v) for v in value)
