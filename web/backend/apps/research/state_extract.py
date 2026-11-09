"""Read a project's state out of a document it already has.

Nobody wants to answer five questions about a project whose abstract, proposal or
pitch deck already answers them. This turns one uploaded document into a
**proposal**: every field it produces is marked ``inferred``, none of it is
applied until a person accepts it, and a stated field is never overwritten by it
(plan H9 / invariant 9).

It is deliberately the same shape as
:mod:`tools.retrieval.collect.extract`, which is the pattern this codebase already
trusts for turning prose into structure:

1. **A fixed schema.** The model is asked for named fields, not for a description.
2. **Deterministic validation.** Shape, types and dates are checked in code.
3. **Grounding checks.** Every extracted sentence has to be traceable to the
   document — an extractor that invents a claimed contribution is worse than one
   that returns nothing, because the invention arrives wearing the team's voice.
4. **A bounded repair loop.** One retry naming what failed, then refusal.

Refusal is a real outcome and is reported as one. The questions stay unanswered
and the wizard's fields stay empty, which is the honest result of a document that
did not say.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from apps.research import state as schema

#: The name every call here is billed against in the daily LLM ledger.
COMPONENT = "project_state_extraction"

#: How much document to send. A proposal runs to tens of thousands of words and
#: the answers are almost always in the opening; sending all of it costs tokens
#: and buries the part that matters.
MAX_SOURCE_CHARS = 24_000

#: One retry, naming what failed. A second adds cost and, measured on the
#: opportunity extractor this mirrors, essentially no recoveries.
MAX_ATTEMPTS = 2

#: Content words a claim must share with the document. Well below the opportunity
#: extractor's prose floor because these are short answers, not summaries: a
#: one-clause contribution has perhaps six content words, and demanding half of
#: them appear verbatim would refuse every correct answer.
GROUNDING_FLOOR = 0.34

#: Below this many content words the ratio is not a meaningful test, and the
#: claim is instead held to the narrower promise: invent no specifics.
MIN_CLAIM_WORDS = 6

_WORD = re.compile(r"[a-z0-9]+")
_SPECIFIC = re.compile(r"\$[\d,]+(?:\.\d+)?|\b\d{4}\b|\b\d+(?:st|nd|rd|th)\b")

_STOP = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were",
    "our", "its", "into", "than", "then", "they", "them", "their", "there",
    "which", "while", "will", "would", "can", "could", "has", "have", "had",
    "not", "but", "all", "any", "use", "used", "using", "new", "also", "may",
    "these", "those", "such", "been", "more", "most", "other", "some", "when",
}

SYSTEM = (
    "You read a research document and report what the project behind it claims. "
    "You report only what the document says. You never infer, never generalise, "
    "and never fill a field the document does not answer — an empty field is the "
    "correct answer to a question the document does not address. Reply with one "
    "JSON object and nothing else."
)

PROMPT = """Read the document below and report the project's state as JSON.

Fields, all optional — omit or leave empty anything the document does not say:

  "problem": one sentence naming the question the project answers.
  "claimed_contribution": one sentence naming what is new about its answer.
  "method": a list of techniques the project uses.
  "data": a list of datasets or corpora it works on.
  "planned_components": a list of parts it intends to build but has not yet.
  "blockers": a list of things the document says are unresolved or missing.
  "stage": one or two words for where the work is (e.g. "experiments").
  "venue_targets": a list of venues it names as targets.

Rules:
- Use the document's own wording wherever you can.
- Do not invent numbers, dates, or venue names.
- If the document is not about a research project, return {{}}.

DOCUMENT
--------
{source}
"""


CompleteFn = Callable[[str, str], str | None]


@dataclass
class ExtractionOutcome:
    """What one document yielded, and why it yielded that."""

    #: A ``{"slow": …, "fast": …, "provenance": …}`` payload, ready to PATCH.
    #: Empty when the document did not answer or the model could not be trusted.
    proposal: dict = field(default_factory=dict)
    ok: bool = False
    #: Why it refused, in the words a person can act on.
    reason: str = ""
    #: What failed on each attempt — kept for the repair prompt and for diagnosis.
    failures: list[str] = field(default_factory=list)
    attempts: int = 0

    @property
    def is_empty(self) -> bool:
        return schema.is_empty(self.proposal)

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "reason": self.reason,
            "attempts": self.attempts,
            "failures": list(self.failures),
            "proposal": self.proposal,
        }


def _words(text: str) -> set[str]:
    found = _WORD.findall((text or "").lower())
    return {word for word in found if word not in _STOP and len(word) > 2}


def _specifics(text: str) -> set[str]:
    return {
        match.group(0).replace(",", "").lstrip("$")
        for match in _SPECIFIC.finditer(text or "")
    }


def grounding_failures(claim: str, source: str) -> list[str]:
    """Check one extracted claim against the document. Two regimes, by length.

    A claim long enough to carry an overlap ratio is held to one. A short claim
    cannot be — a six-word contribution rephrased in the model's own words would
    fail any ratio worth setting — so it is held to the narrower and stricter
    promise instead: every specific in it appears in the document.
    """
    claim_words = _words(claim)
    if not claim_words:
        return []
    invented = _specifics(claim) - _specifics(source)
    if invented:
        return [f"invented specifics {sorted(invented)}: {claim[:80]!r}"]
    if len(claim_words) < MIN_CLAIM_WORDS:
        return []
    overlap = len(claim_words & _words(source)) / len(claim_words)
    if overlap < GROUNDING_FLOOR:
        return [
            f"ungrounded ({overlap:.2f} < {GROUNDING_FLOOR}): {claim[:80]!r}"
        ]
    return []


def _parse(raw: str | None) -> dict | None:
    """The first JSON object in the reply, or ``None``.

    Models wrap JSON in prose and fences however they feel. Refusing anything
    that is not a bare object throws away answers that were correct, so the first
    balanced object is taken and everything around it ignored.
    """
    text = (raw or "").strip()
    if not text:
        return None
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                try:
                    parsed = json.loads(text[start : index + 1])
                except ValueError:
                    return None
                return parsed if isinstance(parsed, dict) else None
    return None


def _to_state(payload: dict) -> dict:
    """One model reply into the state shape, with everything marked inferred."""
    slow = {
        "problem": payload.get("problem") or "",
        "claimed_contribution": payload.get("claimed_contribution") or "",
        "method": payload.get("method") or [],
        "data": payload.get("data") or [],
        "planned_components": payload.get("planned_components") or [],
        "blockers": payload.get("blockers") or [],
    }
    fast = {
        "stage": payload.get("stage") or "",
        "venue_targets": payload.get("venue_targets") or [],
    }
    normalised = schema.normalise_state({"slow": slow, "fast": fast})
    # Everything a document produced is a proposal until a person accepts it.
    # The default is "stated", so it has to be overridden explicitly here rather
    # than left to the normaliser.
    normalised["provenance"] = {
        name: "inferred" for name in normalised["provenance"]
    }
    return normalised


def _claims(state: dict) -> list[str]:
    """Every free-text claim in a proposal, for the grounding check."""
    slow = state.get("slow") or {}
    fast = state.get("fast") or {}
    out = [slow.get("problem") or "", slow.get("claimed_contribution") or ""]
    for name in ("method", "data", "planned_components"):
        out.extend(slow.get(name) or [])
    out.extend(row.get("text", "") for row in slow.get("blockers") or [])
    out.extend(target.get("venue", "") for target in fast.get("venue_targets") or [])
    return [claim for claim in out if claim]


def extract_project_state(
    source: str,
    *,
    complete: CompleteFn | None = None,
) -> ExtractionOutcome:
    """One document into a state proposal. Never raises.

    ``complete`` is the injectable ``(system, user) -> text`` seam; without one it
    routes through the configured client. A model that is down, slow or absent
    produces a refusal, not an exception — the wizard's questions simply stay for
    the person to answer.
    """
    text = " ".join((source or "").split())[:MAX_SOURCE_CHARS]
    if len(_words(text)) < 20:
        return ExtractionOutcome(
            reason="the document has too little text to read a project out of"
        )

    ask = complete if complete is not None else _settings_complete()
    outcome = ExtractionOutcome()
    prompt = PROMPT.format(source=text)

    for attempt in range(1, MAX_ATTEMPTS + 1):
        outcome.attempts = attempt
        try:
            raw = ask(SYSTEM, prompt)
        except Exception as exc:  # noqa: BLE001 — a refusal, not a crash
            outcome.failures.append(f"model call failed: {exc}")
            outcome.reason = "Mylo could not read the document just now"
            return outcome

        parsed = _parse(raw)
        if parsed is None:
            outcome.failures.append("reply was not a JSON object")
            prompt = _repair_prompt(text, outcome.failures)
            continue

        proposal = _to_state(parsed)
        if schema.is_empty(proposal):
            # A correct answer to a document that does not describe a project.
            outcome.ok = True
            outcome.reason = "the document does not describe a project's state"
            return outcome

        failures = [
            problem
            for claim in _claims(proposal)
            for problem in grounding_failures(claim, text)
        ]
        if failures:
            outcome.failures.extend(failures)
            prompt = _repair_prompt(text, failures)
            continue

        outcome.proposal = proposal
        outcome.ok = True
        return outcome

    outcome.reason = (
        "Mylo could not ground what it read in the document, so it proposed nothing"
    )
    return outcome


def _repair_prompt(source: str, failures: list[str]) -> str:
    """The retry: the same task, with what went wrong stated plainly."""
    named = "\n".join(f"- {failure}" for failure in failures[-6:])
    return (
        PROMPT.format(source=source)
        + "\n\nYour previous answer was rejected:\n"
        + named
        + "\n\nUse the document's own wording. Leave a field empty rather than "
        "filling it from anything but the document."
    )


def _settings_complete() -> CompleteFn:
    def ask(system: str, prompt: str) -> str | None:
        from apps.core.llm import LLMMessage, build_llm_client

        client = build_llm_client(component=COMPONENT)
        response = client.complete(
            [LLMMessage("system", system), LLMMessage("user", prompt)],
        )
        return response.content

    return ask
