"""Compile a day into the data the daily Discord PDF report renders from.

This is the *gather* half of the daily "Mylo Report" — as a DM to a person
(``apps.content.reminders_discord.send_personal_report``) and as an attachment to a
lab's channel (``apps.content.lab_digest.queue_lab_report``); the render half is
:mod:`.daily_report_pdf`, which is target-agnostic. It reads the same suggested
:class:`RelevanceScore` feeds the portal and the written briefing read — reusing
:mod:`apps.content.briefing`'s canonical readers, including its report narrowing
(new today, above the relevance floor), so the PDF can never drift from what the
written report says — and shapes them into a :class:`ReportData`:

* a **Personal** part, each watched category capped at :data:`TOP_PERSONAL`,
* one part **per project** the reader is on, each category capped at
  :data:`TOP_PROJECT`,
* the day's per-category feed counts (and how many first surfaced today), and
* the freshest written :class:`DailyBriefing` body (the report's main section).

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

from apps.content import briefing
from apps.content.models import DailyBriefing, RelevanceScore

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
    match_percent: int | None
    headline: str
    reason: str
    source: str
    deadline_date: str
    is_new: bool
    cluster_label: str = ""


@dataclass
class ReportPart:
    """One part of the report — Personal, or one project — rendered as a section.

    ``counts`` is how many new, above-threshold items the part has per category
    (the number its summary-table cell shows, uncapped); ``items`` is the capped
    slice the PDF lists under the part's headings.
    """

    key: str
    label: str
    kind: str  # "personal" | "project"
    cap: int
    counts: dict[str, int] = field(default_factory=dict)
    items: dict[str, list[ReportItem]] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.counts.values())


@dataclass
class ReportData:
    """Everything the PDF and the summary DM need for one user."""

    username: str
    display_name: str
    generated_on: str
    briefing_markdown: str
    briefing_origin: str
    categories: list[str]
    counts: dict[str, int] = field(default_factory=dict)
    new_counts: dict[str, int] = field(default_factory=dict)
    personal: ReportPart | None = None
    projects: list[ReportPart] = field(default_factory=list)

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
        """How many items the report actually shows — the table's grand total."""
        return sum(part.total for part in self.parts)

    def summary_line(self) -> str:
        """A one-line 'what Mylo found' summary for the DM embed body.

        Counts what the report *shows* (new today and above the relevance floor),
        not what the feeds hold, so the DM and the attachment never disagree.
        """
        personal = self.personal.counts if self.personal is not None else {}
        parts = [
            f"{personal[category]} "
            f"{CATEGORY_LABELS.get(category, category.title()).lower()}"
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
        return ", ".join(
            p for p in (_clean(meta.get("location")), _clean(meta.get("country"))) if p
        )
    # grants + fellowships
    return _clean(meta.get("sponsor")) or _clean(meta.get("funder"))


def _clean(value) -> str:
    return " ".join(str(value).split()) if value else ""


def _item_from_score(score: RelevanceScore, category: str, today: str) -> ReportItem:
    flat = briefing._showcase_item(score, today)
    meta = score.content.metadata or {}
    return ReportItem(
        type=flat["type"],
        category=category,
        title=flat["title"],
        url=flat["url"],
        match_percent=flat["match_percent"],
        headline=flat["headline"],
        reason=flat["reason"],
        source=_source_line(flat["type"], meta),
        deadline_date=flat["deadline_date"],
        is_new=flat["is_new"],
        cluster_label=flat["cluster_label"],
    )


def _compile_part(
    target_filter: dict,
    categories: list[str],
    today: str,
    *,
    key: str,
    label: str,
    kind: str,
    cap: int,
) -> ReportPart:
    """One part's per-category counts and capped item lists."""
    counts: dict[str, int] = {}
    items: dict[str, list[ReportItem]] = {}
    for category in categories:
        scores = briefing.report_scores(
            target_filter, briefing.CATEGORY_TYPES[category], today
        )
        counts[category] = len(scores)
        items[category] = [
            _item_from_score(s, category, today) for s in scores[:cap]
        ]
    return ReportPart(
        key=key, label=label, kind=kind, cap=cap, counts=counts, items=items
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

    # Feed-level counts, kept for the cover's "what Mylo found" framing: these say
    # what the reader's pages currently hold, which is a different (and still true)
    # number from what the report chose to show.
    counts: dict[str, int] = {}
    new_counts: dict[str, int] = {}
    for category in categories:
        scores = briefing._suggested_scores(
            target_filter, briefing.CATEGORY_TYPES[category]
        )
        counts[category] = len(scores)
        new_counts[category] = sum(
            1 for s in scores if briefing._is_new_today(s.signals, today)
        )

    personal = _compile_part(
        target_filter,
        categories,
        today,
        key="personal",
        label="Personal",
        kind="personal",
        cap=TOP_PERSONAL,
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
        )
        for project in projects
    ]

    daily = DailyBriefing.latest_for(**briefing_filter)

    return ReportData(
        username=key,
        display_name=display_name,
        generated_on=today,
        briefing_markdown=getattr(daily, "body", "") or "",
        briefing_origin=getattr(daily, "origin", "") or "",
        categories=categories,
        counts=counts,
        new_counts=new_counts,
        personal=personal,
        projects=project_parts,
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
    )


def compile_report_for_lab(lab) -> ReportData:
    """Gather one lab's day into a :class:`ReportData` (read-only).

    Narrowed to ``LAB_BRIEFING_CATEGORIES`` — the categories a lab is actually
    scored for — so its report never advertises a section it cannot fill, and broken
    out over the lab's own projects.
    """
    return _compile(
        key=lab.slug,
        display_name=lab.name,
        watch=getattr(lab, "watch", None),
        target_filter={"target_lab": lab},
        briefing_filter={"lab": lab},
        projects=briefing.report_projects_for_lab(lab),
        allow=briefing.LAB_BRIEFING_CATEGORIES,
    )
