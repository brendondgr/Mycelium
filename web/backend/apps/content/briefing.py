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
from apps.content.targets import target_for_lab, target_for_user

logger = logging.getLogger(__name__)

#: WatchPreference.categories value -> the ContentItem type it maps to.
CATEGORY_TYPES: dict[str, str] = {
    "papers": ContentItem.Type.PAPER,
    "grants": ContentItem.Type.GRANT,
    "conferences": ContentItem.Type.CONFERENCE,
    "fellowships": ContentItem.Type.FELLOWSHIP,
}

#: The categories a lab briefing can cover. Labs are scored for papers/grants/
#: conferences; fellowships stay user-only (they surface for a lab only as a
#: consented union of member matches, handled on the overview — never in prose).
LAB_BRIEFING_CATEGORIES: tuple[str, ...] = ("papers", "grants", "conferences")

#: How many items per category to show in the briefing showcase (bottom-right UI).
SHOWCASE_PER_CATEGORY = 3


def _watched_categories(watch, allow: tuple[str, ...] | None = None) -> list[str]:
    """The categories a target watches, or all available when none are configured.

    ``watch`` is the target's ``WatchPreference``/``LabWatchPreference`` (or ``None``
    when never set); an empty ``categories`` means "not narrowed", so we show
    everything available. ``allow`` optionally restricts the universe — a lab, for
    instance, only ever brief on the categories it is scored for.
    """
    universe = list(allow) if allow is not None else list(CATEGORY_TYPES)
    configured = [
        c for c in (getattr(watch, "categories", None) or []) if c in universe
    ]
    return configured or universe


def _suggested_scores(target_filter: dict, content_type: str) -> list[RelevanceScore]:
    """A target's suggested items of one type, read the way its feed reads them.

    ``target_filter`` is the single ``target_*`` FK to read under —
    ``{"target_user": user}`` for a person, ``{"target_lab": lab}`` for a lab.
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
            **target_filter, content__type=content_type
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


def _is_new_today(signals: dict, today: str) -> bool:
    """True only when a row was *first seen on the run date* — new since yesterday.

    The daily report answers "what surfaced today", so an item counts as new only
    when its immutable ``first_seen`` date equals ``today`` (the run date). This is
    deliberately stricter than the feed's "New" badge, which pins a fresh item for a
    week (``is_new`` AND ``pinned_until >= today`` — see
    :func:`apps.content.views._build_summary._is_new` and
    :meth:`apps.content.serializers.…get_is_new`). Using the pin window here made the
    report re-announce the same set every day for a week: the opportunity feeds
    accumulate and fellowships are effectively never pruned, so a one-time bulk
    import of 78 eligible fellowships read "78 new" every day until the pins expired.
    Anchoring on the first-seen date instead means each item is announced once, the
    day it actually arrives.

    ``first_seen`` is stored on every suggested row (opportunities carry the
    immutable ``metadata.first_seen``; papers fall back to the ingest date), as a
    full ISO datetime or a bare ISO date — comparing the first 10 chars handles both.
    """
    first_seen = signals.get("first_seen")
    return bool(first_seen) and str(first_seen)[:10] == today


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
        "is_new": _is_new_today(signals, today),
    }


def _gather(
    target_filter: dict,
    watch,
    allow: tuple[str, ...] | None = None,
) -> tuple[
    list[str],
    dict[str, int],
    dict[str, int],
    dict[str, list[dict]],
    dict[str, list[dict]],
]:
    """Return (categories, counts, new_counts, showcase, report_items) per category.

    ``counts`` is everything each category's feed surfaces (papers fresh-only,
    opportunities accumulated); ``new_counts`` is the subset that first surfaced on
    the run date (:func:`_is_new_today`), the number the briefing leads with, so a
    day with 3 fresh conferences reads "3 new", not "140" — and an accumulated,
    never-pruned fellowship feed no longer re-announces the same set as "new" every
    day of its week-long pin window.

    ``showcase`` is the small top-``SHOWCASE_PER_CATEGORY`` set the UI card renders;
    ``report_items`` is a slightly larger top slice (``REPORT_ITEMS_PER_SECTION``,
    from :mod:`.briefing_agents`) the area agents write their sections from — each
    flattened item carries the per-item ``reason``/``headline`` the matcher already
    wrote, so the agents enrich real, grounded rationale rather than inventing.
    """
    categories = _watched_categories(watch, allow)
    today = timezone.now().date().isoformat()
    report_n = briefing_agents.REPORT_ITEMS_PER_SECTION
    counts: dict[str, int] = {}
    new_counts: dict[str, int] = {}
    showcase: dict[str, list[dict]] = {}
    report_items: dict[str, list[dict]] = {}
    for category in categories:
        scores = _suggested_scores(target_filter, CATEGORY_TYPES[category])
        counts[category] = len(scores)
        new_counts[category] = sum(
            1 for s in scores if _is_new_today(s.signals, today)
        )
        flattened = [_showcase_item(s, today) for s in scores[:report_n]]
        showcase[category] = flattened[:SHOWCASE_PER_CATEGORY]
        report_items[category] = flattened
    return categories, counts, new_counts, showcase, report_items


def _profile_text(target) -> str:
    """A compact natural-language description of the target for the agents.

    Built from the same interest surface the matcher scores on (a
    :class:`apps.content.targets.MatchTarget`): the free-text research statement,
    focus areas, keywords, skills, and (for a person) career stage / institution.
    A lab target simply carries no ``profile_meta``, so those lines are omitted.
    """
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


def _write_briefing(
    *,
    owner: dict,
    target,
    target_filter: dict,
    watch,
    allow: tuple[str, ...] | None = None,
    complete: briefing_agents.CompleteFn | None = None,
) -> DailyBriefing:
    """Gather a target's day, write the report, and persist it as a ``DailyBriefing``.

    ``owner`` is the update-or-create key (``{"user": user}`` or ``{"lab": lab}``);
    ``target`` is the :class:`MatchTarget` the prose is grounded in; ``target_filter``
    is the ``target_*`` FK the scores are read under. Shared by the user and lab
    entry points so both apply the same gather + fallback rules.
    """
    categories, counts, new_counts, showcase, report_items = _gather(
        target_filter, watch, allow
    )

    if sum(counts.values()) > 0:
        body, used_llm = briefing_agents.generate_report_body(
            _profile_text(target),
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
        **owner,
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
    return _write_briefing(
        owner={"user": user},
        target=target_for_user(user),
        target_filter={"target_user": user},
        watch=getattr(user, "watch", None),
        complete=complete,
    )


def generate_briefing_for_lab(
    lab,
    *,
    complete: briefing_agents.CompleteFn | None = None,
) -> DailyBriefing:
    """Build and persist a lab's daily report over its aggregate matches.

    Same shape as the personal briefing, but grounded in the lab's shared interest
    profile (:func:`apps.content.targets.target_for_lab`) and its ``target_lab``
    scores, and limited to the categories a lab is scored for
    (:data:`LAB_BRIEFING_CATEGORIES` — fellowships stay user-only). The row is keyed
    on the lab, so a lab's briefing is distinct from any member's own.
    """
    return _write_briefing(
        owner={"lab": lab},
        target=target_for_lab(lab),
        target_filter={"target_lab": lab},
        watch=getattr(lab, "watch", None),
        allow=LAB_BRIEFING_CATEGORIES,
        complete=complete,
    )
