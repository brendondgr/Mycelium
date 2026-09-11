"""Can this project actually make that deadline?

The question a researcher asks of a call for papers is never "is this venue
relevant" — they know their field. It is "given where I am, can I make it?" That
is arithmetic over three things Mycelium already stores: the venue's dated rounds
(:class:`~apps.content.models.ContentDeadline`), the project's milestones, and the
reader's own sense of how much runway they need
(:mod:`apps.content.timeline_settings`).

Six statuses, and the distinctions between them are the whole point:

``fits``
    The deadline lands at least a buffer's worth of days after the milestone that
    feeds it.
``tight``
    After the milestone, but inside the buffer. Still possible; say so, and say
    by how little.
``misses``
    Before the milestone. The work will not exist in time.
``not_viable``
    There is not enough runway to write the thing at all — fewer than the
    reader's minimum paper window between now (or the date a constraint lets them
    start) and the deadline. Distinct from ``misses`` on purpose: one is about
    this project's plan, the other about anyone's.
``no_milestone``
    The project has not dated the milestone this venue would be judged against.
    Mylo says so rather than guessing a date, because a guessed date produces a
    confident verdict about a plan that does not exist.
``rolling``
    The call has no date — continuous or rolling submission. Nothing to compute.

Plus an ``anticipated`` flag, carried from the deadline row's own confidence: a
date projected from last cycle is a different thing to plan against from a
published one, and a report that does not say which is quietly overstating what
it knows.

**Which milestone.** An abstract-only round is judged against ``results_by`` — an
abstract needs findings, not prose. A full-paper or application round is judged
against ``draft_by``. Getting this backwards is how a system tells someone a
venue fits because they will have results, when what the venue wants is a written
paper six weeks earlier.

**The window test is not applied to abstracts.** The minimum paper window is about
writing a paper; holding an abstract deadline to it would call every abstract-only
venue unviable, which is exactly wrong for the venues that are easiest to make.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from apps.content.models import ContentDeadline, SavedOpportunity
from apps.content.timeline_settings import Timeline, effective_timeline

FITS = "fits"
TIGHT = "tight"
MISSES = "misses"
NOT_VIABLE = "not_viable"
NO_MILESTONE = "no_milestone"
ROLLING = "rolling"

#: Which milestone kind each deadline kind is judged against, and whether the
#: minimum **paper** window applies to it.
_JUDGED_AGAINST: dict[str, tuple[str, bool]] = {
    SavedOpportunity.DeadlineKind.ABSTRACT: ("results_by", False),
    SavedOpportunity.DeadlineKind.MANUSCRIPT: ("draft_by", True),
    SavedOpportunity.DeadlineKind.APPLICATION: ("draft_by", True),
    SavedOpportunity.DeadlineKind.OTHER: ("draft_by", True),
}

#: An event date is when the conference happens, not when anything is due. It is
#: never a thing to plan a submission against, so it is not judged at all.
_IGNORED_KINDS = {SavedOpportunity.DeadlineKind.EVENT}


@dataclass
class TimelineRow:
    """One venue round, judged against one project's plan."""

    content_id: str
    venue: str
    deadline_kind: str
    round_label: str
    due_date: date | None
    status: str
    #: Days between the governing milestone and the deadline. Positive means the
    #: milestone lands first, which is the direction that leaves room to work.
    slack_days: int | None = None
    #: Days between today (or a constraint's earliest start) and the deadline.
    window_days: int | None = None
    buffer_days: int = 0
    min_window_days: int = 0
    buffer_source: str = ""
    window_source: str = ""
    #: The milestone this was judged against, when there was one.
    milestone_id: str = ""
    milestone_what: str = ""
    milestone_date: str = ""
    #: The date is projected from a previous cycle, not published.
    anticipated: bool = False
    #: A constraint pushed the earliest possible start, and which one.
    constraint_id: str = ""
    constraint_date: str = ""

    @property
    def is_reachable(self) -> bool:
        """Whether this is worth putting in front of the reader as an option."""
        return self.status in (FITS, TIGHT)

    def as_dict(self) -> dict:
        return {
            "content_id": self.content_id,
            "venue": self.venue,
            "deadline_kind": self.deadline_kind,
            "round_label": self.round_label,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "status": self.status,
            "slack_days": self.slack_days,
            "window_days": self.window_days,
            "buffer_days": self.buffer_days,
            "min_window_days": self.min_window_days,
            "buffer_source": self.buffer_source,
            "window_source": self.window_source,
            "milestone_id": self.milestone_id,
            "milestone_what": self.milestone_what,
            "milestone_date": self.milestone_date,
            "anticipated": self.anticipated,
            "constraint_id": self.constraint_id,
            "constraint_date": self.constraint_date,
        }


@dataclass
class ProjectPlan:
    """The half of a project's state the timeline matcher reads.

    Lifted out of the model so the matcher can be exercised — and reasoned about —
    without a database, which is what makes "changing the buffer recomputes
    everything" a testable claim rather than an aspiration.
    """

    milestones: list[dict] = field(default_factory=list)
    constraints: list[dict] = field(default_factory=list)

    @classmethod
    def from_project(cls, project) -> ProjectPlan:
        fast = getattr(getattr(project, "state", None), "fast", None) or {}
        return cls(
            milestones=list(fast.get("milestones") or []),
            constraints=list(fast.get("constraints") or []),
        )

    def milestone(self, kind: str) -> dict | None:
        """The **earliest dated** milestone of one kind.

        Earliest rather than latest: the question is when the work first exists,
        and a project with two dated drafts is ready at the first of them.
        """
        dated = [
            row
            for row in self.milestones
            if row.get("kind") == kind and row.get("date")
        ]
        return min(dated, key=lambda row: row["date"]) if dated else None

    def earliest_start(self) -> dict | None:
        """The latest ``earliest_start`` constraint — the one that actually binds.

        Two constraints saying "not before October" and "not before December" mean
        December; taking the first would report a viability the project does not
        have.
        """
        dated = [
            row
            for row in self.constraints
            if row.get("kind") == "earliest_start" and row.get("date")
        ]
        return max(dated, key=lambda row: row["date"]) if dated else None


def _venue_name(content) -> str:
    metadata = (getattr(content, "metadata", None) or {}) if content else {}
    return (
        metadata.get("title")
        or metadata.get("name")
        or metadata.get("series")
        or ""
    )


def judge_row(
    row: ContentDeadline,
    plan: ProjectPlan,
    timeline: Timeline,
    *,
    today: date,
) -> TimelineRow | None:
    """One deadline row against one plan. ``None`` when the row is not a deadline.

    Pure: every input is passed in, so the same row and plan always produce the
    same verdict, and a changed buffer produces a different one without any model
    being asked anything.
    """
    if row.kind in _IGNORED_KINDS:
        return None

    judged_against, applies_window = _JUDGED_AGAINST.get(row.kind, ("draft_by", True))
    verdict = TimelineRow(
        content_id=str(row.content_id or ""),
        venue=_venue_name(getattr(row, "content", None)),
        deadline_kind=row.kind,
        round_label=row.round_label or row.label or "",
        due_date=row.due_date,
        status=ROLLING,
        buffer_days=timeline.buffer_days,
        min_window_days=timeline.window_days,
        buffer_source=timeline.buffer_source,
        window_source=timeline.window_source,
        anticipated=row.confidence == ContentDeadline.Confidence.ANTICIPATED,
    )
    if row.due_date is None:
        # Rolling or unknown: there is no date, so there is nothing to compute.
        # Saying "rolling" is more useful than saying nothing, because a rolling
        # call is always makeable and that is the point of knowing.
        return verdict

    # The window is measured from the first day the project is *allowed* to
    # start, which a constraint can push past today ("no publication before the
    # pitch on 24 Oct"). Measuring from today would report runway the project
    # does not have.
    start = today
    constraint = plan.earliest_start()
    if constraint is not None:
        verdict.constraint_id = constraint.get("id", "")
        verdict.constraint_date = constraint.get("date", "")
        try:
            start = max(start, date.fromisoformat(constraint["date"]))
        except (KeyError, TypeError, ValueError):  # pragma: no cover - normalised
            pass
    verdict.window_days = (row.due_date - start).days

    if applies_window and verdict.window_days < timeline.window_days:
        # Not enough runway to write the thing, whatever this project's plan
        # says. A different claim from "misses", and a more final one.
        verdict.status = NOT_VIABLE
        return verdict

    milestone = plan.milestone(judged_against)
    if milestone is None:
        verdict.status = NO_MILESTONE
        return verdict

    verdict.milestone_id = milestone.get("id", "")
    verdict.milestone_what = milestone.get("what", "")
    verdict.milestone_date = milestone.get("date", "")
    verdict.slack_days = (row.due_date - date.fromisoformat(milestone["date"])).days

    if verdict.slack_days < 0:
        verdict.status = MISSES
    elif verdict.slack_days < timeline.buffer_days:
        verdict.status = TIGHT
    else:
        verdict.status = FITS
    return verdict


def timeline_rows(
    project,
    content_ids,
    *,
    reader=None,
    today: date | None = None,
    horizon_days: int | None = None,
) -> list[TimelineRow]:
    """Judge every dated round of ``content_ids`` against ``project``'s plan.

    ``reader`` decides whose buffer applies — a lab project in someone's personal
    report is judged by whether *they* can make the deadline.

    Rows come back sorted by date with undated (rolling) rows last, so a caller
    never has to re-sort what is meant to read as a timeline.
    """
    from django.utils import timezone

    today = today or timezone.localdate()
    if not content_ids:
        return []

    plan = ProjectPlan.from_project(project)
    timeline = effective_timeline(project, reader)

    queryset = ContentDeadline.objects.filter(
        content_id__in=list(content_ids)
    ).select_related("content")
    if horizon_days is not None:
        from datetime import timedelta

        # A rolling row has no date and must survive the horizon filter, or the
        # one status that always means "yes, any time" would vanish from a
        # bounded view.
        queryset = queryset.filter(
            due_date__isnull=True
        ) | queryset.filter(
            due_date__gte=today, due_date__lte=today + timedelta(days=horizon_days)
        )

    rows = [
        judged
        for row in queryset
        if (judged := judge_row(row, plan, timeline, today=today)) is not None
    ]
    rows.sort(key=lambda r: (r.due_date is None, r.due_date or today, r.venue))
    return rows
