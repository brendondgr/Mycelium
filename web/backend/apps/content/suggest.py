"""Turn fused, ranked papers into a two-tier explained research digest.

Retrieval + fusion give us the papers most relevant to a researcher's interests;
this module turns that ordered candidate list into the daily digest with a
deliberate two-tier shape (a product requirement):

- **Surface the top ``surface_limit`` papers** (default 25) so the researcher sees
  the full breadth of what matched today.
- **Only the top ``llm_limit`` papers** (default 10) are sent to the language model
  for a bespoke headline, reason, and percent-match judgement. The percent match is
  *only* ever the model's — papers ranked below (the cross-embedding tail) carry a
  templated reason and **no percent** (``match_percent=None``), honest that the
  model only vetted the top slice and that the fusion score is a ranking, not a %.

The language model does the selecting and justifying for the top slice when it is
reachable; a deterministic fallback (rank by score, template the reason from
interest overlap) fills the rest and keeps the pipeline producing suggestions
offline and in CI.

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

#: Two-tier digest defaults: how many papers we surface in total, and how many of
#: those top papers the language model ranks and explains.
_DEFAULT_SURFACE_LIMIT = 25
_DEFAULT_LLM_LIMIT = 10
_ABSTRACT_CHARS = 600

_SYSTEM_PROMPT = (
    "You are Mylo, a research scout. Given a researcher's interest profile and a "
    "numbered list of candidate papers, choose the ones most worth their "
    "attention and explain why. For each pick, judge how well the paper fits "
    "THIS researcher — their statement, research focus, and keywords — and give "
    "an integer percent match from 0 to 100 (100 = a near-perfect fit; be "
    "honest and use the full range). Return ONLY one JSON object:\n"
    '  {"suggestions": [{"paper": <number>, "match": <integer 0-100>, '
    '"headline": <short title-case phrase>, "reason": <2-4 sentences, second '
    "person, that explain concretely WHY this researcher should read it, HOW it "
    'connects to their work, and WHAT they could take from it>}]}\n'
    "Rank best first. Only use papers from the list (reference them by their "
    "number). Ground every reason and match score in the paper and the profile "
    "— do not invent findings. No prose outside the JSON, no markdown fences."
)


def generate_suggestions(
    interests: dict,
    hits: Sequence[tuple[ContentItem, float]],
    *,
    llm_limit: int = _DEFAULT_LLM_LIMIT,
    surface_limit: int = _DEFAULT_SURFACE_LIMIT,
    complete: CompleteFn | None = None,
) -> list[Suggestion]:
    """Return the two-tier digest: up to ``surface_limit`` ranked suggestions.

    ``hits`` is the fused, ranked candidate list (``(ContentItem, score)``), best
    first. The top ``llm_limit`` go to the model for bespoke headlines/reasons/match
    scores; the model's picks lead (``source="llm"``). Every remaining surfaced
    paper is filled in deterministically (``source="fallback"``), preserving score
    order, up to ``surface_limit`` total. When the model is unavailable, errors, or
    returns nothing usable, the whole list is the deterministic fallback.
    """
    candidates = list(hits)
    if not candidates:
        return []

    surfaced = candidates[:surface_limit]
    llm_subset = surfaced[:llm_limit]

    llm = _llm_suggestions(interests, llm_subset, limit=llm_limit, complete=complete)
    picked = {s["content_id"] for s in llm}

    # Fill the remaining surfaced slots deterministically, in score order. This
    # also covers any of the top ``llm_limit`` the model chose to skip.
    out: list[Suggestion] = list(llm)
    for item, score in surfaced:
        if len(out) >= surface_limit:
            break
        if str(item.id) in picked:
            continue
        out.append(
            _suggestion(
                item,
                score,
                rank=len(out) + 1,
                headline=_title(item),
                reason=_fallback_reason(interests, item),
                # Cross-embedding matches carry no percent — the percent is the
                # language model's meaning judgement, and these papers never went
                # through it. (The fusion ``score`` is a ranking score, not a
                # 0-100 similarity, so scaling it would just read as "100%".)
                match_percent=None,
                source="fallback",
            )
        )

    # Renumber ranks 1..N so the LLM picks and the fallback tail form one sequence.
    for rank, suggestion in enumerate(out, start=1):
        suggestion["rank"] = rank
    return out


def _llm_suggestions(
    interests: dict,
    shown: Sequence[tuple[ContentItem, float]],
    *,
    limit: int,
    complete: CompleteFn | None,
) -> list[Suggestion]:
    """Ask the model to rank+explain ``shown``; ``[]`` if it can't be used.

    Returns the model's picks (``source="llm"``) or an empty list on any failure
    (unreachable, error, or unparseable) — the caller then fills everything with
    the deterministic fallback.
    """
    if not shown:
        return []
    ask = complete if complete is not None else _settings_complete
    try:
        raw = ask(_build_prompt(interests, shown, limit=limit))
    except Exception as exc:
        # An unreachable model is an expected degradation — one concise line, not
        # a full traceback — then fall back to the deterministic digest.
        logger.warning(
            "LLM suggestion generation unavailable (%s); using similarity fallback.",
            exc,
        )
        return []
    if not raw:
        return []  # no model / empty response — fall back quietly
    parsed = _parse(raw, shown, limit=limit)
    if not parsed:
        logger.warning(
            "LLM returned unparseable suggestions; using similarity fallback. "
            "Response head: %r",
            raw[:300],
        )
    return parsed


# -- prompt -------------------------------------------------------------------


def _build_prompt(
    interests: dict,
    shown: Sequence[tuple[ContentItem, float]],
    *,
    limit: int = _DEFAULT_LLM_LIMIT,
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
    parts.append(f"\nReturn the {limit} best as JSON.")
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
                match_percent=_as_match(row.get("match")),
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


def _as_match(value: Any) -> int | None:
    """The model's percent-match clamped to 0–100, or ``None`` if it gave none.

    The percent is *only* ever the language model's meaning judgement, so when the
    model omits or garbles the number we return ``None`` (no badge) rather than
    fabricating one from the ranking score — a researcher should never see a
    percent that the model did not actually assign.
    """
    try:
        return max(0, min(100, round(float(value))))
    except (TypeError, ValueError):
        return None


# -- fallback -----------------------------------------------------------------


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
    match_percent: int | None,
    source: str,
) -> Suggestion:
    return {
        "content_id": str(item.id),
        "rank": rank,
        "headline": headline,
        "reason": reason,
        "match_percent": match_percent,
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
