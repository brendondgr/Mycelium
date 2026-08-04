"""Language-model scoring for grant & conference opportunities.

The opportunity twin of :mod:`apps.content.suggest`. Retrieval + fusion give the
opportunities most relevant to a researcher; this turns the top slice into the
percent-match + reason the UI leads with, using an area-aware judgement ported
from the ProQuest tool's multi-agent evaluator:

- **Grants** are judged on scope alignment *and* eligibility — "can this specific
  researcher (career stage, institution) plausibly apply?" — the tool's two grant
  specialists, folded into one call.
- **Conferences** are judged on topic & track fit.
- **Fellowships** are judged on research/interest fit *after* the deterministic
  eligibility rule engine (:mod:`.fellowships`) has already gated them — the model
  never re-litigates eligibility; :func:`generate_fellowship_suggestions` overlays
  its report onto the rule engine's eligible, fit-ranked list.

Same contract as the paper digest: a two-tier list (the top ``llm_limit`` get a
model percent + bespoke reason, ``source="llm"``; the rest are deterministic
fallback with ``match_percent=None``), an injectable ``complete`` seam, a tolerant
JSON parser, and a fallback that never raises — so a missing/flaky model degrades
to a still-useful, honestly-unscored list rather than nothing.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Sequence
from typing import Any

from django.utils import timezone

from .digest_selection import new_first
from .models import ContentItem, RelevanceScore

logger = logging.getLogger(__name__)

CompleteFn = Callable[[str], str | None]
Suggestion = dict[str, Any]

_DEFAULT_LLM_LIMIT = 10
_TEXT_CHARS = 900

_JSON_SHAPE = (
    'Return ONLY one JSON object:\n'
    '  {"suggestions": [{"item": <number>, "match": <integer 0-100>, '
    '"headline": <short title-case phrase>, "reason": <2-4 sentences, second '
    "person, that explain concretely WHY this fits the researcher, HOW their "
    "specific research and methods align with it, and WHAT they could pursue or "
    'use it for — not a single generic line>}]}\n'
    "Rank best first. Only use items from the list (reference them by number). "
    "Ground every reason and match score in the item and the profile — do not "
    "invent details. No prose outside the JSON, no markdown fences."
)

_SYSTEM_PROMPT = {
    ContentItem.Type.GRANT: (
        "You are Mylo, a research funding scout. Given a researcher's profile and a "
        "numbered list of funding opportunities, pick the ones most worth their "
        "attention. Judge each on BOTH scope alignment (topic/method/domain fit) "
        "AND eligibility — whether THIS researcher, at their career stage and "
        "institution, could plausibly apply and win (a student may need a faculty "
        "PI). Give an integer percent match 0-100 that reflects overall fit and "
        "eligibility (100 = a near-perfect, clearly-eligible fit; be honest and use "
        "the full range). " + _JSON_SHAPE
    ),
    ContentItem.Type.CONFERENCE: (
        "You are Mylo, a research conference scout. Given a researcher's profile and "
        "a numbered list of conferences / calls for papers, pick the ones most worth "
        "their attention. Judge each on topic & track fit — whether the researcher's "
        "work belongs in this venue's scope and submission tracks. Give an integer "
        "percent match 0-100 (100 = a near-perfect venue; be honest and use the full "
        "range). " + _JSON_SHAPE
    ),
    ContentItem.Type.FELLOWSHIP: (
        "You are Mylo, a research fellowship scout. The researcher has ALREADY "
        "passed each fellowship's hard eligibility gates (citizenship, academic "
        "stage, institutional and demographic restrictions), so do NOT re-litigate "
        "eligibility or lead with it. Judge each fellowship on how well it fits "
        "THIS researcher's specific research topics, methods, career trajectory, "
        "and goals, and pick the ones most worth their attention. Give an integer "
        "percent match 0-100 that reflects research/interest fit (100 = a "
        "near-perfect fit; be honest and use the full range). " + _JSON_SHAPE
    ),
}


def load_prior_llm_verdicts(persist_kwargs: dict, content_type: str) -> dict[str, dict]:
    """Prior-run LLM verdicts for ``persist_kwargs``'s target, keyed by content id.

    The carry-forward store: :class:`~apps.content.models.RelevanceScore` rows
    persist across nightly runs (only the *read* layer filters to the latest
    ``run_at``), so a row from any earlier run whose signals show it was actually
    scored by the model (``source == "llm"``, a real ``match_percent``) is a
    verdict already paid for. The caller skips sending that item back to the model
    and reuses this dict's headline/reason/match_percent instead. Missing or
    malformed signals are silently skipped — degrade, don't crash.
    """
    rows = RelevanceScore.objects.filter(
        **persist_kwargs, content__type=content_type
    ).only("content_id", "signals")
    out: dict[str, dict] = {}
    for row in rows:
        signals = row.signals or {}
        if signals.get("source") != "llm":
            continue
        match_percent = signals.get("match_percent")
        if match_percent is None:
            continue
        out[str(row.content_id)] = {
            "match_percent": match_percent,
            "headline": signals.get("headline", ""),
            "reason": signals.get("reason", ""),
            "llm_scored_at": signals.get("llm_scored_at")
            or signals.get("run_at")
            or "",
        }
    return out


def generate_opportunity_suggestions(
    area: str,
    interests: dict,
    profile_meta: dict,
    hits: Sequence[tuple[ContentItem, float]],
    *,
    llm_limit: int = _DEFAULT_LLM_LIMIT,
    surface_limit: int | None = None,
    complete: CompleteFn | None = None,
    prior: dict[str, dict] | None = None,
    new_ids: set[str] | None = None,
) -> list[Suggestion]:
    """Two-tier opportunity digest: model-scored top slice + deterministic tail.

    ``hits`` is the fused, ranked candidate list — the caller (the matcher) may have
    already filtered it by the area's match threshold, so by default
    (``surface_limit=None``) every candidate is surfaced and only the top
    ``llm_limit`` go to the model. An explicit ``surface_limit`` caps the total to a
    fixed slice (the legacy top-N behaviour).

    ``prior`` (from :func:`load_prior_llm_verdicts`) carries forward verdicts a
    previous run already got from the model — those items are never re-sent; this
    run's ``llm_limit`` slots go entirely to items still unscored, preferring ones
    in ``new_ids`` (freshly-seen this week) over older backlog items. LLM-scored
    suggestions (fresh + carried) are ordered by match percent (ties: fused order);
    the fallback tail keeps fused order.
    """
    candidates = list(hits)
    if not candidates:
        return []
    prior = prior or {}
    new_ids = new_ids or set()

    surfaced = candidates if surface_limit is None else candidates[:surface_limit]

    unscored = [pair for pair in surfaced if str(pair[0].id) not in prior]
    llm_subset = new_first(unscored, lambda pair: str(pair[0].id), new_ids)[:llm_limit]

    fresh = _llm_suggestions(
        area, interests, profile_meta, llm_subset, limit=llm_limit, complete=complete
    )
    now = timezone.now().isoformat()
    for suggestion in fresh:
        suggestion["llm_scored_at"] = now
    fresh_ids = {s["content_id"] for s in fresh}

    carried: list[Suggestion] = []
    for item, score in surfaced:
        cid = str(item.id)
        if cid in fresh_ids:
            continue
        verdict = prior.get(cid)
        if verdict is None:
            continue
        suggestion = _suggestion(
            item,
            score,
            rank=0,
            headline=verdict.get("headline") or _title(item),
            reason=verdict.get("reason") or _fallback_reason(interests, item),
            match_percent=verdict.get("match_percent"),
            source="llm",
        )
        suggestion["llm_scored_at"] = verdict.get("llm_scored_at", "")
        carried.append(suggestion)

    scored = fresh + carried
    scored_ids = fresh_ids | {s["content_id"] for s in carried}

    # ``surfaced`` is the final set (all candidates, or the ``surface_limit`` slice);
    # every item is either scored (fresh/carried, above) or falls through here.
    fallback: list[Suggestion] = []
    for item, score in surfaced:
        if str(item.id) in scored_ids:
            continue
        fallback.append(
            _suggestion(
                item,
                score,
                rank=0,
                headline=_title(item),
                reason=_fallback_reason(interests, item),
                match_percent=None,
                source="fallback",
            )
        )

    fused_order = {str(item.id): i for i, (item, _score) in enumerate(surfaced)}
    scored.sort(
        key=lambda s: (-(s["match_percent"] or 0), fused_order.get(s["content_id"], 0))
    )

    out = scored + fallback
    for rank, suggestion in enumerate(out, start=1):
        suggestion["rank"] = rank
    return out


def generate_fellowship_suggestions(
    interests: dict,
    profile_meta: dict,
    ranked: Sequence[Suggestion],
    items_by_id: dict[str, ContentItem],
    *,
    llm_limit: int = _DEFAULT_LLM_LIMIT,
    complete: CompleteFn | None = None,
    prior: dict[str, dict] | None = None,
    new_ids: set[str] | None = None,
) -> list[Suggestion]:
    """Overlay a model-written report onto the top slice of the eligible list.

    ``ranked`` is the deterministic rule engine's eligibility-gated, fit-ranked
    output (each dict from :func:`apps.content.fellowships.match_fellowships`, with
    ``source="rules"``). Eligibility is already decided; this only enriches *why
    it fits the person's research*: the top ``llm_limit`` of the items ``prior``
    hasn't already scored (new ones first, per ``new_ids``) go to the fellowship
    model for a bespoke 2-4 sentence reason + percent match. Items ``prior`` already
    scored keep that verdict without a fresh model call. Either way the overlay
    (``source`` becomes ``"llm"``) preserves the eligibility fields
    (``tier``/``gates_failed``/``reasons``/``fit``/status). When the model is
    unavailable and there is no prior verdict, the rule reason survives unchanged,
    so nothing regresses. Output order always follows ``ranked`` (the rule engine's
    tier/fit order) — only which items got a *fresh* model call changes.
    """
    if not ranked:
        return []
    prior = prior or {}
    new_ids = new_ids or set()

    unscored = [s for s in ranked if s["content_id"] not in prior]
    top = new_first(unscored, lambda s: s["content_id"], new_ids)[:llm_limit]
    pairs = [
        (items_by_id[s["content_id"]], float(s.get("fit", 0.0)))
        for s in top
        if s.get("content_id") in items_by_id
    ]
    llm = _llm_suggestions(
        ContentItem.Type.FELLOWSHIP,
        interests,
        profile_meta,
        pairs,
        limit=llm_limit,
        complete=complete,
    )
    now = timezone.now().isoformat()
    for suggestion in llm:
        suggestion["llm_scored_at"] = now
    by_id = {s["content_id"]: s for s in llm}

    out: list[Suggestion] = []
    for suggestion in ranked:
        cid = suggestion["content_id"]
        enriched = by_id.get(cid)
        if enriched is not None:
            # Keep the eligibility verdict; take the model's fresh headline/reason.
            merged = {
                **suggestion,
                "headline": enriched["headline"],
                "reason": enriched["reason"],
                "source": "llm",
                "llm_scored_at": enriched.get("llm_scored_at", now),
            }
            if _usable_percent(enriched.get("match_percent")):
                merged["match_percent"] = enriched["match_percent"]
            out.append(merged)
            continue
        verdict = prior.get(cid)
        if verdict is not None:
            merged = {
                **suggestion,
                "headline": verdict.get("headline") or suggestion["headline"],
                "reason": verdict.get("reason") or suggestion["reason"],
                "source": "llm",
                "llm_scored_at": verdict.get("llm_scored_at", ""),
            }
            if _usable_percent(verdict.get("match_percent")):
                merged["match_percent"] = verdict["match_percent"]
            out.append(merged)
            continue
        out.append(suggestion)
    return out


def _usable_percent(value) -> bool:
    """True when a model-supplied fellowship percent should override the computed one.

    A fellowship arrives here already carrying a real ``match_percent`` — the
    researcher's embedding cosine to the item, computed by the retrieve/fuse step.
    The model's job in this overlay is the *written report*, not the number, so a
    missing or zero percent (the model omitted it, or the parse fell back to 0)
    must not overwrite a measured 48% match with 0 and drop the item under the feed's
    match-percent floor. Any positive number is taken as a genuine verdict.
    """
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def _llm_suggestions(
    area: str,
    interests: dict,
    profile_meta: dict,
    shown: Sequence[tuple[ContentItem, float]],
    *,
    limit: int,
    complete: CompleteFn | None,
) -> list[Suggestion]:
    if not shown:
        return []
    ask = complete if complete is not None else _settings_complete(area)
    try:
        raw = ask(_build_prompt(area, interests, profile_meta, shown, limit=limit))
    except Exception as exc:
        # A missing/unreachable model is an expected degradation (e.g. the vLLM
        # endpoint is down), so log one concise line — not a full traceback per
        # user/area — and fall back to deterministic scoring.
        logger.warning("LLM opportunity scoring unavailable (%s); using fallback.", exc)
        return []
    if not raw:
        return []  # no model / empty response — fall back quietly
    parsed = _parse(raw, shown, limit=limit)
    if not parsed:
        logger.warning(
            "LLM returned unparseable opportunity scores; using fallback. Head: %r",
            raw[:300],
        )
    return parsed


# -- prompt -------------------------------------------------------------------


def _build_prompt(
    area: str,
    interests: dict,
    profile_meta: dict,
    shown: Sequence[tuple[ContentItem, float]],
    *,
    limit: int,
) -> str:
    parts = [
        f"Researcher profile:\n{_profile_text(interests, profile_meta)}",
        "",
        "Candidate opportunities:",
    ]
    for index, (item, _score) in enumerate(shown, start=1):
        parts.append(_candidate_brief(area, index, item))
    parts.append(f"\nReturn the {limit} best as JSON.")
    return "\n".join(parts)


def _profile_text(interests: dict, profile_meta: dict) -> str:
    interests = interests or {}
    profile_meta = profile_meta or {}
    bits = []
    stage = _clean(profile_meta.get("academic_title"))
    institution = _clean(profile_meta.get("institution"))
    if stage or institution:
        who = " · ".join(p for p in (stage, institution) if p)
        bits.append(f"Career stage / institution: {who}")
    statement = _clean(interests.get("statement"))
    if statement:
        bits.append(statement)
    for label, key in (
        ("Research focus", "areas"),
        ("Keywords", "keywords"),
        ("Skills", "skills"),
        ("Funding needs", "funding_needs"),
    ):
        values = _clean_list(interests.get(key))
        if values:
            bits.append(f"{label}: {', '.join(values)}")
    return "\n".join(bits) or "(no profile details)"


def _candidate_brief(area: str, index: int, item: ContentItem) -> str:
    meta = item.metadata or {}
    if area == ContentItem.Type.GRANT:
        line = f"[{index}] {_clean(meta.get('title')) or '(untitled grant)'}"
        tail = ", ".join(
            p for p in (_clean(meta.get("sponsor")), _clean(meta.get("amount"))) if p
        )
        if tail:
            line += f" — {tail}"
        if meta.get("deadline_date"):
            line += f" (deadline {meta['deadline_date']})"
        body = _clean(meta.get("abstract")) or _clean(meta.get("ai_summary"))
        if body:
            line += f"\n    {body[:_TEXT_CHARS]}"
        topics = _clean(meta.get("matched_topics"))
        if topics:
            line += f"\n    Topics: {topics}"
        return line

    if area == ContentItem.Type.FELLOWSHIP:
        line = f"[{index}] {_clean(meta.get('title')) or '(untitled fellowship)'}"
        tail = ", ".join(
            p
            for p in (_clean(meta.get("award_class")), _clean(meta.get("amount_raw")))
            if p
        )
        if tail:
            line += f" — {tail}"
        deadline = meta.get("deadline") or {}
        if deadline.get("date"):
            line += f" (deadline {deadline['date']})"
        body = _clean(meta.get("description")) or _clean(meta.get("blurb"))
        if body:
            line += f"\n    {body[:_TEXT_CHARS]}"
        facets = meta.get("facets") or {}
        fields = ", ".join(_clean_list(facets.get("field")))
        if fields:
            line += f"\n    Fields: {fields}"
        stages = ", ".join(_clean_list(facets.get("stage")))
        if stages:
            line += f"\n    Stage: {stages}"
        elig = meta.get("eligibility")
        if isinstance(elig, list) and elig:
            elig_text = "; ".join(_clean_list(elig))
            if elig_text:
                line += f"\n    Eligibility: {elig_text[:_TEXT_CHARS]}"
        return line

    # conference
    line = f"[{index}] {_clean(meta.get('name')) or '(untitled conference)'}"
    where = ", ".join(
        p for p in (_clean(meta.get("location")), _clean(meta.get("country"))) if p
    )
    if where:
        line += f" — {where}"
    if meta.get("event_date"):
        line += f" (event {meta['event_date']})"
    scope = _clean(meta.get("scope"))
    if scope:
        line += f"\n    {scope[:_TEXT_CHARS]}"
    kws = _clean(meta.get("keywords"))
    if kws:
        line += f"\n    Keywords: {kws}"
    return line


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
        idx = _as_index(row.get("item"), len(shown))
        if idx is None or idx in seen:
            continue
        seen.add(idx)
        item, score = shown[idx]
        out.append(
            _suggestion(
                item,
                score,
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
    try:
        return max(0, min(100, round(float(value))))
    except (TypeError, ValueError):
        return None


# -- fallback & shared --------------------------------------------------------


def _fallback_reason(interests: dict, item: ContentItem) -> str:
    term = _overlap_term(interests, item)
    if term:
        return f"Closely matches your stated interest in {term}."
    return "A strong topical match to your research profile."


def _overlap_term(interests: dict, item: ContentItem) -> str:
    interests = interests or {}
    haystack = str((item.metadata or {}).get("search_text", "")).casefold()
    if not haystack.strip():
        return ""
    for key in ("keywords", "areas"):
        for term in _clean_list(interests.get(key)):
            if term.casefold() in haystack:
                return term
    return ""


def _suggestion(
    item: ContentItem,
    score: float,
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
        "similarity": round(float(score), 4),
        "source": source,
    }


def _title(item: ContentItem) -> str:
    meta = item.metadata or {}
    return _clean(meta.get("title")) or _clean(meta.get("name")) or "Untitled"


def _settings_complete(area: str) -> CompleteFn:
    def _complete(prompt: str) -> str | None:
        from apps.core.llm import LLMMessage, build_llm_client

        client = build_llm_client()
        response = client.complete(
            [LLMMessage("system", _SYSTEM_PROMPT[area]), LLMMessage("user", prompt)]
        )
        if response.finish_reason == "length" and not (response.content or "").strip():
            logger.warning(
                "LLM opportunity response truncated (finish_reason=length); raise "
                "LLM_MAX_TOKENS so the model can finish."
            )
        return response.content

    return _complete


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
