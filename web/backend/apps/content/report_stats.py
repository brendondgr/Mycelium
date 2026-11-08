"""What Mylo actually found today, as numbers a reader can act on.

The Discord posts said one thing: a count per research theme. Not how much Mylo
read to get there, not how selective the match was, not where today's arrivals
landed, not what is due soon. A reader could see "Agentic KG — 5 papers" and had
no way to tell whether that was a heavy day filtered hard or a quiet day scraped
thin, which is exactly the judgement the number is supposed to support.

:class:`ReportStats` is that missing layer, and it is deliberately **derived from
the report's own structures** rather than re-queried. Every count here comes from
the same :class:`~apps.content.daily_report.ReportData` the document is rendered
from, so the statistics block and the summary table cannot disagree — the one
failure that would make both untrustworthy at once. The only outside reads are the
corpus-wide discovery totals (which belong to nobody in particular) and the
deadline horizon (which is a projection, not a slate).

Three rules the shape follows:

* **Visible only.** ``by_project`` lists what the surface is allowed to name. A
  lab post lists shared projects and reports the rest as a count (plan H4).
* **No scores.** No percentages, no cosines, no ranks-as-quality (plan H3). Every
  number here is a count of things or a count of days.
* **Honest about absence.** The discovery totals are ``None`` rather than ``0``
  when the analytics collector has nothing for the day: "Mylo read 0 new papers"
  and "Mylo does not know how many it read" are different statements, and only
  one of them is ever true.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from django.utils import timezone

#: Themes listed before a Discord field stops being scannable. Matches the
#: cluster ceiling the lab digest already used.
MAX_THEMES = 8

#: The daily's deadline horizon. Overridden per reader by their own buffer.
DEFAULT_DEADLINE_WINDOW_DAYS = 14


@dataclass
class ReportStats:
    """One run's numbers, for one target, on one surface."""

    #: Corpus-wide: what Mylo ingested overnight, for everyone. ``None`` when the
    #: analytics collector has no figure — see the module docstring.
    discovered_papers: int | None = None
    discovered_opportunities: int | None = None
    #: Distinct items that first matched this target or one of its visible
    #: projects on this run. Bigger than ``entered`` and much smaller than the
    #: feeds: it is the middle number that makes the other two legible.
    matched: int = 0
    #: Items that entered a top list. Equals the summary table's grand total, by
    #: construction — both are read off the same parts.
    entered: int = 0
    #: ``{category: (entered today, in the feed)}``.
    by_category: dict[str, tuple[int, int]] = field(default_factory=dict)
    #: ``[(label, entered, alerts)]`` — the reader's own part first, then each
    #: visible project.
    by_project: list[tuple[str, int, int]] = field(default_factory=list)
    #: What the first ``by_project`` row is called — "Personal" on a person's
    #: report, the lab's name on a lab's. Named rather than found by position, so
    #: a surface that wants projects only (a lab post, which already says the
    #: lab's totals above) can drop that row without counting.
    aggregate_label: str = ""
    #: ``[(label, entered)]``, busiest first, capped at :data:`MAX_THEMES`.
    by_theme: list[tuple[str, int]] = field(default_factory=list)
    alerts: int = 0
    deadline_window_days: int = DEFAULT_DEADLINE_WINDOW_DAYS
    deadlines_in_window: int = 0
    #: ``{title, url, due_date, days, label}`` for the nearest one, or ``None``.
    nearest_deadline: dict | None = None
    #: Lab surfaces only: how many projects this post is not naming.
    private_projects_hidden: int = 0

    @property
    def is_quiet(self) -> bool:
        """Whether this run has nothing to push (plan H7).

        "Nothing entered a top list and nothing raised an alert" — not "the feeds
        are empty". A reader with a settled Top-25 and a quiet Tuesday has plenty
        of matched items and no news, and a post restating yesterday's list is how
        a channel gets muted and a DM gets opted out of.
        """
        return not self.entered and not self.alerts

    @property
    def has_volume(self) -> bool:
        """Whether the overnight-volume sentence can be written at all."""
        return (
            self.discovered_papers is not None
            or self.discovered_opportunities is not None
        )

    def as_dict(self) -> dict:
        """The wire form stored on the briefing row and read back by every surface.

        Flat and boring on purpose: this is a contract between the nightly run and
        three renderers that run later. Add keys; do not reshape existing ones.
        """
        return {
            "discovered_papers": self.discovered_papers,
            "discovered_opportunities": self.discovered_opportunities,
            "matched": self.matched,
            "entered": self.entered,
            "by_category": {
                category: list(pair) for category, pair in self.by_category.items()
            },
            "by_project": [list(row) for row in self.by_project],
            "aggregate_label": self.aggregate_label,
            "by_theme": [list(row) for row in self.by_theme],
            "alerts": self.alerts,
            "deadline_window_days": self.deadline_window_days,
            "deadlines_in_window": self.deadlines_in_window,
            "nearest_deadline": self.nearest_deadline,
            "private_projects_hidden": self.private_projects_hidden,
        }

    @classmethod
    def from_dict(cls, payload: dict | None) -> ReportStats:
        """Read back what :meth:`as_dict` wrote, tolerating an older or empty row.

        Every field falls back to its default, so a briefing written before
        statistics existed reads as "no numbers" rather than raising in a renderer.
        """
        payload = payload or {}
        return cls(
            discovered_papers=payload.get("discovered_papers"),
            discovered_opportunities=payload.get("discovered_opportunities"),
            matched=int(payload.get("matched") or 0),
            entered=int(payload.get("entered") or 0),
            by_category={
                category: (int(pair[0]), int(pair[1]))
                for category, pair in (payload.get("by_category") or {}).items()
                if isinstance(pair, (list, tuple)) and len(pair) == 2
            },
            by_project=[
                (str(row[0]), int(row[1]), int(row[2]))
                for row in (payload.get("by_project") or [])
                if isinstance(row, (list, tuple)) and len(row) == 3
            ],
            by_theme=[
                (str(row[0]), int(row[1]))
                for row in (payload.get("by_theme") or [])
                if isinstance(row, (list, tuple)) and len(row) == 2
            ],
            aggregate_label=str(payload.get("aggregate_label") or ""),
            alerts=int(payload.get("alerts") or 0),
            deadline_window_days=int(
                payload.get("deadline_window_days") or DEFAULT_DEADLINE_WINDOW_DAYS
            ),
            deadlines_in_window=int(payload.get("deadlines_in_window") or 0),
            nearest_deadline=payload.get("nearest_deadline"),
            private_projects_hidden=int(payload.get("private_projects_hidden") or 0),
        )


# --------------------------------------------------------------------------- #
# Computing
# --------------------------------------------------------------------------- #
def discovery_totals(day: date) -> tuple[int | None, int | None]:
    """``(papers, opportunities)`` ingested corpus-wide on ``day``.

    Reuses the run-analytics collector rather than counting again: it already owns
    the definition of "discovered on a day" (a :class:`ContentItem` first created
    then), and two definitions of the same word is how the analytics report and the
    morning post end up quoting different figures for the same night.

    Returns ``(None, None)`` if the collector cannot answer — see the module
    docstring on why that is not zero.
    """
    try:
        from apps.content.run_analytics import collect_discovery

        counts = collect_discovery(day).counts
    except Exception:  # noqa: BLE001 — a statistic must never sink a report
        return None, None
    papers = counts.get("papers")
    opportunities = sum(
        int(counts.get(category) or 0)
        for category in ("grants", "fellowships", "conferences")
    )
    return (None if papers is None else int(papers)), opportunities


def _entered_by_category(data, categories: list[str]) -> dict[str, int]:
    """Each category's column total in the summary table.

    Summed over every part — the reader's own and each project — because that is
    what the table's column adds up to, and the statistics block exists to be
    reconciled against the table rather than against a second query (plan S7).
    """
    return {
        category: sum(part.counts.get(category, 0) for part in data.parts)
        for category in categories
    }


def _matched_today(target_filter: dict, projects: list, today: str, *, reader) -> int:
    """Distinct items that first matched this target or its projects on this run.

    ``first_seen`` is the per-target record of when an item first reached this
    reader, so it answers "what is new to *you* today" without depending on when
    the item was crawled. Distinct across categories and across projects, because
    one paper matching a person and two of their projects is one paper found.
    """
    from apps.content.briefing import CATEGORY_TYPES, _suggested_scores

    seen: set = set()
    filters = [target_filter] + [{"target_project": project} for project in projects]
    for one in filters:
        for content_type in CATEGORY_TYPES.values():
            for score in _suggested_scores(one, content_type, reader=reader):
                if (score.signals or {}).get("first_seen") == today:
                    seen.add(score.content_id)
    return len(seen)


def _deadline_horizon(
    content_ids: set, today: date, window_days: int
) -> tuple[int, dict | None]:
    """How many dated rounds fall inside the window, and the nearest one.

    Read from :class:`~tools.retrieval.models.ContentDeadline`, the projection the
    feeds and reminders already share, so "due Friday" means the same thing in a
    Discord post as it does on a card. Rolling and unknown rounds carry no date
    and are simply not in the window — Mylo says nothing rather than guessing.
    """
    from tools.retrieval.models import ContentDeadline

    if not content_ids:
        return 0, None
    rows = list(
        ContentDeadline.objects.filter(
            content_id__in=content_ids,
            due_date__gte=today,
            due_date__lte=today + timedelta(days=window_days),
        )
        .select_related("content")
        .order_by("due_date", "kind", "round_key")
    )
    if not rows:
        return 0, None
    first = rows[0]
    metadata = (first.content.metadata or {}) if first.content_id else {}
    nearest = {
        "title": metadata.get("title") or metadata.get("name") or "",
        "url": first.content.source_url if first.content_id else "",
        "due_date": first.due_date.isoformat(),
        "days": (first.due_date - today).days,
        "label": first.round_label or first.label or first.get_kind_display(),
    }
    return len(rows), nearest


def open_alert_counts(target_filter: dict, day: date) -> dict[str, int]:
    """``{project id: open alerts}`` for one target on one day.

    Open only. A held alert is real and will reach the reader on Monday, but it
    is deliberately not being shouted about today, and counting it in "needs your
    attention (4)" beside three shown lines would make the cap look broken.
    """
    from tools.retrieval.models import ProjectAlert

    rows = ProjectAlert.objects.filter(
        **target_filter, fired_on=day, status=ProjectAlert.Status.OPEN
    ).values_list("project_id", flat=True)
    counts: dict[str, int] = {}
    for project_id in rows:
        key = str(project_id)
        counts[key] = counts.get(key, 0) + 1
    return counts


def compile_stats(
    data,
    *,
    target_filter: dict,
    projects: list,
    reader=None,
    window_days: int = DEFAULT_DEADLINE_WINDOW_DAYS,
    saved_content_ids: set | None = None,
    alerts_by_project: dict[str, int] | None = None,
) -> ReportStats:
    """Derive one run's statistics from the report that was just compiled.

    ``data`` is the :class:`~apps.content.daily_report.ReportData`; everything that
    can be read off it is, so the numbers cannot drift from the document. The
    deadline horizon covers the slate's items plus anything the reader saved,
    which is the set a reader would consider "mine" — a saved call with a date
    next week matters whether or not it is still in a top list this morning.
    """
    today_date = timezone.localdate()
    today = today_date.isoformat()
    if alerts_by_project is None:
        alerts_by_project = open_alert_counts(target_filter, today_date)

    entered_by_category = _entered_by_category(data, data.categories)
    papers, opportunities = discovery_totals(today_date)

    slate_ids = {
        item.content_id
        for part in data.parts
        for items in part.items.values()
        for item in items
        if getattr(item, "content_id", None)
    }
    horizon_ids = slate_ids | set(saved_content_ids or set())
    in_window, nearest = _deadline_horizon(horizon_ids, today_date, window_days)

    themes = sorted(
        (
            (section.label, section.entrant_count)
            for section in (data.personal.themes if data.personal else [])
            if section.entrant_count
        ),
        key=lambda row: (-row[1], row[0]),
    )[:MAX_THEMES]

    by_project = [
        (part.label, part.total, int(alerts_by_project.get(part.key, 0)))
        for part in data.parts
    ]

    return ReportStats(
        discovered_papers=papers,
        discovered_opportunities=opportunities,
        matched=_matched_today(target_filter, projects, today, reader=reader),
        entered=sum(entered_by_category.values()),
        by_category={
            category: (entered_by_category[category], data.counts.get(category, 0))
            for category in data.categories
        },
        by_project=by_project,
        aggregate_label=data.personal.label if data.personal else "",
        by_theme=themes,
        alerts=sum(alerts_by_project.values()),
        deadline_window_days=window_days,
        deadlines_in_window=in_window,
        nearest_deadline=nearest,
        private_projects_hidden=data.private_projects_hidden,
    )


def record_run_stats(briefing, data=None):
    """Compute this run's statistics for a saved briefing and store them on it.

    Called once per target per run, right after the briefing is written, so the
    numbers are settled before anything reads them. Every later surface — the web
    header, the Discord post, the PDF — reads them **back off the row** rather than
    deriving its own, which is the only way three renderers running minutes apart
    can be guaranteed to quote the same morning.

    Never raises. A statistic is a nicety; a briefing is the product, and a
    failure here must not cost a reader their report.
    """
    from apps.content.daily_report import (
        compile_report_for_lab,
        compile_report_for_user,
    )

    try:
        if data is None:
            owner = briefing.user or briefing.lab
            data = (
                compile_report_for_user(owner)
                if briefing.user_id
                else compile_report_for_lab(owner)
            )
        briefing.stats = data.stats.as_dict()
        briefing.save(update_fields=["stats", "generated_at"])
    except Exception:  # noqa: BLE001 — a statistic must never sink a report
        import logging

        logging.getLogger(__name__).warning(
            "could not record run statistics for briefing %s",
            getattr(briefing, "id", "?"),
            exc_info=True,
        )
    return briefing
