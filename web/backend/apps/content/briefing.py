"""The cross-category "Mylo Report" daily briefing.

After the daily run has produced the day's paper suggestions and opportunity
matches, this module reads the latest-run :class:`RelevanceScore` rows for a user
across every category they watch (papers, grants, conferences, fellowships),
rolls them into per-category counts and a small showcase of top items, and asks
the language model to write a short, grounded 2–3 paragraph briefing over exactly
those items. The result is persisted as the user's :class:`DailyBriefing`.

Design mirrors ``suggest.py`` / ``opportunity_llm.py``:

- The synthesis is **grounded** — the prompt lists only the real showcase items,
  and the model is told to reference nothing else. The showcase we persist is the
  same set the prose talks about, so the UI can render the evidence beside it.
- There is a **deterministic fallback** — when the LLM is unreachable or returns
  nothing usable, a templated summary is written from the same counts/items and
  ``origin`` is recorded as ``fallback``, so the surface is always populated and
  honest about how it was produced.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable

from django.utils import timezone

from apps.content.models import ContentItem, DailyBriefing, RelevanceScore

logger = logging.getLogger(__name__)

#: WatchPreference.categories value -> the ContentItem type it maps to.
CATEGORY_TYPES: dict[str, str] = {
    "papers": ContentItem.Type.PAPER,
    "grants": ContentItem.Type.GRANT,
    "conferences": ContentItem.Type.CONFERENCE,
    "fellowships": ContentItem.Type.FELLOWSHIP,
}

#: How many items per category to show in the briefing showcase (bottom-right UI).
SHOWCASE_PER_CATEGORY = 3
#: How many items per category to describe to the model (a little more context).
PROMPT_ITEMS_PER_CATEGORY = 5

_SYSTEM_PROMPT = (
    "You are Mylo, the research scout for a lab-intelligence platform. You write "
    "a short daily briefing for one researcher about what today's automated scan "
    "surfaced for them: new papers, grants, conferences, and fellowships. Be warm, "
    "calm, and specific — a research operations partner, not a hype machine. "
    "LEAD with what is new since the last few days (the 'new' counts and items "
    "marked new); the older total is background, not the headline. Ground every "
    "statement ONLY in the items you are given; never invent a paper, "
    "number, or deadline. Call out the strongest matches by name, group by theme "
    "when natural, and flag any near-term deadlines. Return STRICT JSON of the form "
    '{"briefing": "<2-3 short paragraphs of plain prose>"}. No markdown, no lists.'
)


def _watched_categories(user) -> list[str]:
    """The categories this user watches, or all four when none are configured.

    ``user.watch`` is a OneToOne that is ``None`` when the user never set a watch;
    an empty ``categories`` means "not narrowed", so we show everything available.
    """
    watch = getattr(user, "watch", None)
    configured = [
        c for c in (getattr(watch, "categories", None) or []) if c in CATEGORY_TYPES
    ]
    return configured or list(CATEGORY_TYPES)


def _latest_suggested(user, content_type: str) -> list[RelevanceScore]:
    """The user's suggested items of one type from that type's latest run.

    Mirrors ``views._latest_scores``: filter by type, keep only the newest
    ``run_at``, drop rows that were computed but not promoted (``suggested``),
    then order pinned-first by rank.
    """
    scores = [
        s
        for s in RelevanceScore.objects.filter(
            target_user=user, content__type=content_type
        ).select_related("content")
    ]
    if not scores:
        return []
    latest = max(s.signals.get("run_at", "") for s in scores)
    current = [
        s
        for s in scores
        if s.signals.get("run_at", "") == latest and s.signals.get("suggested")
    ]
    today = timezone.now().date().isoformat()

    def sort_key(s: RelevanceScore):
        pinned_until = s.signals.get("pinned_until")
        pinned = bool(pinned_until and pinned_until >= today)
        return (0 if pinned else 1, s.signals.get("rank") or 999)

    current.sort(key=sort_key)
    return current


def _showcase_item(score: RelevanceScore) -> dict:
    """Flatten one score into the small display item the UI/prompt use."""
    content = score.content
    meta = content.metadata or {}
    signals = score.signals or {}
    title = meta.get("title") or meta.get("name") or "(untitled)"
    url = (
        content.source_url
        or meta.get("website")
        or meta.get("external_url")
        or meta.get("pdf_url")
        or ""
    )
    return {
        "content_id": str(content.id),
        "type": content.type,
        "title": title,
        "url": url,
        "match_percent": signals.get("match_percent"),
        "headline": signals.get("headline", ""),
        "deadline_date": signals.get("deadline_date") or "",
        "is_new": bool(signals.get("is_new")),
    }


def _gather(
    user,
) -> tuple[list[str], dict[str, int], dict[str, int], dict[str, list[dict]]]:
    """Return (watched categories, counts, new counts, showcase) per category.

    ``counts`` is everything the latest run surfaced; ``new_counts`` is the subset
    first seen within the New window (``signals.is_new``) — the number the briefing
    leads with, so a day with 3 fresh conferences reads "3 new", not "140".
    """
    categories = _watched_categories(user)
    counts: dict[str, int] = {}
    new_counts: dict[str, int] = {}
    showcase: dict[str, list[dict]] = {}
    for category in categories:
        scores = _latest_suggested(user, CATEGORY_TYPES[category])
        counts[category] = len(scores)
        new_counts[category] = sum(
            1 for s in scores if s.signals.get("is_new")
        )
        showcase[category] = [
            _showcase_item(s) for s in scores[:SHOWCASE_PER_CATEGORY]
        ]
    return categories, counts, new_counts, showcase


# --------------------------------------------------------------------------- #
# LLM synthesis + deterministic fallback
# --------------------------------------------------------------------------- #


def _build_prompt(
    counts: dict[str, int],
    new_counts: dict[str, int],
    showcase: dict[str, list[dict]],
) -> str:
    """A compact, grounded description of the day for the model."""
    lines: list[str] = ["Today's findings for this researcher:", ""]
    for category, count in counts.items():
        new = new_counts.get(category, 0)
        lines.append(
            f"{category.upper()}: {new} new this week, {count} matched in total."
        )
        for item in showcase.get(category, [])[:PROMPT_ITEMS_PER_CATEGORY]:
            bits = [f'  - "{item["title"]}"']
            if isinstance(item.get("match_percent"), int):
                bits.append(f"{item['match_percent']}% match")
            if item.get("deadline_date"):
                bits.append(f"deadline {item['deadline_date']}")
            if item.get("is_new"):
                bits.append("new")
            lines.append(" — ".join(bits))
        lines.append("")
    lines.append(
        "Write the briefing now. Lead with what is NEW, mention the counts, name "
        "the standout items, and flag near-term deadlines. Reference only the "
        "items above."
    )
    return "\n".join(lines)


def _parse_briefing(raw: str | None) -> str:
    """Pull the ``briefing`` string out of the model's JSON, tolerantly.

    Falls back to the raw text (stripped) when the model answered with prose
    instead of clean JSON — still the model's words, still grounded.
    """
    if not raw or not raw.strip():
        return ""
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            data = json.loads(raw[start : end + 1])
            text = data.get("briefing")
            if isinstance(text, str) and text.strip():
                return text.strip()
        except (json.JSONDecodeError, AttributeError):
            pass
    return raw.strip()


def _settings_complete(prompt: str) -> str | None:
    """Default completion: send the prompt through the configured LLM client."""
    from apps.core.llm import LLMMessage, build_llm_client

    client = build_llm_client()
    response = client.complete(
        [LLMMessage("system", _SYSTEM_PROMPT), LLMMessage("user", prompt)]
    )
    if response.finish_reason == "length" and not (response.content or "").strip():
        logger.warning(
            "LLM briefing response truncated (finish_reason=length) before any "
            "answer; raise LLM_MAX_TOKENS so the model can finish."
        )
    return response.content


def _fallback_body(
    counts: dict[str, int],
    new_counts: dict[str, int],
    showcase: dict[str, list[dict]],
) -> str:
    """A deterministic briefing when the model is unavailable or empty."""
    total = sum(counts.values())
    if total == 0:
        return (
            "No new research matched your profile today. Mylo will keep scanning "
            "your watched topics and surface fresh papers and opportunities here "
            "as they appear."
        )
    # Lead with what's fresh; the running total is the parenthetical, not the news.
    def _noun(category: str, n: int) -> str:
        return _singular(category) if n == 1 else category

    parts = [
        f"{new} new {_noun(category, new)} ({count} matched in total)"
        if (new := new_counts.get(category, 0))
        else f"{count} {_noun(category, count)}"
        for category, count in counts.items()
        if count
    ]
    lead = "Today Mylo surfaced " + _join_english(parts) + " for you."

    highlights: list[str] = []
    for category, items in showcase.items():
        if not items:
            continue
        top = items[0]
        match = top.get("match_percent")
        match_str = f" ({match}% match)" if isinstance(match, int) else ""
        highlights.append(f'the {_singular(category)} "{top["title"]}"{match_str}')
    highlight_line = (
        " Standouts include " + _join_english(highlights) + "." if highlights else ""
    )

    deadlines = [
        f'"{item["title"]}" ({item["deadline_date"]})'
        for items in showcase.values()
        for item in items
        if item.get("deadline_date")
    ]
    deadline_line = (
        " Watch these deadlines: " + _join_english(deadlines[:3]) + "."
        if deadlines
        else ""
    )
    return lead + highlight_line + deadline_line


def _join_english(parts: list[str]) -> str:
    """Join a list as 'a', 'a and b', or 'a, b, and c'."""
    parts = [p for p in parts if p]
    if not parts:
        return "nothing"
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return ", ".join(parts[:-1]) + f", and {parts[-1]}"


def _singular(category: str) -> str:
    return {
        "papers": "paper",
        "grants": "grant",
        "conferences": "conference",
        "fellowships": "fellowship",
    }.get(category, category)


def generate_briefing_for_user(
    user,
    *,
    complete: Callable[[str], str | None] | None = None,
) -> DailyBriefing:
    """Build and persist one user's daily briefing. Returns the saved row.

    ``complete`` is the prompt->text seam (injected in tests). When it is absent,
    fails, or returns nothing usable, the deterministic fallback writes the body
    and ``origin`` is recorded as ``fallback``.
    """
    categories, counts, new_counts, showcase = _gather(user)
    ask = complete if complete is not None else _settings_complete

    body = ""
    origin = DailyBriefing.Origin.FALLBACK
    if sum(counts.values()) > 0:
        try:
            raw = ask(_build_prompt(counts, new_counts, showcase))
        except Exception as exc:  # noqa: BLE001 — any LLM failure => fallback
            logger.warning(
                "LLM briefing generation unavailable (%s); using deterministic "
                "fallback for %s.",
                exc,
                user,
            )
            raw = None
        parsed = _parse_briefing(raw)
        if parsed:
            body = parsed
            origin = DailyBriefing.Origin.LLM

    if not body:
        body = _fallback_body(counts, new_counts, showcase)
        origin = DailyBriefing.Origin.FALLBACK

    briefing, _ = DailyBriefing.objects.update_or_create(
        user=user,
        defaults={
            "body": body,
            "origin": origin,
            "categories": categories,
            "counts": counts,
            "new_counts": new_counts,
            "showcase": showcase,
        },
    )
    return briefing
