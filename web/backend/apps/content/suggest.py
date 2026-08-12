"""Turn fused, ranked papers into a two-tier explained research digest.

Retrieval + fusion give us the papers most relevant to a researcher's interests;
this module turns that ordered candidate list into the daily digest with a
deliberate two-tier shape (a product requirement):

- **Surface every candidate passed in** (``surface_limit=None``, the default) so the
  researcher sees the full breadth of what matched today. The caller (the pipeline)
  has already filtered the pool by the embedding-match threshold, so the surfaced
  count is variable — however many papers cleared it. An explicit ``surface_limit``
  still caps the total when a caller wants a fixed slice.
- **Only papers in the slate** (the top :func:`~apps.content.top_feed.top_n`, what
  the daily report is built from), and at most ``llm_limit`` of them per run, are
  sent to the language model for a bespoke reason and percent-match judgement. The
  percent match is *only* ever the model's — papers ranked below carry a templated
  reason and **no percent** (``match_percent=None``), honest that the model only
  vetted the slate and that the fusion score is a ranking, not a %.

The digest's **order is the fused retrieval order throughout**. A model verdict
explains an item; it never promotes one. Sorting the model-scored items above the
tail (and among themselves by the model's percent) meant the ranking a reader saw
was really "what did the model get to", which — since the budget went to whatever
had been ingested most recently — put brand-new, unrelated items at the top.

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

from django.utils import timezone

from .digest_selection import priority_first
from .models import ContentItem
from .top_feed import top_n

logger = logging.getLogger(__name__)

CompleteFn = Callable[[str], str | None]

#: A suggestion is a plain JSON-serializable dict (it lands in RelevanceScore
#: ``signals`` and the daily-report API response).
Suggestion = dict[str, Any]

#: Two-tier digest defaults: the language model ranks and explains this many of the
#: top papers. The surface total is unbounded by default (``surface_limit=None``) —
#: the pipeline decides how many papers to surface by an embedding-match threshold,
#: not a fixed count.
_DEFAULT_LLM_LIMIT = 10
_ABSTRACT_CHARS = 600

_SYSTEM_PROMPT = (
    "You are Mylo, a research scout. Given a researcher's interest profile and a "
    "numbered list of candidate papers, choose the ones most worth their "
    "attention and explain why. For each pick, judge how well the paper fits "
    "THIS researcher — their statement, research focus, and keywords — and give "
    "an integer percent match from 0 to 100 (100 = a near-perfect fit; be "
    "honest and use the full range). When a paper line names a focus cluster "
    "(\"for your <cluster> focus\"), write the reason for THAT focus — say why it "
    "matters to that specific strand of their work. Return ONLY one JSON object:\n"
    '  {"suggestions": [{"paper": <number>, "match": <integer 0-100>, '
    '"reason": <2-4 sentences, second '
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
    surface_limit: int | None = None,
    complete: CompleteFn | None = None,
    prior: dict[str, dict] | None = None,
    priority_ids: set[str] | None = None,
    cluster_by_id: dict[str, str] | None = None,
    llm_groups: Sequence[Sequence[tuple[ContentItem, float]]] | None = None,
) -> list[Suggestion]:
    """Return the two-tier digest: every candidate surfaced, the slate explained.

    ``hits`` is the fused, ranked candidate list (``(ContentItem, score)``), best
    first — already filtered by the caller (e.g. by an embedding-match threshold), so
    by default (``surface_limit=None``) *all* of them are surfaced. Passing an
    explicit ``surface_limit`` caps the total to a fixed slice.

    **The returned order is the fused order.** Retrieval — BM25 + embedding — decides
    what ranks where, and a language-model verdict only ever *annotates* the item it
    is about. The two tiers used to be sorted apart, model-scored items above the
    deterministic tail and among themselves by the model's percent; combined with
    spending the model budget on freshly-ingested items, that made "the model looked
    at this" the real ranking signal, so a bulk import led everyone's feed on the
    strength of having arrived. Rank is relevance now, and nothing else.

    Only the first :func:`~apps.content.top_feed.top_n` candidates — the slate the
    daily report is built from — are eligible for the model, and only ``llm_limit``
    of those per run. A paper further down carries a templated reason and **no
    percent** (``match_percent=None``), honest that the model never vetted it and
    that the fusion score is a ranking, not a percentage.

    ``prior`` (a prior run's LLM verdicts, keyed by content id — see
    ``apps.content.opportunity_llm.load_prior_llm_verdicts``, the opportunity twin's
    loader, reused here) carries forward papers already written up instead of
    re-sending them; the freed ``llm_limit`` slots go to slate members still
    unwritten, ``priority_ids`` (this run's slate entrants) first. This mirrors the
    selection rule in
    :func:`apps.content.opportunity_llm.generate_opportunity_suggestions` — see
    :mod:`apps.content.digest_selection` for the shared ordering helper.

    ``llm_groups`` hands the model *pre-chosen* slates instead of letting it take
    the global top ``llm_limit`` — one group per interest cluster, so a lab's every
    research theme gets its own share of the model's attention rather than losing
    the whole budget to whichever theme happens to score highest today. Each group
    is a separate call: the prompt stays short enough to answer in full, Mylo reads
    one coherent strand of work at a time, and a model failure costs one theme
    rather than the run. A paper appearing in two groups is scored once. Groups are
    intersected with the slate, so per-theme attention is preserved *within* what
    the report will actually show. Left ``None``, the slate itself is the one group.
    """
    candidates = list(hits)
    if not candidates:
        return []
    prior = prior or {}
    priority_ids = priority_ids or set()
    cluster_by_id = cluster_by_id or {}

    surfaced = candidates if surface_limit is None else candidates[:surface_limit]
    # The slate: the only part of the feed the model is ever asked about.
    slate_ids = {str(item.id) for item, _score in surfaced[: top_n()]}

    groups = [surfaced] if llm_groups is None else [list(g) for g in llm_groups]
    llm: list[Suggestion] = []
    asked: set[str] = set()
    scored_ids: set[str] = set()
    for group in groups:
        unscored = [
            pair
            for pair in group
            if str(pair[0].id) in slate_ids
            and str(pair[0].id) not in prior
            and str(pair[0].id) not in asked
        ]
        subset = priority_first(
            unscored, lambda pair: str(pair[0].id), priority_ids
        )[:llm_limit]
        if not subset:
            continue
        asked.update(str(item.id) for item, _score in subset)
        for suggestion in _llm_suggestions(
            interests, subset, limit=llm_limit, complete=complete,
            cluster_by_id=cluster_by_id,
        ):
            if suggestion["content_id"] not in scored_ids:
                scored_ids.add(suggestion["content_id"])
                llm.append(suggestion)

    now = timezone.now().isoformat()
    for suggestion in llm:
        suggestion["llm_scored_at"] = now
    fresh_by_id = {s["content_id"]: s for s in llm}

    # One pass over ``surfaced``, in fused order — each paper is whichever of the
    # three it qualifies for. The list that comes out *is* the ranking, so a paper's
    # position never depends on whether the model happened to reach it.
    out: list[Suggestion] = []
    for item, score in surfaced:
        cid = str(item.id)
        fresh = fresh_by_id.get(cid)
        if fresh is not None:
            out.append(fresh)
            continue
        verdict = prior.get(cid)
        if verdict is not None:
            suggestion = _suggestion(
                item,
                score,
                rank=0,
                # A paper's headline is always its real title — never a model rename
                # (legacy carried verdicts may still hold one; drop it here).
                headline=_title(item),
                reason=verdict.get("reason")
                or _fallback_reason(interests, item, cluster_by_id.get(cid)),
                match_percent=verdict.get("match_percent"),
                source="llm",
            )
            suggestion["llm_scored_at"] = verdict.get("llm_scored_at", "")
            out.append(suggestion)
            continue
        out.append(
            _suggestion(
                item,
                score,
                rank=0,
                headline=_title(item),
                reason=_fallback_reason(interests, item, cluster_by_id.get(cid)),
                # Cross-embedding matches carry no percent — the percent is the
                # language model's meaning judgement, and these papers never went
                # through it. (The fusion ``score`` is a ranking score, not a
                # 0-100 similarity, so scaling it would just read as "100%".)
                match_percent=None,
                source="fallback",
            )
        )

    for rank, suggestion in enumerate(out, start=1):
        suggestion["rank"] = rank
    return out


def _llm_suggestions(
    interests: dict,
    shown: Sequence[tuple[ContentItem, float]],
    *,
    limit: int,
    complete: CompleteFn | None,
    cluster_by_id: dict[str, str] | None = None,
) -> list[Suggestion]:
    """Ask the model to rank+explain ``shown``; ``[]`` if it can't be used.

    Returns the model's picks (``source="llm"``) or an empty list on any failure
    (unreachable, error, or unparseable) — the caller then fills everything with
    the deterministic fallback.
    """
    if not shown:
        return []
    cluster_by_id = cluster_by_id or {}
    ask = complete if complete is not None else _settings_complete
    try:
        raw = ask(
            _build_prompt(interests, shown, limit=limit, cluster_by_id=cluster_by_id)
        )
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
    parsed = _parse(raw, shown, limit=limit, cluster_by_id=cluster_by_id)
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
    cluster_by_id: dict[str, str] | None = None,
) -> str:
    cluster_by_id = cluster_by_id or {}
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
        cluster = cluster_by_id.get(str(item.id))
        if cluster:
            line += f" — for your {cluster} focus"
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
    cluster_by_id: dict[str, str] | None = None,
) -> list[Suggestion]:
    cluster_by_id = cluster_by_id or {}
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
                headline=_title(item),
                reason=_clean(row.get("reason"))
                or _fallback_reason({}, item, cluster_by_id.get(str(item.id))),
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


def _fallback_reason(
    interests: dict, item: ContentItem, cluster: str | None = None
) -> str:
    term = _overlap_term(interests, item)
    if cluster:
        if term:
            return (
                f"Recommended for your {cluster} focus — matches your interest "
                f"in {term}."
            )
        return f"A strong topical match for your {cluster} focus."
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

    client = build_llm_client(component="papers")
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
