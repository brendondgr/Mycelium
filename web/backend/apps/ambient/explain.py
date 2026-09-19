"""Mylo's account of why it thinks so, in its own words (Plan 04, step 10).

For every finding that will reach a person — a suggestion, a skill, a
proposal, a question, a recorded fact — the model writes the explanation they
will see: what the topic is, when and where it came up, how often, and why Mylo
read it the way it did. It is written **only from the observations' own
accounts** (each one Mylo's words, with its date and place), because by the
time deliberation runs the messages are gone. There is nothing to quote, and
the validator still refuses an explanation that reads like one.

No rule-based fallback (README principle 18): without the model the finding
waits, marked ``pending``, and the next night tries again.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from django.conf import settings
from django.utils import timezone

from .deliberate import _fingerprint
from .models import Finding, Observation, UnderstandingKind

logger = logging.getLogger(__name__)

COMPONENT = "ambient_explain"
PROMPT_VERSION = "e1"
MIN_CHARS = 40
MAX_CHARS = 700

CompleteFn = Callable[[str, str], str | None]

SYSTEM = (
    "You are Mylo, a research lab's assistant. You explain, briefly and "
    "plainly, why you noticed something about a person or a project. You use "
    "only the notes you are given, you never invent a date, place or count, and "
    "you never claim to have changed anything. Reply with one JSON object and "
    "nothing else."
)

READING = {
    UnderstandingKind.ENDURING_INTEREST: "a lasting interest of theirs",
    UnderstandingKind.CURRENT_CURIOSITY: "something they are curious about lately",
    UnderstandingKind.WORK_PREFERENCE: "a preference for how they like to work",
    UnderstandingKind.CAREER_DIRECTION: "where they want their career to go",
    UnderstandingKind.CAPABILITY: "something they can do",
    UnderstandingKind.LEARNING_GOAL: "something they want to learn",
    UnderstandingKind.PROJECT_INTENT: "what the project is trying to achieve",
    UnderstandingKind.PROJECT_DEVELOPMENT: "a change in the project",
}

WHY = {
    Finding.Outcome.SUGGEST: "Mylo would like to ask whether to include it.",
    Finding.Outcome.CAPABILITY: "Mylo would like to ask whether to add it as a skill.",
    Finding.Outcome.PROPOSE: (
        "Mylo would like to ask whether the project's stated aims should change."
    ),
    Finding.Outcome.ASK: "Mylo is unsure and would like to check.",
    Finding.Outcome.RECORD: "It was told to Mylo directly, so it is noted as a fact.",
}

PROMPT = """Write the explanation {audience} will see, in two or three short
sentences addressed to {address}: what the topic is, when and where it came up,
how often, and why you read it as {reading}. {why}

Topic: {topic}
Notes (your own earlier notes; each is dated, with where it came up):
{notes}

Reply as {{"explanation": "..."}}. Do not quote anybody, do not add dates or
places that are not in the notes, and do not say you have updated or changed
anything."""

_FORBIDDEN = (
    "i updated",
    "i've updated",
    "i have updated",
    "i changed",
    "i've changed",
    "i added",
)


@dataclass
class ExplainRun:
    pending: int = 0
    written: int = 0
    refused: int = 0
    unavailable: int = 0

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def _who(observation: Observation, finding: Finding) -> str:
    if finding.user_id:
        return "you"
    speaker = observation.speaker
    return (speaker.first_name or speaker.get_username()) if speaker else "someone"


def notes(finding: Finding, observations: list[Observation]) -> str:
    rows = []
    for o in sorted(observations, key=lambda o: o.observed_at):
        when = timezone.localtime(o.observed_at).strftime("%d %b")
        if o.place_kind == "dm":
            where = "in a direct message to Mylo"
        elif o.place_label:
            where = f"in #{o.place_label}"
        else:
            where = f"in a {o.place_kind}"
        rows.append(f"- {when}, {where}, {_who(o, finding)} [{o.force}]: {o.text}")
    return "\n".join(rows)


def prompt_for(finding: Finding, observations: list[Observation]) -> str:
    personal = finding.user_id is not None
    return PROMPT.format(
        audience="the person" if personal else "the project's members",
        address='them as "you"' if personal else "the project's members",
        reading=READING.get(finding.understanding_kind, "worth noting"),
        why=WHY.get(finding.outcome, ""),
        topic=finding.topic,
        notes=notes(finding, observations),
    )


def validate(text: str) -> str | None:
    text = " ".join((text or "").split())
    if not (MIN_CHARS <= len(text) <= MAX_CHARS):
        return None
    if '"' in text or "“" in text:
        return None
    if any(phrase in text.casefold() for phrase in _FORBIDDEN):
        return None
    return text


def _parse(raw: str | None) -> str | None:
    text = (raw or "").strip()
    start = text.find("{")
    if start < 0:
        return None
    try:
        data, _ = json.JSONDecoder().raw_decode(text[start:])
    except ValueError:
        return None
    return data.get("explanation") if isinstance(data, dict) else None


def _settings_complete(system: str, user: str) -> str | None:
    from apps.core.llm import LLMMessage, build_llm_client

    client = build_llm_client(component=COMPONENT)
    return client.complete(
        [LLMMessage("system", system), LLMMessage("user", user)]
    ).content


def _write(finding: Finding, observations, ask) -> tuple[str, str | None]:
    """``("written" | "refused" | "unavailable", text)``. One repair."""
    prompt = prompt_for(finding, observations)
    for _ in range(2):
        try:
            raw = ask(SYSTEM, prompt)
        except Exception as exc:  # noqa: BLE001 - unavailable, not broken
            logger.warning("ambient explanation unavailable (%s)", type(exc).__name__)
            return "unavailable", None
        text = validate(_parse(raw) or "")
        if text:
            return "written", text
        prompt += (
            "\n\nYour previous answer was not usable: two or three plain "
            "sentences, no quotation marks, no claim of having changed anything."
        )
    return "refused", None


def explain_pending(
    *, complete: CompleteFn | None = None, limit: int | None = None
) -> ExplainRun:
    """Write every pending explanation, up to the nightly cap."""
    run = ExplainRun()
    cap = limit if limit is not None else int(settings.AMBIENT_EXPLAIN_NIGHTLY_CAP)
    findings = list(
        Finding.objects.filter(explained=Finding.Explained.PENDING)
        .exclude(outcome=Finding.Outcome.IGNORE)
        .order_by("-influence", "pk")[:cap]
    )
    run.pending = len(findings)
    if not findings:
        return run
    evidence = {
        o.pk: o
        for o in Observation.objects.filter(
            pk__in={pk for f in findings for pk in f.observation_ids}
        ).select_related("speaker")
    }
    jobs = [
        (f, [evidence[pk] for pk in f.observation_ids if pk in evidence])
        for f in findings
    ]
    ask = complete if complete is not None else _settings_complete
    workers = max(1, min(int(settings.AMBIENT_EXTRACT_CONCURRENCY), len(jobs)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda job: _write(job[0], job[1], ask), jobs))
    for (finding, observations), (status, text) in zip(jobs, results, strict=True):
        if status == "written":
            finding.explanation = text
            finding.explained = Finding.Explained.WRITTEN
            finding.explained_from = _fingerprint(observations)
            finding.save(
                update_fields=[
                    "explanation",
                    "explained",
                    "explained_from",
                    "updated_at",
                ]
            )
            run.written += 1
        elif status == "refused":
            run.refused += 1
        else:
            run.unavailable += 1
    return run
