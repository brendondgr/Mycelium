"""Compile a day into the data the daily Discord PDF report renders from.

This is the *gather* half of the daily "Mylo Report" — as a DM to a person
(``apps.content.reminders_discord.send_personal_report``) and as an attachment to a
lab's channel (``apps.content.lab_digest.queue_lab_report``); the render half is
:mod:`.daily_report_pdf`, which is target-agnostic. It reads the same suggested
:class:`RelevanceScore` feeds the portal and the written briefing read — reusing
:mod:`apps.content.briefing`'s canonical readers so the PDF can never drift from
what the app shows — and shapes them into a :class:`ReportData`:

* the day's per-category counts (and how many first surfaced today),
* the **top 25 articles**,
* a **combined top 25 across grants / fellowships / conferences** the user watches,
* the full per-category lists for the appendix, and
* the freshest written :class:`DailyBriefing` body (the report's main section).

Everything is pure and read-only; the command in
``management/commands/send_daily_discord_reports.py`` drives compile → render →
send → cleanup over the eligible users.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.utils import timezone

from apps.content import briefing
from apps.content.models import DailyBriefing, RelevanceScore

#: The article section is the top-N papers; the opportunity section is a combined
#: top-N across the three opportunity categories.
TOP_PAPERS = 25
TOP_OPPORTUNITIES = 25

#: The opportunity categories that share the combined top-25 section, in the order
#: ties are broken for display.
OPPORTUNITY_CATEGORIES: tuple[str, ...] = ("grants", "fellowships", "conferences")

#: Human labels for each category, used in the PDF headings and the DM summary.
CATEGORY_LABELS: dict[str, str] = {
    "papers": "Papers",
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
    top_papers: list[ReportItem] = field(default_factory=list)
    top_opportunities: list[ReportItem] = field(default_factory=list)
    all_items: dict[str, list[ReportItem]] = field(default_factory=dict)

    @property
    def total_count(self) -> int:
        return sum(self.counts.values())

    @property
    def total_new(self) -> int:
        return sum(self.new_counts.values())

    def summary_line(self) -> str:
        """A one-line 'what Mylo found' summary for the DM embed body."""
        parts = []
        for category in self.categories:
            count = self.counts.get(category, 0)
            if not count:
                continue
            new = self.new_counts.get(category, 0)
            label = CATEGORY_LABELS.get(category, category.title()).lower()
            suffix = f" ({new} new)" if new else ""
            parts.append(f"{count} {label}{suffix}")
        if not parts:
            return "No new matches today — Mylo will keep watching."
        return "Mylo found " + ", ".join(parts) + "."


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


def _opportunity_sort_key(item: ReportItem):
    match = item.match_percent if isinstance(item.match_percent, int) else -1
    # New first, then strongest match, then soonest real deadline.
    return (0 if item.is_new else 1, -match, item.deadline_date or "9999-99-99")


def _compile(
    *,
    key: str,
    display_name: str,
    watch,
    target_filter: dict,
    briefing_filter: dict,
    allow: tuple[str, ...] | None = None,
) -> ReportData:
    """The shared gather, over whatever target the two public compilers name.

    Everything here — which categories are watched, which suggested scores to read,
    which written briefing to attach — is the same work for a person and for a lab;
    only the four identifying arguments differ. Keeping it one function is what makes
    a lab's PDF structurally the same document its members already receive.
    """
    categories = briefing._watched_categories(watch, allow=allow)
    today = timezone.now().date().isoformat()

    counts: dict[str, int] = {}
    new_counts: dict[str, int] = {}
    all_items: dict[str, list[ReportItem]] = {}
    for category in categories:
        content_type = briefing.CATEGORY_TYPES[category]
        scores = briefing._suggested_scores(target_filter, content_type)
        items = [_item_from_score(s, category, today) for s in scores]
        counts[category] = len(items)
        new_counts[category] = sum(1 for it in items if it.is_new)
        all_items[category] = items

    top_papers = all_items.get("papers", [])[:TOP_PAPERS]

    opportunities: list[ReportItem] = []
    for category in OPPORTUNITY_CATEGORIES:
        if category in all_items:
            opportunities.extend(all_items[category])
    opportunities.sort(key=_opportunity_sort_key)
    top_opportunities = opportunities[:TOP_OPPORTUNITIES]

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
        top_papers=top_papers,
        top_opportunities=top_opportunities,
        all_items=all_items,
    )


def compile_report_for_user(user) -> ReportData:
    """Gather one user's day into a :class:`ReportData` (read-only)."""
    return _compile(
        key=user.get_username(),
        display_name=user.get_full_name() or user.get_username(),
        watch=getattr(user, "watch", None),
        target_filter={"target_user": user},
        briefing_filter={"user": user},
    )


def compile_report_for_lab(lab) -> ReportData:
    """Gather one lab's day into a :class:`ReportData` (read-only).

    Narrowed to ``LAB_BRIEFING_CATEGORIES`` — the categories a lab is actually
    scored for — so its report never advertises a section it cannot fill.
    """
    return _compile(
        key=lab.slug,
        display_name=lab.name,
        watch=getattr(lab, "watch", None),
        target_filter={"target_lab": lab},
        briefing_filter={"lab": lab},
        allow=briefing.LAB_BRIEFING_CATEGORIES,
    )
