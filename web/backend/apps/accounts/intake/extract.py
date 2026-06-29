"""LLM-driven extraction of a structured research profile from free text.

This is the engine behind onboarding's "Grow my profile": given the gathered
text about a researcher — their works' titles, declared interests, and/or an
uploaded résumé — one call to the configured language model returns a single JSON
object holding every interest field at once (statement, areas, keywords, methods,
skills). When no model is configured (or the call fails), an injectable
deterministic fallback keeps the flow working offline and in CI.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["FIELD_KEYS", "ProfileFields", "extract_profile_fields"]

# The five interest fields the model fills (everything a profile needs from text).
FIELD_KEYS = ("statement", "areas", "keywords", "methods", "skills")

ProfileFields = dict[str, Any]
CompleteFn = Callable[[str], str | None]
FallbackFn = Callable[[], ProfileFields]

_MAX_TEXT = 12000

_SYSTEM_PROMPT = (
    "You build a researcher's interest profile from the supplied text (their "
    "papers, declared interests, and/or résumé). Return ONLY one JSON object "
    "with exactly these keys:\n"
    '  "statement": a 2-4 sentence first-person research summary,\n'
    '  "areas": list of research areas or fields,\n'
    '  "keywords": list of specific topics or keywords,\n'
    '  "methods": list of techniques or methodologies,\n'
    '  "skills": list of tools, languages, and technical skills.\n'
    "Ground every value in the supplied text — do not invent topics, "
    "affiliations, or accomplishments. Use an empty string or empty list when "
    "the text does not support a field. Output only the JSON object: no prose, "
    "no explanation, no markdown code fences."
)


def extract_profile_fields(
    text: str,
    *,
    complete: CompleteFn | None = None,
    fallback: FallbackFn | None = None,
) -> ProfileFields:
    """Return ``{statement, areas, keywords, methods, skills}`` for ``text``.

    Tries the LLM seam first (``complete``; defaults to the configured endpoint).
    If the model is unavailable, errors, or returns nothing usable, calls
    ``fallback`` when given, otherwise returns empty fields. The result always
    has all five keys with the right types.
    """

    corpus = (text or "").strip()
    if corpus:
        ask = complete if complete is not None else _settings_complete
        raw: str | None = None
        try:
            raw = ask(_build_prompt(corpus))
        except Exception:
            # Any failure (no model, no SDK, network, bad response) -> fall back,
            # but make the reason visible: a silent fallback is indistinguishable
            # from "the model is ignoring me".
            logger.warning(
                "LLM profile extraction failed; using deterministic fallback.",
                exc_info=True,
            )
        else:
            parsed = _parse_fields(raw)
            if parsed is not None and _has_signal(parsed):
                return parsed
            if parsed is None:
                logger.warning(
                    "LLM returned no parseable JSON for profile extraction; "
                    "using fallback. Response head: %r",
                    (raw or "")[:300],
                )
            else:
                logger.warning(
                    "LLM profile extraction returned only empty fields; "
                    "using fallback."
                )

    if fallback is not None:
        return _normalize(fallback())
    return _empty()


def _settings_complete(prompt: str) -> str | None:
    from apps.core.llm import LLMMessage, build_llm_client

    # Use the configured reasoning level and token budget (LLM_REASONING /
    # LLM_MAX_TOKENS). A hardcoded small cap here starves reasoning models: the
    # reasoning trace eats the budget and the JSON answer is truncated to
    # nothing, which then looks like the model "only filled skills".
    client = build_llm_client()
    response = client.complete(
        [
            LLMMessage("system", _SYSTEM_PROMPT),
            LLMMessage("user", prompt),
        ]
    )
    if response.finish_reason == "length" and not (response.content or "").strip():
        logger.warning(
            "LLM response was truncated (finish_reason=length) before producing "
            "any answer; raise LLM_MAX_TOKENS so the model can finish."
        )
    return response.content


def _build_prompt(text: str) -> str:
    return f"Researcher source text:\n\n{text[:_MAX_TEXT]}"


# -- parsing ------------------------------------------------------------------


def _parse_fields(raw: str | None) -> ProfileFields | None:
    if not raw:
        return None
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return _normalize(data)


def _normalize(data: ProfileFields) -> ProfileFields:
    return {
        "statement": _as_str(data.get("statement") or data.get("summary")),
        "areas": _as_list(data.get("areas")),
        "keywords": _as_list(data.get("keywords")),
        "methods": _as_list(data.get("methods")),
        "skills": _as_list(data.get("skills")),
    }


def _has_signal(fields: ProfileFields) -> bool:
    return bool(
        fields["statement"]
        or fields["areas"]
        or fields["keywords"]
        or fields["methods"]
        or fields["skills"]
    )


def _empty() -> ProfileFields:
    return {"statement": "", "areas": [], "keywords": [], "methods": [], "skills": []}


def _as_str(value: Any) -> str:
    return " ".join(str(value).split()) if isinstance(value, str) else ""


def _as_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for item in value:
        text = " ".join(str(item).split())
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            out.append(text)
    return out
