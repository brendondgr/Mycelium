"""The cross-category "Mylo Report" daily briefing.

After the daily run has produced the day's paper suggestions and opportunity
matches, this module reads each category's :class:`RelevanceScore` feed for a user
(papers fresh-only, opportunities accumulated) across every category they watch,
rolls them into per-category counts and a small showcase of top items, and hands
the found items to the sectioned report writer in :mod:`.briefing_sections`, which
produces a structured, sectioned **markdown** report. The result is persisted as
that day's :class:`DailyBriefing` — one row per target per ``generated_on``, so a
rerun replaces today's report and the previous days stay readable.

The report is organised the way a researcher's work is: a **Personal** part over
the reader's own matches, then one part per **project** they are on — an individual
project they own, or a lab project a PI assigned them to. Each part is broken down
by category (papers, grants, fellowships, conferences), and the report opens with a
project × category table of what is new today. A lab's report is the same document
over the lab's aggregate matches and the lab's own projects.

What may appear in the report is deliberately narrower than what the feeds hold
(:func:`report_scores`): a feed accumulates everything that ever cleared its
category's threshold, while the report answers "what arrived today, and is it worth
your attention" — so a row must have *first surfaced today* and its search
relevance must clear :data:`REPORT_RELEVANCE_FALLBACK` (settings
``REPORT_RELEVANCE_THRESHOLD``). When nothing clears the bar the report says so
rather than padding itself out.

The Personal part is a fan-out of prompts (see :mod:`.briefing_sections`): one
per-category section prompt — Paper, Grant, Fellowship, and Conference — each
writing a tailored section grounded in that area's found items and reusing the
per-item rationale already persisted on each :class:`RelevanceScore`, plus one
prompt for the opening paragraph. Project parts are written deterministically from
those same persisted rationales, so the daily model cost stays flat no matter how
many projects a reader is on. Every stage has a deterministic markdown fallback, so
a missing or flaky model degrades to a still-useful, honest report (``origin``
recorded as ``fallback``) rather than nothing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.content import briefing_sections
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

#: The categories a lab briefing can cover — all four. A lab is now scored for
#: fellowships in its own right (ranked on research fit, no eligibility gate), so
#: its report covers the same ground its feeds do. Who each item suits is named
#: from the stored member-fit layer, never re-derived in prose.
LAB_BRIEFING_CATEGORIES: tuple[str, ...] = (
    "papers",
    "grants",
    "conferences",
    "fellowships",
)

#: How many items per category to show in the briefing showcase (bottom-right UI).
SHOWCASE_PER_CATEGORY = 3

#: Report relevance floor used when ``settings.REPORT_RELEVANCE_THRESHOLD`` is
#: absent (bare test configs). See that setting for what it gates and why.
REPORT_RELEVANCE_FALLBACK = 0.65


def report_relevance_threshold() -> float:
    """The report's relevance floor, as a cosine fraction in ``[0, 1]``."""
    return getattr(settings, "REPORT_RELEVANCE_THRESHOLD", REPORT_RELEVANCE_FALLBACK)


def relevance_of(signals: dict) -> float | None:
    """A row's search relevance in ``[0, 1]``, or ``None`` when it has no signal.

    ``embedding_match`` is the raw cosine the matcher recorded for the row and is
    the signal the threshold is expressed in. Rows matched without an embedder (a
    rule-only fellowship, an older row) carry no cosine; their model-assigned
    ``match_percent`` stands in, on the same 0-1 scale. A row with neither has
    nothing to judge relevance by, so it returns ``None`` and the report leaves it
    out rather than assuming it is good.
    """
    match = signals.get("embedding_match")
    if isinstance(match, (int, float)) and not isinstance(match, bool):
        return float(match)
    percent = signals.get("match_percent")
    if isinstance(percent, (int, float)) and not isinstance(percent, bool):
        return float(percent) / 100.0
    return None


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


def report_scores(
    target_filter: dict,
    content_type: str,
    today: str,
    *,
    threshold: float | None = None,
) -> list[RelevanceScore]:
    """The suggested rows a *report* may show: new today, and relevant enough.

    Two narrowings on top of :func:`_suggested_scores`, and both matter:

    - **New today** (:func:`_is_new_today`). The opportunity feeds accumulate and
      fellowships are effectively never pruned, so "everything currently matched"
      is a standing backlog, not a day's news. A report that lists it re-announces
      the same items every morning.
    - **Above the relevance floor** (:func:`relevance_of` against
      :func:`report_relevance_threshold`). A feed page is browsable and can afford
      the long tail; a once-a-day report cannot. Below the floor an item is left
      for the reader to find by searching, which is what search is for.

    Returns them in the feed's own order, so the report's "top N" is the same top N
    the reader would see on the page. An empty list is a real answer — the caller
    writes "nothing today" rather than relaxing the bar.
    """
    return filter_for_report(
        _suggested_scores(target_filter, content_type), today, threshold=threshold
    )


def filter_for_report(
    scores: list[RelevanceScore], today: str, *, threshold: float | None = None
) -> list[RelevanceScore]:
    """The report narrowing applied to rows already read — see :func:`report_scores`."""
    floor = report_relevance_threshold() if threshold is None else threshold
    keep: list[RelevanceScore] = []
    for score in scores:
        if not _is_new_today(score.signals, today):
            continue
        relevance = relevance_of(score.signals)
        if relevance is None or relevance < floor:
            continue
        keep.append(score)
    return keep


def report_projects_for_user(user) -> list:
    """The active projects a person's report covers, in display order.

    Both ways a project can be *theirs*: one they own personally (``scope_user``)
    and one they were added to as a member — which is how a PI or lab admin assigns
    a lab project to someone in the lab, making it count as both a lab project and
    one of that person's own. Archived projects are excluded: they keep their
    stored recommendations but stop getting new ones, so they can only ever
    contribute an empty row.
    """
    from apps.research.models import Project

    return list(
        Project.objects.active()
        .filter(Q(scope_user=user) | Q(members=user))
        .distinct()
        .order_by("name", "id")
    )


def report_projects_for_lab(lab) -> list:
    """The active projects a lab's report covers — the lab's own, in display order."""
    from apps.research.models import Project

    return list(Project.objects.active().filter(scope_lab=lab).order_by("name", "id"))


def _showcase_item(
    score: RelevanceScore, today: str, member_names: dict[str, str] | None = None
) -> dict:
    """Flatten one score into the small display item the UI/prompt use.

    ``member_names`` maps a username to a display name; it is what turns the stored
    member-fit layer (usernames only, so a rename never needs a re-score) into the
    names the report actually says.
    """
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
        # The attributed cluster (papers only; empty elsewhere) so the papers
        # section prompt can group its write-up by the researcher's focus clusters.
        "cluster_label": signals.get("cluster_label", ""),
        # Who this item is for (institutional targets only — see
        # :mod:`apps.content.member_fit`). Names only; the prompt is told to pass
        # them through, not to reason about who anyone is.
        "for_members": [
            (member_names or {}).get(entry["username"], entry["username"])
            for entry in (signals.get("member_fit") or [])
            if entry.get("username")
            and (not member_names or entry["username"] in member_names)
        ],
    }


@dataclass
class ScopePart:
    """One part of the report: the Personal part, or one project's part.

    ``counts`` is how many new, above-threshold items that part actually has, per
    category — the number the summary table's cell shows. ``items`` is the capped
    slice its section is written from, so a part with 40 qualifying grants counts
    40 and writes up the top few; the heading names the cap, and the two never
    disagree about what is on the page.
    """

    key: str  # "personal" or the project id — stable across a day's reruns
    label: str  # "Personal" or the project name
    kind: str  # "personal" | "project"
    scope: str  # a project's owner discriminator ("user"/"lab"/…); "" for personal
    counts: dict[str, int] = field(default_factory=dict)
    items: dict[str, list[dict]] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    def as_summary_row(self, categories: list[str]) -> dict:
        """The JSON row the summary table renders (one row per part)."""
        return {
            "key": self.key,
            "label": self.label,
            "kind": self.kind,
            "scope": self.scope,
            "counts": {c: self.counts.get(c, 0) for c in categories},
        }


def gather_part(
    target_filter: dict,
    categories: list[str],
    today: str,
    *,
    key: str,
    label: str,
    kind: str,
    scope: str = "",
    limit: int,
    member_names: dict[str, str] | None = None,
) -> ScopePart:
    """Read one target's day into a :class:`ScopePart`, report rules applied.

    Each flattened item carries the per-item ``reason``/``headline`` the matcher
    already wrote, so whatever writes the section — a prompt or the deterministic
    renderer — enriches real, grounded rationale rather than inventing.
    """
    counts: dict[str, int] = {}
    items: dict[str, list[dict]] = {}
    for category in categories:
        scores = report_scores(target_filter, CATEGORY_TYPES[category], today)
        counts[category] = len(scores)
        items[category] = [
            _showcase_item(s, today, member_names) for s in scores[:limit]
        ]
    return ScopePart(
        key=key, label=label, kind=kind, scope=scope, counts=counts, items=items
    )


def _gather(
    target_filter: dict,
    watch,
    allow: tuple[str, ...] | None = None,
    member_names: dict[str, str] | None = None,
) -> tuple[
    list[str],
    dict[str, int],
    dict[str, int],
    dict[str, list[dict]],
]:
    """Return (categories, counts, new_counts, showcase) — the feed-level zones.

    ``counts`` is everything each category's feed surfaces (papers fresh-only,
    opportunities accumulated); ``new_counts`` is the subset that first surfaced on
    the run date (:func:`_is_new_today`), so a day with 3 fresh conferences reads
    "3 new", not "140" — and an accumulated, never-pruned fellowship feed no longer
    re-announces the same set as "new" every day of its week-long pin window.
    ``showcase`` is the small top-``SHOWCASE_PER_CATEGORY`` set the UI card renders.

    These three describe the *feeds*, and the Daily page's summary zone links
    straight to them, so they stay unfiltered. What the report body may say is the
    stricter set (:func:`report_scores`), gathered separately per part.
    """
    categories = _watched_categories(watch, allow)
    today = timezone.now().date().isoformat()
    counts: dict[str, int] = {}
    new_counts: dict[str, int] = {}
    showcase: dict[str, list[dict]] = {}
    for category in categories:
        scores = _suggested_scores(target_filter, CATEGORY_TYPES[category])
        counts[category] = len(scores)
        new_counts[category] = sum(
            1 for s in scores if _is_new_today(s.signals, today)
        )
        showcase[category] = [
            _showcase_item(s, today, member_names)
            for s in scores[:SHOWCASE_PER_CATEGORY]
        ]
    return categories, counts, new_counts, showcase


def _profile_text(target) -> str:
    """A compact natural-language description of the target for the prompts.

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
# Report generation (sectioned fan-out, in briefing_sections)
# --------------------------------------------------------------------------- #


def _write_briefing(
    *,
    owner: dict,
    target,
    target_filter: dict,
    watch,
    allow: tuple[str, ...] | None = None,
    member_names: dict[str, str] | None = None,
    projects: list | None = None,
    complete: briefing_sections.CompleteFn | None = None,
) -> DailyBriefing:
    """Gather a target's day, write the report, and persist it as a ``DailyBriefing``.

    ``owner`` is the update-or-create key (``{"user": user}`` or ``{"lab": lab}``);
    ``target`` is the :class:`MatchTarget` the prose is grounded in; ``target_filter``
    is the ``target_*`` FK the scores are read under; ``projects`` are the projects
    the report covers after the Personal part. Shared by the user and lab entry
    points so both apply the same gather + fallback rules — a lab's report is
    structurally the same document its members receive.
    """
    categories, counts, new_counts, showcase = _gather(
        target_filter, watch, allow, member_names
    )
    today = timezone.now().date().isoformat()

    personal = gather_part(
        target_filter,
        categories,
        today,
        key="personal",
        label="Personal",
        kind="personal",
        limit=briefing_sections.REPORT_ITEMS_PER_SECTION,
        member_names=member_names,
    )
    project_parts = [
        gather_part(
            {"target_project": project},
            categories,
            today,
            key=str(project.id),
            label=project.name,
            kind="project",
            scope=project.scope,
            limit=briefing_sections.PROJECT_ITEMS_PER_SECTION,
            member_names=_project_member_names(project),
        )
        for project in (projects or [])
    ]

    if personal.total or any(part.total for part in project_parts):
        body, used_llm = briefing_sections.generate_report_body(
            _profile_text(target),
            categories,
            personal,
            project_parts,
            complete=complete,
        )
        origin = (
            DailyBriefing.Origin.LLM if used_llm else DailyBriefing.Origin.FALLBACK
        )
    else:
        # Nothing cleared the report's bar today: an honest, populated note — no
        # model call needed, and no padding the page with weaker matches.
        body = briefing_sections.empty_report_body()
        origin = DailyBriefing.Origin.FALLBACK

    if not body:
        body = briefing_sections.empty_report_body()
        origin = DailyBriefing.Origin.FALLBACK

    # Every part gets a row, including a project with nothing today — "no news for
    # this project" is itself an answer, and a row that vanishes on a quiet day
    # reads as the project having been dropped from the report.
    project_summary = [
        part.as_summary_row(categories) for part in ([personal] + project_parts)
    ]

    # Keyed on the day, so a same-day rerun replaces today's report while every
    # earlier day stays readable on the Reports page.
    briefing, _ = DailyBriefing.objects.update_or_create(
        **owner,
        generated_on=timezone.localdate(),
        defaults={
            "body": body,
            "origin": origin,
            "categories": categories,
            "counts": counts,
            "new_counts": new_counts,
            "showcase": showcase,
            "project_summary": project_summary,
        },
    )
    return briefing


def generate_briefing_for_user(
    user,
    *,
    complete: briefing_sections.CompleteFn | None = None,
) -> DailyBriefing:
    """Build and persist one user's daily report. Returns the saved row.

    Gathers the day's per-category counts and found items, then hands them to the
    sectioned writer (:func:`apps.content.briefing_sections.generate_report_body`),
    which produces the sectioned markdown body. ``complete`` is the injectable
    ``(system, user) -> text`` LLM seam (used in tests); when it is absent, fails,
    or returns nothing usable, each prompt's deterministic markdown fallback fills
    in and ``origin`` is recorded as ``fallback``.
    """
    return _write_briefing(
        owner={"user": user},
        target=target_for_user(user),
        target_filter={"target_user": user},
        watch=getattr(user, "watch", None),
        projects=report_projects_for_user(user),
        complete=complete,
    )


def generate_briefing_for_lab(
    lab,
    *,
    complete: briefing_sections.CompleteFn | None = None,
) -> DailyBriefing:
    """Build and persist a lab's daily report over its aggregate matches.

    Same shape as the personal briefing, but grounded in the lab's shared interest
    profile (:func:`apps.content.targets.target_for_lab`) and its ``target_lab``
    scores, and limited to the categories a lab is scored for
    (:data:`LAB_BRIEFING_CATEGORIES`, now all four). The row is keyed on the lab, so
    a lab's briefing is distinct from any member's own.

    A lab report also names *who* each item suits, carried through from the stored
    member-fit layer. Only current members are resolvable, so a departed member's
    stale signal drops out of the prose the same way it drops out of the feed.
    """
    return _write_briefing(
        owner={"lab": lab},
        target=target_for_lab(lab),
        target_filter={"target_lab": lab},
        watch=getattr(lab, "watch", None),
        allow=LAB_BRIEFING_CATEGORIES,
        member_names=_lab_member_names(lab),
        projects=report_projects_for_lab(lab),
        complete=complete,
    )


def _lab_member_names(lab) -> dict[str, str]:
    """``{username: display name}`` for a lab's current members."""
    return _member_names({"target_lab": lab})


def _project_member_names(project) -> dict[str, str]:
    """``{username: display name}`` for the people a project's items can name.

    A lab project resolves to its lab's members (the people who could pick the work
    up); a personal project to its own members — the same rule the matcher used when
    it wrote the member-fit layer, so the names the report says are exactly the ones
    it was given.
    """
    return _member_names({"target_project": project})


def _member_names(persist_kwargs: dict) -> dict[str, str]:
    from apps.core.people import display_name

    from .member_fit import scope_members

    return {
        user.get_username(): display_name(user)
        for user in scope_members(persist_kwargs)
    }
