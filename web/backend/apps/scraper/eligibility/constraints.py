"""Structured eligibility constraints from a fellowship's *prose*.

The five Illinois stage facets (``Master's`` … ``Postdoctoral/Post-graduate``)
cannot express the constraint that actually binds most awards. "Applicants must
have received the PhD within the previous 24 months" is a sentence, and it lives
in ``metadata["eligibility"]`` — a list of scraped sentences that, before this
module, no matcher ever read. A postdoctoral award therefore reached anyone whose
facets happened to line up, because the facets are not where the rule is written.

Two layers, cheapest first:

1. **Patterns.** A small set of well-attested phrasings — degree requirements and
   post-doctorate time windows — matched deterministically. Free, offline, and
   exact where it fires.
2. **Mylo.** One extraction call for the records the patterns did not resolve,
   returning the same shape. Behind ``FELLOWSHIP_CONSTRAINT_EXTRACTION``; when the
   model is unavailable the pattern result stands on its own.

Extraction happens once per record at ingest and is carried forward on re-ingest
(:mod:`apps.scraper.fellowships.ingest`), so neither layer runs nightly over a
corpus that has not changed.

The output block, stored at ``metadata["constraints"]``:

    {
      "min_stage": "" | masters | doctoral_early | doctoral_dissertation | postdoc,
      "max_years_post_phd": int | None,
      "degree_required": "" | "bachelors" | "masters" | "phd",
      "source": "patterns" | "llm" | "none",
      "evidence": "<the phrase this was read from>",
    }

Everything is optional and everything defaults to *unconstrained*: a constraint
this module did not find must never invent a gate.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Sequence

logger = logging.getLogger(__name__)

CompleteFn = Callable[[str], str | None]

#: Ladder tokens this module may emit, mirroring
#: :data:`apps.content.fellowships.STAGE_LADDER`.
STAGE_TOKENS = ("masters", "doctoral_early", "doctoral_dissertation", "postdoc")

DEGREES = ("bachelors", "masters", "phd")

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

# "received the PhD", "hold a doctorate", "completed their doctoral degree"
_DOCTORATE_HELD = re.compile(
    r"\b(receiv\w*|earn\w*|hold\w*|complet\w*|obtain\w*|award\w*|confer\w*)\b"
    r"[^.]{0,40}?\b(ph\.?\s?d\.?|doctorate|doctoral degree)\b",
    re.I,
)

# "within five years of", "no more than 3 years since", "within 24 months of",
# "within the previous two years". The optional filler covers the determiners the
# phrasing habitually carries without letting the trigger drift a clause away.
_WINDOW = re.compile(
    r"\b(?:within|no (?:more|later) than|not more than|at most|less than)\s+"
    r"(?:the\s+)?(?:previous|past|preceding|last|prior)?\s*"
    r"(?P<n>\d{1,2}|" + "|".join(_NUMBER_WORDS) + r")\s+"
    r"(?P<unit>year|month)s?\b",
    re.I,
)

_DEGREE_PATTERNS = (
    (
        "phd",
        re.compile(
            r"\b(?:must|should|shall|required to)\b[^.]{0,60}?"
            r"\b(?:hold|have|possess|earned?|received?)\b[^.]{0,30}?"
            r"\b(?:ph\.?\s?d\.?|doctorate|doctoral degree)\b",
            re.I,
        ),
    ),
    (
        "masters",
        re.compile(
            r"\b(?:must|should|shall|required to)\b[^.]{0,60}?"
            r"\b(?:hold|have|possess|earned?|received?)\b[^.]{0,30}?"
            r"\b(?:master'?s(?: degree)?|m\.?a\.?|m\.?s\.?)\b",
            re.I,
        ),
    ),
)

_POSTDOC_HINTS = re.compile(
    r"\b(postdoctoral (?:fellow|scholar|research|appointment|training)|"
    r"post-?doctoral (?:fellow|scholar|research)|"
    r"recent (?:ph\.?\s?d\.?|doctoral) (?:recipient|graduate)s?)\b",
    re.I,
)

_DISSERTATION_HINTS = re.compile(
    r"\b(dissertation (?:research|writ\w+|stage|phase|completion)|"
    r"advanced to candidacy|abd|all but dissertation)\b",
    re.I,
)


def empty_constraints() -> dict:
    """The unconstrained block — what a record gets when nothing was found."""
    return {
        "min_stage": "",
        "max_years_post_phd": None,
        "degree_required": "",
        "source": "none",
        "evidence": "",
    }


def _as_count(raw: str) -> int | None:
    token = raw.strip().lower()
    if token.isdigit():
        return int(token)
    return _NUMBER_WORDS.get(token)


def _sentences(eligibility, note: str = "") -> list[str]:
    """The prose to read, as individual sentences."""
    if isinstance(eligibility, str):
        parts = [eligibility]
    else:
        parts = [str(part) for part in (eligibility or [])]
    if note:
        parts.append(str(note))
    out: list[str] = []
    for part in parts:
        for chunk in re.split(r"(?<=[.;])\s+", part):
            text = " ".join(chunk.split())
            if text:
                out.append(text)
    return out


def extract_by_pattern(eligibility, note: str = "") -> dict:
    """Constraints readable from the prose without a model.

    Conservative by construction: a post-doctorate time window is only recorded
    when the same sentence also says the doctorate must already be held, so
    "funding runs for no more than 3 years" is not mistaken for an eligibility
    limit.
    """
    out = empty_constraints()
    for sentence in _sentences(eligibility, note):
        if not out["degree_required"]:
            for degree, pattern in _DEGREE_PATTERNS:
                if pattern.search(sentence):
                    out["degree_required"] = degree
                    out["evidence"] = out["evidence"] or sentence[:240]
                    break

        holds_doctorate = bool(_DOCTORATE_HELD.search(sentence))
        if holds_doctorate:
            if not out["degree_required"]:
                out["degree_required"] = "phd"
            window = _WINDOW.search(sentence)
            if window and out["max_years_post_phd"] is None:
                count = _as_count(window.group("n"))
                if count is not None:
                    years = count if window.group("unit").lower() == "year" else None
                    if years is None:
                        # Months round up: "within 18 months" is a two-year window
                        # for a year-granularity comparison, and rounding down
                        # would gate someone the award would accept.
                        years = max(1, -(-count // 12))
                    out["max_years_post_phd"] = years
            out["evidence"] = out["evidence"] or sentence[:240]

        if not out["min_stage"]:
            if _POSTDOC_HINTS.search(sentence) or holds_doctorate:
                out["min_stage"] = "postdoc"
                out["evidence"] = out["evidence"] or sentence[:240]
            elif _DISSERTATION_HINTS.search(sentence):
                out["min_stage"] = "doctoral_dissertation"
                out["evidence"] = out["evidence"] or sentence[:240]

    if out["degree_required"] == "phd" and not out["min_stage"]:
        out["min_stage"] = "postdoc"
    if out["min_stage"] or out["degree_required"] or out["max_years_post_phd"]:
        out["source"] = "patterns"
    return out


def is_resolved(constraints: dict) -> bool:
    """True when the patterns found something worth gating on."""
    return bool(
        constraints.get("min_stage")
        or constraints.get("degree_required")
        or constraints.get("max_years_post_phd") is not None
    )


# --------------------------------------------------------------------------- #
# Mylo's pass — for the prose the patterns did not resolve
# --------------------------------------------------------------------------- #

_SYSTEM_PROMPT = (
    "You read fellowship eligibility text and report only what it *states* as a "
    "requirement of the applicant. You never infer, never generalise from the "
    "award's name, and never fill a field the text does not decide.\n"
    "Return ONLY one JSON object:\n"
    '  {"items": [{"item": <number>, "min_stage": <one of "masters", '
    '"doctoral_early", "doctoral_dissertation", "postdoc", or "">, '
    '"max_years_post_phd": <integer or null>, "degree_required": <one of '
    '"bachelors", "masters", "phd", or "">, "evidence": <the exact phrase you '
    "read it from, or \"\">}]}\n"
    "min_stage is the EARLIEST career stage the award accepts — an award open to "
    "doctoral students and postdocs has min_stage \"doctoral_early\". "
    "max_years_post_phd is set only when the text limits how long ago the "
    "doctorate was awarded; express months as whole years, rounded up. Leave a "
    "field empty or null whenever the text is silent. No prose outside the JSON, "
    "no markdown fences."
)

#: How much prose one record contributes to the prompt.
_TEXT_CHARS = 700


def _build_prompt(units: Sequence[tuple[str, str]]) -> str:
    lines: list[str] = []
    for index, (title, text) in enumerate(units, start=1):
        lines.append(f"ITEM {index}: {title}")
        lines.append(f"  Eligibility: {text[:_TEXT_CHARS]}")
        lines.append("")
    return "\n".join(lines).strip()


def _settings_complete(prompt: str) -> str | None:
    from apps.core.llm import LLMMessage, build_llm_client

    client = build_llm_client(component="fellowship_constraints")
    response = client.complete(
        [LLMMessage("system", _SYSTEM_PROMPT), LLMMessage("user", prompt)]
    )
    return response.content


def _coerce(row: dict) -> dict:
    """One model row → a validated constraints block. Unknown values are dropped."""
    out = empty_constraints()
    stage = str(row.get("min_stage") or "").strip()
    if stage in STAGE_TOKENS:
        out["min_stage"] = stage
    degree = str(row.get("degree_required") or "").strip().lower()
    if degree in DEGREES:
        out["degree_required"] = degree
    years = row.get("max_years_post_phd")
    if isinstance(years, bool):
        years = None
    if isinstance(years, (int, float)) and 0 < years <= 30:
        out["max_years_post_phd"] = int(years)
    out["evidence"] = " ".join(str(row.get("evidence") or "").split())[:240]
    if is_resolved(out):
        out["source"] = "llm"
    return out


def extract_by_model(
    units: Sequence[tuple[str, str]], *, complete: CompleteFn | None = None
) -> dict[int, dict]:
    """``{index: constraints}`` for the units the model resolved; ``{}`` on failure.

    Never raises: an unreachable model leaves every record on its pattern result,
    which is the same degradation every other Mylo seam takes.
    """
    if not units:
        return {}
    ask = complete if complete is not None else _settings_complete
    try:
        raw = ask(_build_prompt(units))
    except Exception as exc:
        logger.warning(
            "fellowship constraint extraction unavailable (%s); patterns only.", exc
        )
        return {}
    if not raw:
        return {}
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        return {}
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        logger.warning("fellowship constraint extraction returned non-JSON; ignoring.")
        return {}
    rows = data.get("items") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return {}

    out: dict[int, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            index = int(row.get("item")) - 1
        except (TypeError, ValueError):
            continue
        if not 0 <= index < len(units):
            continue
        block = _coerce(row)
        if is_resolved(block):
            out[index] = block
    return out
