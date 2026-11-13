"""Compile a day into the data the daily Discord PDF report renders from.

This is the *gather* half of the daily "Mylo Report" — as a DM to a person
(``tools.delivery.reminders_discord.send_personal_report``) and as an attachment to a
lab's channel (``tools.delivery.lab_digest.queue_lab_report``); the render half is
:mod:`.daily_report_pdf`, which is target-agnostic. It reads the same suggested
:class:`RelevanceScore` feeds the portal and the written briefing read — reusing
:mod:`tools.delivery.briefing`'s canonical readers, including its slate selection, so
the PDF can never drift from what the written report says — and shapes them into a
:class:`ReportData`:

* a **Personal** part: each watched category's slate, capped at :data:`TOP_PERSONAL`,
* one part **per project** the reader is on, each category capped at
  :data:`TOP_PROJECT`,
* the day's per-category feed counts and how many entered the slate, and
* the freshest written :class:`DailyBriefing` body (the report's main section).

The reader always gets their best 25 per category. What changes day to day is which
of them are flagged new — the ones that entered the slate on this run — and those
are the only ones Mylo spends a fresh write-up on.

Every category is capped in its own right. The old report pooled grants,
fellowships, and conferences into one combined top 25, which meant a heavy grant
day could push every conference off the page — a reader looking for venues
concluded there were none.

Everything is pure and read-only; the command in
``management/commands/send_daily_discord_reports.py`` drives compile → render →
send → cleanup over the eligible users.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.utils import timezone

from tools.delivery import briefing
from tools.delivery.briefing_sections import SECTION_NOUN, apply_narrative
from tools.delivery.models import DailyBriefing, SavedOpportunity
from tools.delivery.report_stats import (
    DEFAULT_DEADLINE_WINDOW_DAYS,
    ReportStats,
    compile_stats,
)
from tools.delivery.theme_report import (
    ThemeSection,
    declared_clusters,
    quiet_lines,
    section_label,
    split_by_theme,
)
from tools.recommendation.fellowship_bands import OPEN as OPEN_BAND
from tools.recommendation.models import RelevanceScore
from tools.recommendation.slates import standing_render_depth
from tools.recommendation.targets import target_for_lab

#: Per-category caps. The reader's own part gets the deeper list; a project is a
#: narrower surface and a short list is the point of having one per project.
TOP_PERSONAL = 25
TOP_PROJECT = 10

#: Human labels for each category, used in the PDF headings and the DM summary.
CATEGORY_LABELS: dict[str, str] = {
    "papers": "Papers",
    "grants": "Grants",
    "fellowships": "Fellowships",
    "conferences": "Conferences",
}

#: The word the PDF's section headings use for each category ("Top 25 Articles").
SECTION_NOUNS: dict[str, str] = {
    "papers": "Articles",
    "grants": "Grants",
    "fellowships": "Fellowships",
    "conferences": "Conferences",
}


@dataclass
class ReportItem:
    """One found item, flattened for display in the PDF."""

    type: str
    category: str
    title: str
    url: str
    headline: str
    reason: str
    source: str
    deadline_date: str
    #: This item entered the reader's slate on this run — the report's "new" badge.
    is_new: bool
    #: The underlying :class:`~tools.retrieval.models.ContentItem` id, as a string.
    #: Carried so a surface that needs to join back — the deadline horizon, a
    #: reader's saves — can do it without re-reading the score rows the report was
    #: already built from. Defaults to empty for the hand-built sample items,
    #: which have no row behind them; every join skips a falsy id.
    content_id: str = ""
    cluster_label: str = ""
    #: Position within **this theme's** slate — what replaced the percent match.
    #: A global position would compare scores that are not comparable, which is
    #: the failure the per-cluster redesign removes.
    position: int = 0
    # : read / skim / file / skip (:mod:`tools.recommendation.verdicts`). ``None`` on a
    # row
    #: scored before the verdict existed.
    verdict: str | None = None
    #: The reason's **first beat** — the one sentence the printed page carries.
    #: Without it a reader gets sixty titles and must open the site to make any
    #: judgement at all, which defeats a morning brief. The remaining beats and
    #: the caveat go to the web entry.
    lead: str = ""
    caveat: str = ""
    #: Other themes whose slate this item also sits in — the ``ALSO IN`` badge.
    bridge_labels: list[str] = field(default_factory=list)
    #: The call's edition, where one exists (*NeurIPS 2027*). It carries the
    #: returning-reader signal on a reopened annual call, so no second badge is
    #: needed beyond ``NEW``.
    edition: str = ""
    #: Every dated round, normalised across grants and conferences (see
    #: ``briefing._deadline_rounds``) — the multi-deadline detail ``deadline_date``
    #: alone cannot carry. Rendered as a small table only in the structured PDF
    #: listings (plan Phase 11 point 3); the written markdown report keeps its one
    #: ``deadline YYYY-MM-DD`` marker per item, because widening that grammar would
    #: mean changing three independent parsers in lockstep (see
    #: ``daily_report_pdf._split_item_line``).
    deadlines: list[dict] = field(default_factory=list)
    #: ``{system: {rank, edition}}`` verbatim, and its frontend-friendly flattening
    #: — conferences only; empty for papers, grants, and fellowships (plan D2:
    #: rankings are visual only, never a relevance signal).
    rankings: dict = field(default_factory=dict)
    rank_badges: list[dict] = field(default_factory=list)
    #: Per-source attribution string (plan D9's licence/attribution requirement).
    license: str = ""
    #: The item's raw provenance id (``"grants:nsf"``, ``"conf:ccf_deadlines"``),
    #: not a display label — none exists anywhere in this codebase, so this is
    #: exactly what ``content.source`` holds rather than an invented friendly name.
    source_name: str = ""


#: What the reader's own (non-project) part is called when the report is a person's.
#: A lab's report uses the lab's name instead — see :func:`compile_report_for_lab`.
PERSONAL_LABEL = "Personal"


@dataclass
class ReportPart:
    """One part of the report — the reader's own, or one project — as a section.

    ``counts`` is how many items *entered* the part's slate per category — the
    number its summary-table cell shows. ``items`` is the slate itself, capped at
    ``cap``, which is what the PDF lists under the part's headings. A part with a
    settled Top-25 and one entrant therefore counts 1 and still prints 25.
    """

    key: str
    label: str
    kind: str  # "personal" | "project"
    cap: int
    counts: dict[str, int] = field(default_factory=dict)
    items: dict[str, list[ReportItem]] = field(default_factory=dict)
    #: Slate size per category before ``cap`` — what "showing 10 of 25" counts.
    slate_sizes: dict[str, int] = field(default_factory=dict)
    #: One section per research theme that has news — the document's body. Empty
    #: for a project, which stays flat and entrant-only (open decision OD3).
    themes: list[ThemeSection] = field(default_factory=list)
    #: ``[(label, standing count)]`` for themes holding a slate but nothing new.
    quiet: list[tuple[str, int]] = field(default_factory=list)

    @property
    def live_themes(self) -> list[ThemeSection]:
        return [theme for theme in self.themes if theme.has_news]

    @property
    def total(self) -> int:
        """How many items entered this part's slate — the part's news."""
        return sum(self.counts.values())

    @property
    def shown(self) -> int:
        """How many items this part actually prints, across categories."""
        return sum(len(items) for items in self.items.values())


@dataclass
class ReportData:
    """Everything the PDF and the summary DM need for one user."""

    username: str
    display_name: str
    generated_on: str
    briefing_markdown: str
    briefing_origin: str
    categories: list[str]
    #: Mylo's opening paragraph, read back from the stored narrative rather than
    #: regenerated — a model call happens once per artefact (plan §19). Empty for
    #: an unentitled reader, whose document opens on the cover table instead.
    lead: str = ""
    lead_origin: str = ""
    #: Eligibility-qualified fellowships whose research fit is **flat** across
    #: every theme — topic-agnostic awards. They belong to no theme, so they get
    #: their own short band rather than being repeated under all of them or
    #: dropped for having no slate place (plan §12).
    open_fellowships: list[ReportItem] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    new_counts: dict[str, int] = field(default_factory=dict)
    personal: ReportPart | None = None
    projects: list[ReportPart] = field(default_factory=list)
    #: How many of the target's projects this surface is holding back — a lab's
    #: projects whose editors have not turned on ``share_in_lab_reports``. Reported
    #: as a count and never by name, so the document is honest about being partial
    #: without publishing what it is withholding. Always 0 on a personal report,
    #: which is scoped to one reader.
    private_projects_hidden: int = 0
    #: This run's numbers (plan 1.1). Derived from the parts above, so the
    #: statistics block and the summary table can never disagree.
    stats: ReportStats = field(default_factory=ReportStats)
    #: Today's open alerts as renderable blocks
    #: (:class:`tools.delivery.alert_report.AlertBlock`). Structured rather than
    #: markdown because the PDF renders from structure — the written body carries
    #: the same alerts as markdown for the web, and both come from one source.
    alerts: list = field(default_factory=list)

    @property
    def parts(self) -> list[ReportPart]:
        """Personal first, then every project — the report's section order."""
        return ([self.personal] if self.personal is not None else []) + list(
            self.projects
        )

    @property
    def total_count(self) -> int:
        return sum(self.counts.values())

    @property
    def total_new(self) -> int:
        return sum(self.new_counts.values())

    @property
    def report_new(self) -> int:
        """How many items the report calls new — the summary table's grand total."""
        return sum(part.total for part in self.parts)

    #: Discord's embed description limit. The message body has to fit inside it
    #: whole — a truncated brief that stops mid-theme is worse than a short one.
    DISCORD_BODY_LIMIT = 4096

    def message_body(self) -> str:
        """The Discord message that carries the PDF.

        It was a summary line and the word "attached". It is now Mylo's lead
        paragraph, one line per theme with its entrant count, and the attachment
        line — short enough to read in the channel, complete enough that a reader
        who never opens the PDF still knows whether they should.

        Trimming is by whole themes, never mid-sentence: a body cut in half reads
        as a delivery failure, while a body that says "and 3 more themes" reads as
        an editor's decision.
        """
        tail = "Your full report is attached as a PDF."
        lines: list[str] = []
        if self.lead:
            lines.append(self.lead)
            lines.append("")
        themes = self.personal.live_themes if self.personal is not None else []
        for section in themes:
            count = section.entrant_count
            noun = "item" if count == 1 else "items"
            lines.append(f"**{section.label}** — {count} new {noun}")
        quiet = getattr(self.personal, "quiet", None) or []
        if quiet:
            lines.append(f"Quiet today: {', '.join(label for label, _ in quiet)}.")
        if not themes:
            lines.append(self.summary_line())
        lines.append("")
        lines.append(tail)

        body = "\n".join(lines)
        while len(body) > self.DISCORD_BODY_LIMIT and themes:
            dropped = len(themes)
            themes = themes[:-1]
            kept = [f"**{s.label}** — {s.entrant_count} new" for s in themes]
            more = dropped - len(themes)
            body = "\n".join(
                [self.lead, "", *kept, f"…and {more} more themes.", "", tail]
            )
        return body[: self.DISCORD_BODY_LIMIT]

    def summary_line(self) -> str:
        """A one-line 'what Mylo found' summary for the DM embed body.

        Counts what *entered* the reader's slate, not what the feeds hold — the DM
        says what changed, and the attachment shows the whole Top-25 it changed in.
        """
        personal = self.personal.counts if self.personal is not None else {}
        parts = [
            f"{personal[category]} {_category_noun(category, personal[category])}"
            for category in self.categories
            if personal.get(category)
        ]
        active = [p for p in self.projects if p.total]
        if not parts and not active:
            return "Nothing new cleared the bar today — Mylo will keep watching."
        lead = "Mylo found " + ", ".join(parts) + " for you" if parts else "Mylo found"
        if active:
            noun = "project" if len(active) == 1 else "projects"
            found = sum(p.total for p in active)
            joiner = ", plus " if parts else " "
            lead += f"{joiner}{found} across {len(active)} {noun}"
        return lead + "."


def _category_noun(category: str, count: int) -> str:
    """``"grant"`` / ``"grants"`` — the count's own noun.

    The summary line is the first full sentence on the cover, so "1 grants" is read
    by everyone who opens the report.
    """
    plural = CATEGORY_LABELS.get(category, category.title()).lower()
    return plural if count != 1 else SECTION_NOUN.get(category, plural)


def _source_line(content_type: str, meta: dict) -> str:
    """A short provenance line (venue / sponsor / location) for one item."""
    if content_type == "paper":
        venue = _clean(meta.get("venue"))
        if venue:
            return venue
        authors = meta.get("authors")
        if isinstance(authors, list) and authors:
            first = _clean(authors[0])
            return f"{first} et al." if len(authors) > 1 else first
        return ""
    if content_type == "conference":
        # ``place_text`` (not ``location``) since plan Phase 3: the open collector's
        # mapper (``tools.retrieval.collect.mapping.map_conference``) never writes a
        # "location" key — that is a legacy key from an earlier source. The
        # collector's equivalent free-text venue string is ``place_text``; reading
        # the old key here silently dropped the venue half of this line down to
        # country-only for every migrated record.
        # Chained, not swapped. The collector writes ``place_text``; legacy rows
        # carry ``location``. During the migration window both shapes are in the table
        # at once — measured 2,958 of 2,962 conferences still on ``location`` and
        # none yet on ``place_text`` — so replacing the key outright would drop
        # every existing conference to country-only. The fallback costs one
        # ``or`` and can be deleted once no ``location`` row survives.
        place = _clean(meta.get("place_text")) or _clean(meta.get("location"))
        return ", ".join(p for p in (place, _clean(meta.get("country"))) if p)
    # grants + fellowships
    return _clean(meta.get("sponsor")) or _clean(meta.get("funder"))


def _clean(value) -> str:
    return " ".join(str(value).split()) if value else ""


def _item_from_score(
    score: RelevanceScore,
    category: str,
    today: str,
    cluster_id: str | None = None,
) -> ReportItem:
    flat = briefing._showcase_item(score, today, None, cluster_id)
    meta = score.content.metadata or {}
    return ReportItem(
        content_id=flat["content_id"],
        type=flat["type"],
        category=category,
        title=flat["title"],
        url=flat["url"],
        headline=flat["headline"],
        reason=flat["reason"],
        source=_source_line(flat["type"], meta),
        deadline_date=flat["deadline_date"],
        is_new=flat["is_entrant"],
        cluster_label=flat["cluster_label"],
        position=flat["position"],
        verdict=flat["verdict"],
        lead=flat["lead"],
        caveat=flat["caveat"],
        bridge_labels=flat["bridge_labels"],
        edition=str(flat["edition"] or ""),
        deadlines=flat["deadlines"],
        rankings=flat["rankings"],
        rank_badges=flat["rank_badges"],
        license=flat["license"],
        source_name=flat["source_name"],
    )


def _open_fellowships(
    target_filter: dict, today: str, *, reader=None
) -> list[ReportItem]:
    """The "open to you" band, in the order the eligibility engine produced.

    Deliberately not re-sorted by research fit: these are the awards whose fit is
    flat across every theme, so there is no topical order to impose and pretending
    otherwise would be the directory problem wearing a ranking.
    """
    scores = briefing.report_scores(
        target_filter, briefing.CATEGORY_TYPES["fellowships"], today, reader=reader
    )
    rows = [s for s in scores if (s.signals or {}).get("band") == OPEN_BAND]
    rows.sort(key=lambda s: (s.signals or {}).get("band_position") or 10**6)
    return [
        _item_from_score(s, "fellowships", today)
        for s in rows[:standing_render_depth(briefing.CATEGORY_TYPES["fellowships"])]
    ]


def _saved_content_ids(reader, saves_filter: dict | None) -> set:
    """What this target has bookmarked — the other half of the deadline horizon.

    A saved call with a date next week matters whether or not it is still in a top
    list this morning, and saving something is the clearest statement a reader can
    make that they intend to act on it.
    """
    if saves_filter is None:
        saves_filter = {"user": reader, "target_lab": None} if reader else None
    if not saves_filter:
        return set()
    return set(
        SavedOpportunity.objects.filter(**saves_filter)
        .exclude(content__isnull=True)
        .values_list("content_id", flat=True)
    )


def _theme_item_builder(category: str, today: str):
    """A ``(score, cluster_id) -> ReportItem`` builder bound to one category."""

    def build(score: RelevanceScore, cluster_id: str) -> ReportItem:
        return _item_from_score(score, category, today, cluster_id)

    return build


def _compile_part(
    target_filter: dict,
    categories: list[str],
    today: str,
    *,
    key: str,
    label: str,
    kind: str,
    cap: int,
    reader=None,
    clusters: list | None = None,
) -> ReportPart:
    """One part's slate per category, plus how much of it is new.

    ``reader`` is the person the PDF is addressed to, when there is one; their
    manually ignored items are dropped so the document matches the pages they read.
    """
    counts: dict[str, int] = {}
    items: dict[str, list[ReportItem]] = {}
    slate_sizes: dict[str, int] = {}
    sections: dict[str, ThemeSection] = {}
    for category in categories:
        content_type = briefing.CATEGORY_TYPES[category]
        scores = briefing.report_scores(
            target_filter, content_type, today, reader=reader
        )
        counts[category] = len(briefing.report_new_scores(scores, today))
        slate_sizes[category] = len(scores)
        items[category] = [
            _item_from_score(s, category, today) for s in scores[:cap]
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
                build=_theme_item_builder(category, today),
            )
            entrants, standing = split.get(cluster.id, ([], []))
            if entrants:
                section.entrants[category] = entrants
            if standing:
                section.standing[category] = standing
    themes = [section for section in sections.values() if section.is_alive]
    return ReportPart(
        key=key,
        label=label,
        kind=kind,
        cap=cap,
        counts=counts,
        items=items,
        slate_sizes=slate_sizes,
        themes=themes,
        quiet=quiet_lines(themes),
    )


def _compile(
    *,
    key: str,
    display_name: str,
    watch,
    target_filter: dict,
    briefing_filter: dict,
    projects: list,
    allow: tuple[str, ...] | None = None,
    personal_label: str = PERSONAL_LABEL,
    reader=None,
    interests: dict | None = None,
    hidden_projects: int = 0,
    window_days: int = DEFAULT_DEADLINE_WINDOW_DAYS,
    saves_filter: dict | None = None,
    alerts: list | None = None,
) -> ReportData:
    """The shared gather, over whatever target the two public compilers name.

    Everything here — which categories are watched, which suggested scores to read,
    which projects to break out, which written briefing to attach — is the same work
    for a person and for a lab; only the identifying arguments differ. Keeping it one
    function is what makes a lab's PDF structurally the same document its members
    already receive.
    """
    categories = briefing._watched_categories(watch, allow=allow)
    today = timezone.now().date().isoformat()
    clusters = declared_clusters(interests)

    # Feed-level counts, kept for the cover's "what Mylo found" framing: these say
    # what the reader's pages currently hold, which is a different (and still true)
    # number from what the report chose to show.
    counts: dict[str, int] = {}
    new_counts: dict[str, int] = {}
    for category in categories:
        scores = briefing._suggested_scores(
            target_filter, briefing.CATEGORY_TYPES[category], reader=reader
        )
        counts[category] = len(scores)
        new_counts[category] = len(
            briefing.report_new_scores(briefing.filter_for_report(scores, today), today)
        )

    personal = _compile_part(
        target_filter,
        categories,
        today,
        key="personal",
        label=personal_label,
        kind="personal",
        cap=TOP_PERSONAL,
        reader=reader,
        clusters=clusters,
    )
    project_parts = [
        _compile_part(
            {"target_project": project},
            categories,
            today,
            key=str(project.id),
            label=project.name,
            kind="project",
            cap=TOP_PROJECT,
            reader=reader,
        )
        for project in projects
    ]

    daily = DailyBriefing.latest_for(**briefing_filter)
    narrative = getattr(daily, "narrative", None) or {}
    apply_narrative(personal, narrative)
    open_band = (
        _open_fellowships(target_filter, today, reader=reader)
        if "fellowships" in categories
        else []
    )

    data = ReportData(
        username=key,
        display_name=display_name,
        generated_on=today,
        briefing_markdown=getattr(daily, "body", "") or "",
        briefing_origin=getattr(daily, "origin", "") or "",
        categories=categories,
        lead=narrative.get("lead", ""),
        lead_origin=narrative.get("lead_origin", ""),
        open_fellowships=open_band,
        counts=counts,
        new_counts=new_counts,
        personal=personal,
        projects=project_parts,
        private_projects_hidden=hidden_projects,
        alerts=list(alerts or []),
    )
    # Computed last, from the finished report: every figure in the statistics
    # block is read off the parts above rather than re-queried, so the block and
    # the summary table cannot quote different totals for the same morning.
    stored = getattr(daily, "stats", None) if _is_today(daily, today) else None
    data.stats = (
        ReportStats.from_dict(stored)
        if stored
        else compile_stats(
            data,
            target_filter=target_filter,
            projects=projects,
            reader=reader,
            window_days=window_days,
            saved_content_ids=_saved_content_ids(reader, saves_filter),
        )
    )
    return data


def _is_today(briefing, today: str) -> bool:
    """Whether a stored briefing covers the day being compiled.

    Yesterday's statistics on today's document would be worse than none: the
    numbers would look authoritative and describe a different morning.
    """
    generated = getattr(briefing, "generated_on", None)
    return generated is not None and generated.isoformat() == today


def _alert_blocks(target_filter: dict) -> list:
    """Today's open alerts, as blocks. Imported lazily to keep the module acyclic."""
    from tools.delivery.alert_report import block_for, open_alerts

    return [block_for(alert) for alert in open_alerts(target_filter)]


def _user_window(user) -> int:
    """This person's deadline horizon, in days.

    Their own buffer, which is also the window the report's "deadlines inside N
    days" table uses, so the number in the heading and the rows under it are the
    same setting rather than two constants that drift.
    """
    watch = getattr(user, "watch", None)
    return int(
        getattr(watch, "deadline_buffer_days", None) or DEFAULT_DEADLINE_WINDOW_DAYS
    )


def _lab_window(lab) -> int:
    watch = getattr(lab, "watch", None)
    return int(
        getattr(watch, "deadline_buffer_days", None) or DEFAULT_DEADLINE_WINDOW_DAYS
    )


def compile_report_for_user(user) -> ReportData:
    """Gather one user's day into a :class:`ReportData` (read-only)."""
    return _compile(
        key=user.get_username(),
        display_name=user.get_full_name() or user.get_username(),
        watch=getattr(user, "watch", None),
        target_filter={"target_user": user},
        briefing_filter={"user": user},
        projects=briefing.report_projects_for_user(user),
        # One reader, so the PDF honours their manual ignores.
        reader=user,
        interests=getattr(getattr(user, "profile", None), "interests", None),
        window_days=_user_window(user),
        alerts=_alert_blocks({"target_user": user}),
    )


def compile_report_for_lab(lab) -> ReportData:
    """Gather one lab's day into a :class:`ReportData` (read-only).

    Narrowed to ``LAB_BRIEFING_CATEGORIES`` — the categories a lab is actually
    scored for — so its report never advertises a section it cannot fill, and broken
    out over the lab's own projects.

    The aggregate part carries the **lab's name**, not "Personal": a document whose
    contents page offers a reader "Personal" and then lists the lab's matches has
    mislabelled its own largest section.
    """
    return _compile(
        key=lab.slug,
        display_name=lab.name,
        watch=getattr(lab, "watch", None),
        target_filter={"target_lab": lab},
        briefing_filter={"lab": lab},
        projects=briefing.report_projects_for_lab(lab),
        hidden_projects=briefing.hidden_lab_projects(lab),
        allow=briefing.LAB_BRIEFING_CATEGORIES,
        personal_label=lab.name,
        interests=target_for_lab(lab).interests,
        window_days=_lab_window(lab),
        alerts=_alert_blocks({"target_lab": lab}),
        # A lab's deadline horizon covers what the *lab* saved. One member's
        # bookmark is not the lab's intention, and a lab post naming it would
        # publish a personal save to a channel.
        saves_filter={"target_lab": lab},
    )
