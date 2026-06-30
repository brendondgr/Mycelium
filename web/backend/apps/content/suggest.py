"""Turn RAG-retrieved papers into ranked, explained research suggestions.

Retrieval gives us the papers nearest a researcher's interests; this module turns
that ordered candidate list into a short digest: the few most worth their
attention, each with a one-line headline and a plain-language reason it matters to
*them*. The language model does the selecting and justifying when it is reachable;
a deterministic fallback (rank by similarity, template the reason from interest
overlap) keeps the pipeline producing suggestions offline and in CI.

Mirrors :mod:`apps.accounts.intake.extract`: an injectable ``complete`` seam, a
tolerant JSON parser, and a fallback that never raises — so a missing or flaky
model degrades to a still-useful digest rather than an empty one.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Sequence
from typing import Any

from .models import ContentItem

logger = logging.getLogger(__name__)

CompleteFn = Callable[[str], str | None]

#: A suggestion is a plain JSON-serializable dict (it lands in RelevanceScore
#: ``signals`` and the daily-report API response).
Suggestion = dict[str, Any]

#: How many candidates we show the model, and how many suggestions we return.
_MAX_CANDIDATES = 12
_DEFAULT_LIMIT = 5
_ABSTRACT_CHARS = 600

_SYSTEM_PROMPT = (
    "You are Mylo, a research scout. Given a researcher's interest profile and a "
    "numbered list of candidate papers, choose the ones most worth their "
    "attention and explain why. Return ONLY one JSON object:\n"
    '  {"suggestions": [{"paper": <number>, "headline": <short title-case '
    'phrase>, "reason": <1-2 sentences, second person, why THIS researcher '
    'should read it>}]}\n'
    "Rank best first. Only use papers from the list (reference them by their "
    "number). Ground every reason in the paper and the profile — do not invent "
    "findings. No prose outside the JSON, no markdown fences."
)


def generate_suggestions(
    interests: dict,
    hits: Sequence[tuple[ContentItem, float]],
    *,
    limit: int = _DEFAULT_LIMIT,
    complete: CompleteFn | None = None,
) -> list[Suggestion]:
    """Return up to ``limit`` ranked suggestions for ``hits``.

    ``hits`` is the retrieval output (``(ContentItem, similarity)``), already in
    descending similarity. Tries the model first (``complete`` seam, defaults to
    the configured endpoint); falls back to a similarity ranking with templated
    reasons whenever the model is unavailable, errors, or returns nothing usable.
    """
    candidates = list(hits)
    if not candidates:
        return []

    shown = candidates[:_MAX_CANDIDATES]
    ask = complete if complete is not None else _settings_complete
    raw: str | None = None
    try:
        raw = ask(_build_prompt(interests, shown))
    except Exception:
        logger.warning(
            "LLM suggestion generation failed; using similarity fallback.",
            exc_info=True,
        )
    else:
        parsed = _parse(raw, shown, limit=limit)
        if parsed:
            return parsed
        logger.warning(
            "LLM returned no usable suggestions; using similarity fallback. "
            "Response head: %r",
            (raw or "")[:300],
        )

    return _fallback(interests, candidates, limit=limit)


# -- prompt -------------------------------------------------------------------


def _build_prompt(
    interests: dict, shown: Sequence[tuple[ContentItem, float]]
) -> str:
    parts = [
        f"Researcher profile:\n{_profile_text(interests)}",
        "",
        "Candidate papers:",
    ]
    for index, (item, _similarity) in enumerate(shown, start=1):
        meta = item.metadata or {}
        title = _clean(meta.get("title")) or "(untitled)"
        abstract = _clean(meta.get("abstract"))[:_ABSTRACT_CHARS]
        venue = _clean(meta.get("venue"))
        year = meta.get("year") or ""
        line = f"[{index}] {title}"
        tail = ", ".join(p for p in (str(year).strip(), venue) if p)
        if tail:
            line += f" ({tail})"
        if abstract:
            line += f"\n    {abstract}"
        parts.append(line)
    parts.append(f"\nReturn the {_DEFAULT_LIMIT} best as JSON.")
    return "\n".join(parts)


def _profile_text(interests: dict) -> str:
    interests = interests or {}
    bits = []
    statement = _clean(interests.get("statement"))
    if statement:
        bits.append(statement)
    for label, key in (
        ("Research focus", "areas"),
        ("Keywords", "keywords"),
    ):
        values = _clean_list(interests.get(key))
        if values:
            bits.append(f"{label}: {', '.join(values)}")
    return "\n".join(bits) or "(no profile details)"


# -- parsing ------------------------------------------------------------------


def _parse(
    raw: str | None,
    shown: Sequence[tuple[ContentItem, float]],
    *,
    limit: int,
) -> list[Suggestion]:
    if not raw:
        return []
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        return []
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return []
    rows = data.get("suggestions") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return []

    out: list[Suggestion] = []
    seen: set[int] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        idx = _as_index(row.get("paper"), len(shown))
        if idx is None or idx in seen:
            continue
        seen.add(idx)
        item, similarity = shown[idx]
        out.append(
            _suggestion(
                item,
                similarity,
                rank=len(out) + 1,
                headline=_clean(row.get("headline")) or _title(item),
                reason=_clean(row.get("reason")) or _fallback_reason({}, item),
                source="llm",
            )
        )
        if len(out) >= limit:
            break
    return out


def _as_index(value: Any, count: int) -> int | None:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n - 1 if 1 <= n <= count else None


# -- fallback -----------------------------------------------------------------


def _fallback(
    interests: dict,
    candidates: Sequence[tuple[ContentItem, float]],
    *,
    limit: int,
) -> list[Suggestion]:
    out: list[Suggestion] = []
    for rank, (item, similarity) in enumerate(candidates[:limit], start=1):
        out.append(
            _suggestion(
                item,
                similarity,
                rank=rank,
                headline=_title(item),
                reason=_fallback_reason(interests, item),
                source="fallback",
            )
        )
    return out


def _fallback_reason(interests: dict, item: ContentItem) -> str:
    term = _overlap_term(interests, item)
    if term:
        return f"Closely matches your stated interest in {term}."
    return "A strong topical match to your research profile."


def _overlap_term(interests: dict, item: ContentItem) -> str:
    interests = interests or {}
    meta = item.metadata or {}
    haystack = f"{meta.get('title', '')} {meta.get('abstract', '')}".casefold()
    if not haystack.strip():
        return ""
    for key in ("keywords", "areas"):
        for term in _clean_list(interests.get(key)):
            if term.casefold() in haystack:
                return term
    return ""


# -- shared -------------------------------------------------------------------


def _suggestion(
    item: ContentItem,
    similarity: float,
    *,
    rank: int,
    headline: str,
    reason: str,
    source: str,
) -> Suggestion:
    return {
        "content_id": str(item.id),
        "rank": rank,
        "headline": headline,
        "reason": reason,
        "similarity": round(float(similarity), 4),
        "source": source,
    }


def _title(item: ContentItem) -> str:
    return _clean((item.metadata or {}).get("title")) or "Untitled paper"


def _settings_complete(prompt: str) -> str | None:
    from apps.core.llm import LLMMessage, build_llm_client

    client = build_llm_client()
    response = client.complete(
        [LLMMessage("system", _SYSTEM_PROMPT), LLMMessage("user", prompt)]
    )
    if response.finish_reason == "length" and not (response.content or "").strip():
        logger.warning(
            "LLM suggestion response truncated (finish_reason=length) before any "
            "answer; raise LLM_MAX_TOKENS so the model can finish."
        )
    return response.content


def _clean(value: Any) -> str:
    return " ".join(str(value).split()) if value else ""


def _clean_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _clean(item)
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            out.append(text)
    return out
