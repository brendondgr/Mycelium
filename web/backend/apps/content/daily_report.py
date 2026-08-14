"""Compile a day into the data the daily Discord PDF report renders from.

This is the *gather* half of the daily "Mylo Report" — as a DM to a person
(``apps.content.reminders_discord.send_personal_report``) and as an attachment to a
lab's channel (``apps.content.lab_digest.queue_lab_report``); the render half is
:mod:`.daily_report_pdf`, which is target-agnostic. It reads the same suggested
:class:`RelevanceScore` feeds the portal and the written briefing read — reusing
:mod:`apps.content.briefing`'s canonical readers, including its slate selection, so
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
    #: This item entered the reader's slate on this run — the report's "new" badge.
    is_new: bool
    cluster_label: str = ""


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
        """How many items the report calls new — the summary table's grand total."""
        return sum(part.total for part in self.parts)

    def summary_line(self) -> str:
        """A one-line 'what Mylo found' summary for the DM embed body.

        Counts what *entered* the reader's slate, not what the feeds hold — the DM
        says what changed, and the attachment shows the whole Top-25 it changed in.
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
        is_new=flat["is_entrant"],
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
    """One part's slate per category, plus how much of it is new."""
    counts: dict[str, int] = {}
    items: dict[str, list[ReportItem]] = {}
    slate_sizes: dict[str, int] = {}
    for category in categories:
        scores = briefing.report_scores(
            target_filter, briefing.CATEGORY_TYPES[category], today
        )
        counts[category] = len(briefing.report_new_scores(scores, today))
        slate_sizes[category] = len(scores)
        items[category] = [
            _item_from_score(s, category, today) for s in scores[:cap]
        ]
    return ReportPart(
        key=key,
        label=label,
        kind=kind,
        cap=cap,
        counts=counts,
        items=items,
        slate_sizes=slate_sizes,
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
        allow=briefing.LAB_BRIEFING_CATEGORIES,
        personal_label=lab.name,
    )
