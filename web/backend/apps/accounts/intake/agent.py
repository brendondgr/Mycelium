"""Mylo intake agent — a bounded, schema-filling onboarding loop.

This is a *schema-filling* agent, not open chat (brief Phase E), reusing the
planner's bounded-loop shape: seed from free text and/or a Phase C author draft,
find the thin or missing contract fields, ask **one clarifying question per
turn**, cap the loop, and emit structured output validated against the Phase A
contract — with a confirmation summary before save.

It is deterministic by default so onboarding never hard-depends on the model: the
form flow needs no LLM. An ``extractor`` seam can be injected (LLM-backed) to
parse messier free-text answers; the default splits on commas/semicolons.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import Any

from ..interests import stamp_version, validate_interests
from .drafts import AuthorProfileDraft

# Career stages mirror apps.accounts.models.AcademicTitle (kept as plain strings
# so the agent stays free of a hard model import for unit testing).
CAREER_STAGES = ("student", "postdoc", "researcher", "pi", "staff")

# Career stage -> the fellowship matcher's ladder token
# (tools.recommendation.fellowships.STAGE_LADDER). "researcher" and "staff" are absent
# on
# purpose: a staff scientist and a senior graduate student both pick them, so they
# place nobody on the ladder and must not be guessed at.
CAREER_STAGE_TO_ELIGIBILITY_STAGE = {
    "student": "doctoral_early",
    "postdoc": "postdoc",
    "pi": "postdoc",
}

_EMPTY_ANSWERS = {"", "none", "n/a", "na", "skip", "-"}


@dataclass(frozen=True)
class IntakeField:
    """One clarifying question and the contract field it fills."""

    key: str
    prompt: str
    kind: str  # "list" | "career_stage"


# The clarifying sequence, in priority order (brief Phase E). Only the thin or
# missing ones are actually asked, and the loop is capped.
INTAKE_FIELDS: tuple[IntakeField, ...] = (
    IntakeField(
        "areas",
        "Which research areas best describe your work? (comma-separated)",
        "list",
    ),
    IntakeField(
        "eligibility",
        "What is your career stage? (student, postdoc, researcher, PI, or staff)",
        "career_stage",
    ),
    IntakeField(
        "funding_needs",
        "What kinds of funding are you looking for? (comma-separated, or 'none')",
        "list",
    ),
    IntakeField(
        "exclusions",
        "Anything you would rather not be shown? (comma-separated, or 'none')",
        "list",
    ),
)


@dataclass
class IntakeState:
    """The evolving intake session: accumulating interests + remaining questions."""

    interests: dict[str, Any] = dc_field(default_factory=dict)
    pending: list[IntakeField] = dc_field(default_factory=list)
    asked: list[str] = dc_field(default_factory=list)
    turns: int = 0
    done: bool = False


def _split_list(raw: str) -> list[str]:
    cleaned = raw.replace(";", ",").replace("\n", ",")
    items = [part.strip() for part in cleaned.split(",")]
    return [item for item in items if item and item.lower() not in _EMPTY_ANSWERS]


def _default_extractor(field: IntakeField, raw: str) -> Any:
    text = (raw or "").strip()
    if field.kind == "career_stage":
        stage = text.lower()
        return stage if stage in CAREER_STAGES else text
    return _split_list(text)


ExtractorFn = Callable[[IntakeField, str], Any]


class IntakeAgent:
    """Drive a capped onboarding loop into a contract-valid interests dict."""

    def __init__(self, *, max_turns: int = 4, extractor: ExtractorFn | None = None):
        if max_turns < 1:
            raise ValueError("max_turns must be >= 1")
        self.max_turns = max_turns
        self._extract = extractor or _default_extractor

    # -- seeding ---------------------------------------------------------------

    def start(
        self,
        *,
        free_text: str = "",
        draft: AuthorProfileDraft | None = None,
        seed_interests: dict[str, Any] | None = None,
    ) -> IntakeState:
        interests: dict[str, Any] = {}
        if draft is not None:
            interests.update(draft.to_interests())
        if seed_interests:
            interests.update(seed_interests)
        if free_text.strip() and not interests.get("statement"):
            interests["statement"] = free_text.strip()
        interests = stamp_version(interests)

        pending = [f for f in INTAKE_FIELDS if self._is_thin(interests, f)]
        pending = pending[: self.max_turns]
        state = IntakeState(interests=interests, pending=pending)
        state.done = not pending
        return state

    def _is_thin(self, interests: dict[str, Any], field: IntakeField) -> bool:
        if field.kind == "career_stage":
            return "career_stage" not in (interests.get("eligibility") or {})
        return not interests.get(field.key)

    # -- loop ------------------------------------------------------------------

    def question(self, state: IntakeState) -> str | None:
        """The next clarifying question, or ``None`` when the loop is complete."""
        if state.done or not state.pending or state.turns >= self.max_turns:
            return None
        return state.pending[0].prompt

    def answer(self, state: IntakeState, raw_answer: str) -> IntakeState:
        if state.done or not state.pending:
            return state
        field = state.pending.pop(0)
        value = self._extract(field, raw_answer)
        self._apply(state.interests, field, value)
        state.asked.append(field.key)
        state.turns += 1
        if not state.pending or state.turns >= self.max_turns:
            state.done = True
        return state

    def _apply(self, interests: dict[str, Any], field: IntakeField, value: Any) -> None:
        if field.kind == "career_stage":
            if value:
                eligibility = dict(interests.get("eligibility") or {})
                eligibility["career_stage"] = value
                # Also write the fellowship matcher's own vocabulary. The two
                # vocabularies are different by design (this one mirrors
                # AcademicTitle), and nothing used to bridge them, so an intake
                # answer of "postdoc" was invisible to fellowship eligibility.
                stage = CAREER_STAGE_TO_ELIGIBILITY_STAGE.get(value)
                if stage:
                    eligibility["stage"] = stage
                interests["eligibility"] = eligibility
        elif value:  # list field — only set when the answer was non-empty
            interests[field.key] = value

    # -- output ----------------------------------------------------------------

    def summary(self, state: IntakeState) -> str:
        """A human-readable confirmation card to show before saving."""
        interests = state.interests
        lines = ["Here is the profile I will save:"]
        statement = interests.get("statement")
        if statement:
            lines.append(f"  Summary: {statement}")
        for key in ("areas", "keywords", "funding_needs", "exclusions"):
            values = interests.get(key)
            if values:
                label = key.replace("_", " ").title()
                lines.append(f"  {label}: {', '.join(values)}")
        eligibility = interests.get("eligibility") or {}
        if eligibility.get("career_stage"):
            lines.append(f"  Career stage: {eligibility['career_stage']}")
        return "\n".join(lines)

    def finalize(self, state: IntakeState) -> dict[str, Any]:
        """Validate the gathered interests against the contract (raises if not)."""
        return validate_interests(state.interests)
