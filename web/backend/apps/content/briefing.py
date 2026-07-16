"""The cross-category "Mylo Report" daily briefing.

After the daily run has produced the day's paper suggestions and opportunity
matches, this module reads each category's :class:`RelevanceScore` feed for a user
(papers fresh-only, opportunities accumulated) across every category they watch,
rolls them into per-category counts and a small showcase of top items, and hands
the found items to the multi-agent report writer in :mod:`.briefing_agents`, which
produces a structured, sectioned **markdown** report. The result is persisted as
the user's :class:`DailyBriefing`.

The report is a small agent pipeline (see :mod:`.briefing_agents`): a Paper, Grant,
Fellowship, and Conference specialist each write a tailored ``## Section`` grounded
in that area's found items — reusing the per-item rationale already persisted on
each :class:`RelevanceScore` — and a summary agent writes the opening paragraph
over those sections. Both the sections and the summary have deterministic markdown
fallbacks, so a missing or flaky model degrades to a still-useful, honest report
(``origin`` recorded as ``fallback``) rather than nothing.
"""

from __future__ import annotations

import logging

from django.utils import timezone

from apps.content import briefing_agents
from apps.content.models import ContentItem, DailyBriefing, RelevanceScore
from apps.content.targets import target_for_user

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


def _suggested_scores(user, content_type: str) -> list[RelevanceScore]:
    """The user's suggested items of one type, read the way its feed reads them.

    Mirrors the two read models in ``views.py``:

    - **Papers** (``views._latest_scores``) are fresh-only — keep just the latest
      ``run_at`` (the freshest gather batch), pinned-first by rank.
    - **Opportunities** (``views._accumulated_scores``) accumulate — the union of
      every run's suggested rows, pinned-first then strongest match.

    Either way, rows computed but not promoted (``suggested`` false) are dropped.
    """
    scores = [
        s
        for s in RelevanceScore.objects.filter(
            target_user=user, content__type=content_type
        ).select_related("content")
        if s.signals.get("suggested")
    ]
    if not scores:
        return []
    today = timezone.now().date().isoformat()

    if content_type == ContentItem.Type.PAPER:
        latest = max(s.signals.get("run_at", "") for s in scores)
        scores = [s for s in scores if s.signals.get("run_at", "") == latest]

        def paper_key(s: RelevanceScore):
            pinned_until = s.signals.get("pinned_until")
            pinned = bool(pinned_until and pinned_until >= today)
            return (0 if pinned else 1, s.signals.get("rank") or 999)

        scores.sort(key=paper_key)
        return scores

    def opp_key(s: RelevanceScore):
        pinned_until = s.signals.get("pinned_until")
        pinned = bool(pinned_until and pinned_until >= today)
        match = s.signals.get("match_percent")
        match = match if isinstance(match, int) else -1
        return (0 if pinned else 1, -match, -s.score)

    scores.sort(key=opp_key)
    return scores


def _is_fresh(signals: dict, today: str) -> bool:
    """True only when a row is *genuinely* new: flagged ``is_new`` AND still inside
    its pin window (``pinned_until >= today``).

    ``is_new`` is a static snapshot frozen at scoring time; ``pinned_until`` (=
    first_seen + 7 days) is also frozen but is compared against *today* on read, so
    it is what actually ages an item back out of "new". The opportunity feeds
    accumulate and fellowships are effectively never pruned, so their frozen
    ``is_new=True`` rows pile up — without this gate the count reads e.g. "87 new of
    87 matched". Mirrors :func:`apps.content.views._build_summary._is_new` and
    :meth:`apps.content.serializers.…get_is_new`, the app-wide freshness rule.
    """
    if not signals.get("is_new"):
        return False
    pinned_until = signals.get("pinned_until")
    return bool(pinned_until and pinned_until >= today)


def _showcase_item(score: RelevanceScore, today: str) -> dict:
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
        "reason": signals.get("reason", ""),
        "deadline_date": signals.get("deadline_date") or "",
        "is_new": _is_fresh(signals, today),
    }


def _gather(
    user,
) -> tuple[
    list[str],
    dict[str, int],
    dict[str, int],
    dict[str, list[dict]],
    dict[str, list[dict]],
]:
    """Return (categories, counts, new_counts, showcase, report_items) per category.

    ``counts`` is everything each category's feed surfaces (papers fresh-only,
    opportunities accumulated); ``new_counts`` is the subset that is genuinely new
    right now (:func:`_is_fresh` — ``is_new`` AND still inside its pin window), the
    number the briefing leads with, so a day with 3 fresh conferences reads "3 new",
    not "140" — and an accumulated fellowship feed no longer reads "87 new of 87".

    ``showcase`` is the small top-``SHOWCASE_PER_CATEGORY`` set the UI card renders;
    ``report_items`` is a slightly larger top slice (``REPORT_ITEMS_PER_SECTION``,
    from :mod:`.briefing_agents`) the area agents write their sections from — each
    flattened item carries the per-item ``reason``/``headline`` the matcher already
    wrote, so the agents enrich real, grounded rationale rather than inventing.
    """
    categories = _watched_categories(user)
    today = timezone.now().date().isoformat()
    report_n = briefing_agents.REPORT_ITEMS_PER_SECTION
    counts: dict[str, int] = {}
    new_counts: dict[str, int] = {}
    showcase: dict[str, list[dict]] = {}
    report_items: dict[str, list[dict]] = {}
    for category in categories:
        scores = _suggested_scores(user, CATEGORY_TYPES[category])
        counts[category] = len(scores)
        new_counts[category] = sum(
            1 for s in scores if _is_fresh(s.signals, today)
        )
        flattened = [_showcase_item(s, today) for s in scores[:report_n]]
        showcase[category] = flattened[:SHOWCASE_PER_CATEGORY]
        report_items[category] = flattened
    return categories, counts, new_counts, showcase, report_items


def _profile_text(user) -> str:
    """A compact natural-language description of the researcher for the agents.

    Built from the same interest surface the matcher scores on
    (:func:`apps.content.targets.target_for_user`): the free-text research
    statement, focus areas, keywords, skills, and career stage / institution.
    """
    target = target_for_user(user)
    interests = target.interests or {}
    meta = target.profile_meta or {}
    bits: list[str] = []
    stage = _clean(meta.get("academic_title"))
    institution = _clean(meta.get("institution"))
    if stage or institution:
        bits.append(
            "Career stage / institution: "
            + " · ".join(p for p in (stage, institution) if p)
        )
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
    return "\n".join(bits)


def _clean(value) -> str:
    return " ".join(str(value).split()) if value else ""


def _clean_list(value) -> list[str]:
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


# --------------------------------------------------------------------------- #
# Report generation (multi-agent, in briefing_agents)
# --------------------------------------------------------------------------- #


def generate_briefing_for_user(
    user,
    *,
    complete: briefing_agents.CompleteFn | None = None,
) -> DailyBriefing:
    """Build and persist one user's daily report. Returns the saved row.

    Gathers the day's per-category counts and found items, then hands them to the
    multi-agent writer (:func:`apps.content.briefing_agents.generate_report_body`),
    which produces the sectioned markdown body. ``complete`` is the injectable
    ``(system, user) -> text`` LLM seam (used in tests); when it is absent, fails,
    or returns nothing usable, each agent's deterministic markdown fallback fills
    in and ``origin`` is recorded as ``fallback``.
    """
    categories, counts, new_counts, showcase, report_items = _gather(user)

    if sum(counts.values()) > 0:
        body, used_llm = briefing_agents.generate_report_body(
            _profile_text(user),
            categories,
            counts,
            new_counts,
            report_items,
            complete=complete,
        )
        origin = (
            DailyBriefing.Origin.LLM if used_llm else DailyBriefing.Origin.FALLBACK
        )
    else:
        # Empty day: an honest, populated note — no model call needed.
        body = briefing_agents.empty_report_body()
        origin = DailyBriefing.Origin.FALLBACK

    if not body:
        body = briefing_agents.empty_report_body()
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
