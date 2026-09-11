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

What the report shows is each category's **slate** — the target's top
:func:`~apps.content.top_feed.top_n` by relevance (:func:`report_scores`) — and what
it calls *new* is whatever entered that slate on this run
(:func:`~apps.content.top_feed.is_entrant`). Those are two different questions and
the report answers both: the reader always sees their best 25, and only the part
that changed is written up fresh.

It used to answer neither. A row appeared because it had been *ingested* that day
and cleared a relevance floor, which meant a bulk import arrived in every reader's
report as news whether or not it had anything to do with their work, while a strong
match that had been sitting in their feed for a week was never mentioned at all.
Anchoring on the slate also makes the report follow the reader: change a focus, a
cluster, or a search term and the slate re-ranks, so what that change promotes is
exactly what gets reported.

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

from django.db.models import Q
from django.utils import timezone

from apps.content import briefing_sections
from apps.content.cluster_fit import lead_sentence, stored_writeup
from apps.content.models import (
    ContentItem,
    DailyBriefing,
    IgnoredItem,
    RelevanceScore,
)
from apps.content.slates import (
    cluster_entries,
    cluster_rank,
    entered_cluster_on,
)
from apps.content.targets import target_for_lab, target_for_user
from apps.content.theme_report import (
    ThemeSection,
    declared_clusters,
    quiet_lines,
    section_label,
    split_by_theme,
)
from apps.content.top_feed import is_entrant, order_by_slate

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
#: its report covers the same ground its feeds do.
LAB_BRIEFING_CATEGORIES: tuple[str, ...] = (
    "papers",
    "grants",
    "conferences",
    "fellowships",
)

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


def _reader_ignored_ids(reader) -> set:
    """Content ids ``reader`` manually ignored — empty when a report has no reader."""
    if reader is None:
        return set()
    return set(
        IgnoredItem.objects.filter(user=reader).values_list("content_id", flat=True)
    )


def _suggested_scores(
    target_filter: dict, content_type: str, *, reader=None
) -> list[RelevanceScore]:
    """A target's suggested items of one type, read the way its feed reads them.

    ``target_filter`` is the single ``target_*`` FK to read under —
    ``{"target_user": user}`` for a person, ``{"target_lab": lab}`` for a lab.
    Mirrors the two read models in ``views.py``:

    - **Papers** (``views._latest_scores``) are fresh-only — keep just the latest
      ``run_at`` (the freshest gather batch), pinned-first by rank.
    - **Opportunities** (``views._accumulated_scores``) accumulate — the union of
      every run's suggested rows, pinned-first then strongest match.

    Either way, rows computed but not promoted (``suggested`` false) are dropped.

    ``reader`` is the one person a report is written *for*, when there is one: their
    manually ignored items are left out, so a report cannot re-deliver tomorrow what
    they dismissed today. A lab's report passes no reader — it belongs to the lab,
    and one member's ignore is not the lab's opinion.
    """
    ignored = _reader_ignored_ids(reader)
    scores = [
        s
        for s in RelevanceScore.objects.filter(
            **target_filter, content__type=content_type
        ).select_related("content")
        if s.signals.get("suggested") and s.content_id not in ignored
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
    """True when a row was *first seen on the run date* — the arrival test.

    This is a fact about the item, not about the reader: it says the store first saw
    this grant today. The report no longer decides anything by it — being new to the
    corpus is not a reason to put something in front of someone — but the feed still
    exposes it, and it is the honest input to that badge.

    Distinct from the feed's own "New" pin, which holds a fresh item for a week
    (``is_new`` AND ``pinned_until >= today`` — see
    :func:`apps.content.views._build_summary._is_new` and
    :meth:`apps.content.serializers.…get_is_new`), and from the report's news, which
    is :func:`~apps.content.top_feed.is_entrant`.

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
    reader=None,
) -> list[RelevanceScore]:
    """The rows a *report* shows for one category: the target's slate, in rank order.

    The slate is the top :func:`~apps.content.top_feed.top_n` of the category's feed
    by fused relevance, recorded on each row when the run persisted it. Reading it
    back — rather than re-deriving a "what's worth showing" rule here — is what keeps
    the report, the PDF, and the feed page from ever disagreeing about what the
    reader's best 25 are.

    ``today`` is unused for selection and kept in the signature because every caller
    passes it and uses it moments later for :func:`~apps.content.top_feed.is_entrant`;
    dropping it would only push the same date-threading into four call sites.

    There is deliberately no extra relevance floor. There was one, and stacked on
    top of a slate it can only ever mean "show fewer than the top 25" — the feed's
    own embedding threshold already decides what is good enough to be in the feed at
    all, and a second opinion about the top of that list just made the report quietly
    shorter than it claimed to be. An empty list is still a real answer: a target
    with nothing above its feed threshold gets an honest "nothing yet".
    """
    return filter_for_report(
        _suggested_scores(target_filter, content_type, reader=reader), today
    )


def filter_for_report(
    scores: list[RelevanceScore], today: str
) -> list[RelevanceScore]:
    """The slate, in rank order, from rows already read — see :func:`report_scores`."""
    return order_by_slate(scores)


def report_new_scores(
    scores: list[RelevanceScore], today: str
) -> list[RelevanceScore]:
    """The slate members that entered on ``today``'s run — the report's news."""
    return [s for s in scores if is_entrant(s.signals or {}, today)]


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


def report_projects_for_lab(lab, *, shared_only: bool = True) -> list:
    """The active projects a lab's **shared** surfaces cover, in display order.

    A lab report is read by every lab member and posted to the lab's Discord
    channel, but :meth:`apps.research.models.ProjectQuerySet.visible_to` grants a
    lab project only to its own members and to lab or department heads. Listing
    every active lab project here therefore published names and matched items to
    people the project itself would not show them to — and once project *state*
    enters a report that becomes unpublished research plans.

    So a project reaches a lab surface only when its editors opted it in
    (``share_in_lab_reports``, default off). Private lab projects keep appearing in
    their own members' personal reports through
    :func:`report_projects_for_user`, which is scoped to one reader.

    ``shared_only=False`` is for callers that are not a shared surface — a count of
    what the lab actually owns, or an editor's own project list.
    """
    from apps.research.models import Project

    queryset = Project.objects.active().filter(scope_lab=lab)
    if shared_only:
        queryset = queryset.filter(share_in_lab_reports=True)
    return list(queryset.order_by("name", "id"))


def hidden_lab_projects(lab) -> int:
    """How many of a lab's active projects a shared surface is leaving out.

    The lab post and the lab PDF both say "N private projects not shown" rather
    than silently showing a shorter list: a reader who knows the lab has six
    projects and sees one should be told why, and told it is a sharing setting
    rather than a quiet day.
    """
    from apps.research.models import Project

    return (
        Project.objects.active()
        .filter(scope_lab=lab, share_in_lab_reports=False)
        .count()
    )


def _deadline_rounds(meta: dict) -> list[dict]:
    """Every dated round on a grant or conference, normalised to one shape.

    The mapper (:mod:`apps.scraper.collect.mapping`, plan Phase 3) stores a
    grant's full round history and a conference's full deadline history under
    different keys and in different shapes — the two record schemas were never
    going to agree, and forcing them to at the source would have meant lying
    about one of them. A grant's ``due_dates`` is a flat list of ISO round
    dates; a conference's ``deadlines_structured`` is the full 8-key
    ``Deadline`` array (kind, instant, label, basis, and four more). This is
    the one place that difference gets resolved, into ``{date, kind, label}``
    — so the showcase widget and the PDF's multi-deadline table (plan D1 —
    "display all, remind on next") read one shape regardless of category,
    instead of re-deriving the type distinction at every call site downstream.

    Neither key exists on a paper or a fellowship, so both come back empty and
    the field is simply absent there — no dated-round concept applies to
    either.

    Sorted chronologically, with an undated ("TBD") round last, so a reader —
    or the PDF table — never has to re-sort what is meant to already read as a
    timeline.
    """
    due_dates = meta.get("due_dates")
    if due_dates:
        rounds = [{"date": d, "kind": "application", "label": ""} for d in due_dates]
    else:
        rounds = [
            {
                "date": (entry.get("instant") or "")[:10],
                "kind": entry.get("kind", ""),
                "label": entry.get("round_label", ""),
            }
            for entry in meta.get("deadlines_structured") or []
        ]
    return sorted(rounds, key=lambda r: (r["date"] == "", r["date"]))


def _showcase_item(
    score: RelevanceScore,
    today: str,
    member_names: dict[str, str] | None = None,
    cluster_id: str | None = None,
) -> dict:
    """Flatten one score into the small display item the UI/prompt use.

    ``member_names`` maps a username to a display name; it is what turns the stored
    member-fit layer (usernames only, so a rename never needs a re-score) into the
    names the report actually says.

    This dict is the vocabulary every downstream renderer has — the Daily page's
    showcase widget, the written report's per-item rationale, and the PDF's Top-N
    listings (via :func:`apps.content.daily_report._item_from_score`). A field
    left out here is invisible everywhere those read from, which is why the open
    collector's signals — rankings, trust tier, licence, the full deadline array
    (plan Phase 11) — are added *here*, once, rather than at each consumer.
    """
    content = score.content
    meta = content.metadata or {}
    signals = score.signals or {}
    title = meta.get("title") or meta.get("name") or "(untitled)"
    # Read the write-up for the theme this item is being shown *under*. A bridge
    # item carries a separate judgement in each theme's slate, so reading the row
    # rather than the pair is exactly how one theme's reasoning ends up printed
    # under both headings.
    entries = cluster_entries(signals)
    writeup = stored_writeup(signals, cluster_id) if cluster_id else None
    if writeup is None and not cluster_id and entries:
        best = min(entries, key=lambda key: entries[key].get("rank", 10**6))
        writeup = stored_writeup(signals, best)
    bridge_labels = [
        (entry.get("label") or "")
        for other, entry in entries.items()
        if other != cluster_id and (entry.get("label") or "")
    ]
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
        # The full round array behind that one date (plan D1) — a conference's
        # complete deadline history or a grant's complete round history,
        # normalised to one shape. Read from ``metadata`` directly rather than
        # ``signals``: unlike ``deadline_date``, nothing snapshots this onto the
        # score at persist time, and it is a property of the item itself, not
        # of the match.
        "deadlines": _deadline_rounds(meta),
        # CCF / CORE / THCPL, visual only (plan D2 — never a relevance signal) —
        # conferences only; a grant, paper, or fellowship carries neither key
        # and both default empty.
        "rankings": meta.get("rankings") or {},
        "rank_badges": meta.get("rank_badges") or [],
        # Per-record attribution (plan D5 / D9): US federal grants are public
        # domain by statute, the EU portal carries its own reuse decision, and
        # every conference source states its own licence on the record itself.
        "license": meta.get("license", ""),
        # The item's raw provenance id (``"grants:nsf"``, ``"conf:ccf_deadlines"``
        # — set at Phase 3 mapping), not a display label: no source-to-friendly-
        # name registry exists anywhere in the collector or this codebase, so
        # this is exactly what ``content.source`` holds rather than an invented
        # one.
        "source_name": content.source,
        # Two different questions, both answered: ``is_new`` is the *feed's* badge
        # (first seen today), ``is_entrant`` is the *report's* news (entered the
        # reader's slate on this run). Conflating them is what had a bulk import
        # announced to everyone as an opportunity they had not seen.
        "is_new": _is_new_today(signals, today),
        "is_entrant": (
            entered_cluster_on(signals, cluster_id, today)
            if cluster_id
            else is_entrant(signals, today)
        ),
        "top_rank": signals.get("top_rank"),
        # Position *within this theme* — the thing that replaced the percent. A
        # global position would be comparing scores that are not comparable, which
        # is the failure this whole redesign removes.
        "position": (
            cluster_rank(signals, cluster_id) if cluster_id
            else (signals.get("top_rank") or 0)
        ),
        "verdict": (writeup or {}).get("verdict") or signals.get("verdict"),
        # The PDF prints only the first beat; the web entry gets all three plus
        # the caveat, which is where a reader who wants depth has asked for it.
        "lead": lead_sentence(writeup) or signals.get("reason", ""),
        "caveat": (writeup or {}).get("caveat") or signals.get("caveat", ""),
        "bridge_note": (writeup or {}).get("bridge_note", ""),
        "bridge_labels": bridge_labels,
        "edition": meta.get("edition") or meta.get("year") or "",
        # The attributed cluster (papers only; empty elsewhere) so the papers
        # section prompt can group its write-up by the researcher's focus clusters.
        "cluster_label": signals.get("cluster_label", ""),
        # Who this item is for (institutional targets only — see
        # :mod:`apps.content.member_fit`). Names only, and read by the feed's
        # "Best suited to" strip; the daily report deliberately does not use it.
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
    #: One section per research theme that has news — the document's body since
    #: the report was reorganised from part → category → items to
    #: theme → what's new → what's standing.
    themes: list[ThemeSection] = field(default_factory=list)
    #: ``[(label, standing count)]`` for themes holding a slate but nothing new.
    #: One line at the end of the theme sequence, never a section.
    quiet: list[tuple[str, int]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    @property
    def live_themes(self) -> list[ThemeSection]:
        """The themes that earn a section. A theme with no news is one quiet line."""
        return [theme for theme in self.themes if theme.has_news]

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
    reader=None,
    clusters: list | None = None,
) -> ScopePart:
    """Read one target's slate into a :class:`ScopePart`, and what is new in it.

    ``counts`` is how many *entrants* the part has per category — what the summary
    table calls new — while ``items`` is the slate itself, which is what the reader
    is shown. A part with a full Top-25 and one entrant therefore counts 1 and still
    presents 25: the report is not a list of arrivals, it is the reader's best work
    with this morning's change called out inside it.

    Each flattened item carries the per-item ``reason``/``headline`` the matcher
    already wrote, so whatever writes the section — a prompt or the deterministic
    renderer — enriches real, grounded rationale rather than inventing.
    """
    counts: dict[str, int] = {}
    items: dict[str, list[dict]] = {}
    sections: dict[str, ThemeSection] = {}
    for category in categories:
        content_type = CATEGORY_TYPES[category]
        scores = report_scores(target_filter, content_type, today, reader=reader)
        counts[category] = len(report_new_scores(scores, today))
        items[category] = [
            _showcase_item(s, today, member_names) for s in scores[:limit]
        ]
        for cluster in clusters or []:
            section = sections.get(cluster.id)
            if section is None:
                section = ThemeSection(
                    cluster_id=cluster.id, label=section_label(cluster, label)
                )
                sections[cluster.id] = section
            split = split_by_theme(
                scores,
                [cluster],
                today,
                content_type=content_type,
                build=lambda score, cid: _showcase_item(
                    score, today, member_names, cid
                ),
            )
            entrants, standing = split.get(cluster.id, ([], []))
            if entrants:
                section.entrants[category] = entrants
            if standing:
                section.standing[category] = standing
    themes = [section for section in sections.values() if section.is_alive]
    return ScopePart(
        key=key,
        label=label,
        kind=kind,
        scope=scope,
        counts=counts,
        items=items,
        themes=themes,
        quiet=quiet_lines(themes),
    )


def _gather(
    target_filter: dict,
    watch,
    allow: tuple[str, ...] | None = None,
    member_names: dict[str, str] | None = None,
    reader=None,
) -> tuple[
    list[str],
    dict[str, int],
    dict[str, int],
    dict[str, list[dict]],
]:
    """Return (categories, counts, new_counts, showcase) — the feed-level zones.

    ``counts`` is everything each category's feed surfaces (papers fresh-only,
    opportunities accumulated) — the number the Daily page's summary zone links
    through to, so it stays unfiltered. ``new_counts`` is how many items *entered the
    target's slate* on this run, which is the same number the report announces, so
    the card and the report never disagree about how much is new.
    ``showcase`` is the small top-``SHOWCASE_PER_CATEGORY`` set the UI card renders.
    """
    categories = _watched_categories(watch, allow)
    today = timezone.now().date().isoformat()
    counts: dict[str, int] = {}
    new_counts: dict[str, int] = {}
    showcase: dict[str, list[dict]] = {}
    for category in categories:
        scores = _suggested_scores(
            target_filter, CATEGORY_TYPES[category], reader=reader
        )
        counts[category] = len(scores)
        new_counts[category] = sum(
            1 for s in scores if is_entrant(s.signals or {}, today)
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
    hidden_projects: int = 0,
    alert_summaries: list | None = None,
    personal_label: str = briefing_sections.PERSONAL_HEADING,
    complete: briefing_sections.CompleteFn | None = None,
    reader=None,
    kind: str = DailyBriefing.Kind.DAILY,
    stats: dict | None = None,
    attention: str = "",
) -> DailyBriefing:
    """Gather a target's day, write the report, and persist it as a ``DailyBriefing``.

    ``owner`` is the update-or-create key (``{"user": user}`` or ``{"lab": lab}``);
    ``target`` is the :class:`MatchTarget` the prose is grounded in; ``target_filter``
    is the ``target_*`` FK the scores are read under; ``projects`` are the projects
    the report covers after the Personal part, and ``hidden_projects`` is how many
    the surface is holding back (a lab's unshared projects), which the body reports
    as a count and never by name. Shared by the user and lab entry
    points so both apply the same gather + fallback rules — a lab's report is
    structurally the same document its members receive.
    """
    alert_summaries = alert_summaries or []
    categories, counts, new_counts, showcase = _gather(
        target_filter, watch, allow, member_names, reader=reader
    )
    today = timezone.now().date().isoformat()
    clusters = declared_clusters(getattr(target, "interests", None))

    personal = gather_part(
        target_filter,
        categories,
        today,
        key="personal",
        label=personal_label,
        kind="personal",
        limit=briefing_sections.REPORT_ITEMS_PER_SECTION,
        member_names=member_names,
        reader=reader,
        clusters=clusters,
    )
    # Projects stay flat (open decision OD3): they rarely carry themes of their
    # own, and inheriting the parent's would attribute a project's matches to a
    # strand the project never declared.
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
            reader=reader,
        )
        for project in (projects or [])
    ]

    narrative_payload: dict = {}
    # An alert is news even on a day when nothing entered a top list: something
    # happened *to a project*, which is a different event from something entering
    # a slate. Carrying yesterday's report forward over it would bury the one
    # thing that needed deciding today.
    if personal.total or any(part.total for part in project_parts) or attention:
        narrative_payload = briefing_sections.write_narrative(
            _profile_text(target),
            personal,
            clusters,
            complete=complete,
            entitled=_narrative_entitled(target_filter),
            alerts=alert_summaries,
        )
        body, used_llm = briefing_sections.generate_report_body(
            _profile_text(target),
            categories,
            personal,
            project_parts,
            complete=complete,
            narrative=narrative_payload,
            hidden_projects=hidden_projects,
            attention=attention,
        )
        origin = (
            DailyBriefing.Origin.LLM if used_llm else DailyBriefing.Origin.FALLBACK
        )
    else:
        # Nothing entered the reader's Top-25, so there is nothing to say that was
        # not said yesterday. Carrying the previous body forward verbatim is the
        # honest answer and the cheap one: re-running the model would spend a call
        # to re-word the same conclusions, and the reader would have to read the
        # whole thing again to discover it had not changed.
        body, origin = _carry_forward(owner, kind)

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
        # Part of the key, not the payload: the unique constraint is
        # (target, day, kind), and Monday carries a daily *and* a weekly. Without
        # it a Monday weekly would overwrite that morning's daily in place.
        kind=kind,
        defaults={
            "body": body,
            "origin": origin,
            "categories": categories,
            "counts": counts,
            "new_counts": new_counts,
            "showcase": showcase,
            "project_summary": project_summary,
            "narrative": narrative_payload,
            "stats": stats or {},
        },
    )
    return briefing


def _narrative_entitled(target_filter: dict) -> bool:
    """Whether this target's plan includes Mylo's prose.

    The same gate the write-ups use. A free reader's document opens on the cover
    table and the listings — quieter, not broken — which is the honest rendering
    of a paid layer that is not paid for.
    """
    from .theme_run import target_is_entitled

    return target_is_entitled(target_filter)


def _carry_forward(
    owner: dict, kind: str = DailyBriefing.Kind.DAILY
) -> tuple[str, str]:
    """Yesterday's body for this target, or an honest empty note when there is none.

    Looks past today's own row: a same-day rerun must carry the *previous day's*
    report forward, not the one it is in the middle of replacing. Scoped to the
    same ``kind``, so a quiet Monday carries forward the previous *weekly* rather
    than reissuing Friday's daily under a weekly heading.
    """
    previous = (
        DailyBriefing.objects.filter(kind=kind, **owner)
        .exclude(generated_on=timezone.localdate())
        .order_by("-generated_on")
        .first()
    )
    body = (getattr(previous, "body", "") or "").strip()
    if not body:
        return briefing_sections.empty_report_body(), DailyBriefing.Origin.FALLBACK
    return body, DailyBriefing.Origin.CARRIED


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
    from .alert_report import attention_section, block_for, open_alerts
    from .report_stats import record_run_stats

    blocks = [block_for(alert) for alert in open_alerts({"target_user": user})]
    summaries = [
        (block.project_label, block.trigger_label, block.title) for block in blocks
    ]
    briefing = _write_briefing(
        owner={"user": user},
        target=target_for_user(user),
        target_filter={"target_user": user},
        watch=getattr(user, "watch", None),
        projects=report_projects_for_user(user),
        complete=complete,
        # A personal report has exactly one reader, so it honours their ignores.
        reader=user,
        attention=attention_section(blocks),
        alert_summaries=summaries,
    )
    # The run's numbers, settled here so every later surface reads them back off
    # the row rather than deriving its own from the same tables minutes apart.
    return record_run_stats(briefing)


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
    a lab's briefing is distinct from any member's own, and its own part is headed
    with the lab's name rather than "Personal".

    The report does *not* name who each item suits. The member-fit layer is still
    computed and still drives the "Best suited to" strip on a lab's feed cards,
    which is the surface where "who should pick this up" is a question the reader is
    asking; inside a ranked daily read it broke the one shape every other entry
    shares. ``member_names`` is still resolved and passed down because
    :func:`_showcase_item` records it on the stored showcase for those surfaces.
    """
    from .alert_report import attention_section, block_for, open_alerts
    from .report_stats import record_run_stats

    blocks = [block_for(alert) for alert in open_alerts({"target_lab": lab})]
    summaries = [
        (block.project_label, block.trigger_label, block.title) for block in blocks
    ]
    briefing = _write_briefing(
        owner={"lab": lab},
        target=target_for_lab(lab),
        target_filter={"target_lab": lab},
        watch=getattr(lab, "watch", None),
        allow=LAB_BRIEFING_CATEGORIES,
        member_names=_lab_member_names(lab),
        projects=report_projects_for_lab(lab),
        hidden_projects=hidden_lab_projects(lab),
        # The lab's aggregate part is the lab, so it is named after it. "Personal"
        # is what a *person's* own matches are called; on a lab's report it named
        # nobody.
        personal_label=lab.name,
        complete=complete,
        attention=attention_section(blocks),
        alert_summaries=summaries,
    )
    return record_run_stats(briefing)


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
