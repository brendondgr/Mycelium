"""Which of today's findings actually change what a project should do.

The gap this closes is between *relevant* and *actionable*. A feed is full of
relevant papers, and a daily report that lists them is a daily report people stop
opening. An alert makes a much stronger claim — something happened to **this
project** and here is what to do about it — so it fires far more rarely, and
everything about this module is about keeping that claim true.

**Five triggers**, in the priority the cap spends its budget on:

1. ``deadline_moved`` on a saved item due inside the buffer. Time-critical and
   purely factual; nothing to calibrate, and the only trigger allowed to reach a
   weekly-cadence reader between Mondays.
2. ``overlap_risk`` — someone published close to what the project claims is new.
3. ``unblocks`` — something on offer closes a stated blocker.
4. ``timeline`` — a venue just became reachable from the next milestone.
5. ``team_gap`` — a call requires expertise nobody on the team states.

**Three at most, per target, per day** (``PROJECT_ALERT_DAILY_CAP``). The cap is a
product decision rather than a performance one: four things that all need
attention today produce a reader who attends to none of them. Overflow is not
dropped — it is marked ``held`` and the Monday weekly picks it up, so nothing is
lost, it is just not shouted.

**Once per (target, project, item, trigger), forever.** Enforced by a database
constraint, not a query. The weekly then reports what *happened* to an
already-alerted item rather than raising it again.

**Two triggers do not wait for calibration.** ``timeline`` and ``deadline_moved``
are arithmetic over stored dates and are correct today. The three that rest on a
similarity threshold are gated behind ``PROJECT_ALERTS_ENABLED`` until a
calibration run has set those thresholds against measured alert precision (plan
3.8) — a threshold chosen by taste fires constantly or never, and both teach a
reader to stop reading.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from django.conf import settings
from django.db import IntegrityError
from django.utils import timezone
from tools.retrieval.models import ContentDeadline, ProjectAlert

from apps.content.matchers import blockers as blocker_matcher
from apps.content.matchers import known_literature as known_matcher
from apps.content.matchers import overlap as overlap_matcher
from apps.content.matchers import team_gap as team_matcher
from apps.content.matchers import timeline as timeline_matcher

#: The order the daily cap spends its budget in. Time-critical first, then the
#: two that change what a reader should *write*, then the two that change what
#: they should *plan*.
TRIGGER_PRIORITY = (
    ProjectAlert.Trigger.DEADLINE_MOVED,
    ProjectAlert.Trigger.OVERLAP_RISK,
    ProjectAlert.Trigger.UNBLOCKS,
    ProjectAlert.Trigger.TIMELINE,
    ProjectAlert.Trigger.TEAM_GAP,
)

#: Triggers that are arithmetic rather than similarity, and therefore correct
#: before any calibration run. They fire whatever ``PROJECT_ALERTS_ENABLED`` says.
DETERMINISTIC_TRIGGERS = frozenset(
    {ProjectAlert.Trigger.TIMELINE, ProjectAlert.Trigger.DEADLINE_MOVED}
)


@dataclass
class Candidate:
    """One alert that could fire, before the cap and the once-ever rule."""

    project: object
    content: object
    trigger: str
    evidence: dict = field(default_factory=dict)

    @property
    def rank(self) -> int:
        try:
            return TRIGGER_PRIORITY.index(self.trigger)
        except ValueError:  # pragma: no cover - a trigger not in the list
            return len(TRIGGER_PRIORITY)


@dataclass
class AlertRun:
    """What one evaluation produced, for the run log and the tests."""

    considered: int = 0
    fired: int = 0
    held: int = 0
    duplicates: int = 0
    skipped_disabled: int = 0

    def as_dict(self) -> dict:
        return {
            "considered": self.considered,
            "fired": self.fired,
            "held": self.held,
            "duplicates": self.duplicates,
            "skipped_disabled": self.skipped_disabled,
        }


def _enabled(trigger: str) -> bool:
    """Whether this trigger may fire today."""
    if trigger in DETERMINISTIC_TRIGGERS:
        return True
    return bool(getattr(settings, "PROJECT_ALERTS_ENABLED", False))


# --------------------------------------------------------------------------- #
# The five triggers
# --------------------------------------------------------------------------- #
def developments_for(project, reader) -> dict[str, tuple[str, ...]]:
    """What conversation says changed about this project, by kind of change.

    Only developments in effect — told to Mylo, or confirmed — and only those
    this reader may know: lab-visible ones, plus a person's own private ones in
    their own report (``apps.ambient.read.developments_in_effect``).
    """
    from django.contrib.auth import get_user_model

    from apps.ambient.read import developments_in_effect

    person = reader if isinstance(reader, get_user_model()) else None
    out: dict[str, list[str]] = {}
    for row in developments_in_effect(
        project, reader=person, changes=("blocker_closed", "method_dropped")
    ):
        out.setdefault(row.change, []).append(row.topic)
    return {change: tuple(topics) for change, topics in out.items()}


def overlap_candidates(
    project, precis_by_content, contents, *, dropped_methods: tuple[str, ...] = ()
) -> list[Candidate]:
    out = []
    for verdict in overlap_matcher.overlap_rows(
        project, precis_by_content, dropped_methods=dropped_methods
    ):
        if not verdict.fires():
            continue
        content = contents.get(verdict.content_id)
        if content is None:
            continue
        out.append(
            Candidate(
                project=project,
                content=content,
                trigger=ProjectAlert.Trigger.OVERLAP_RISK,
                evidence=verdict.as_dict(),
            )
        )
    return out


def blocker_candidates(
    project, precis_by_content, contents, *, closed: tuple[str, ...] = ()
) -> list[Candidate]:
    out = []
    seen: set[str] = set()
    for match in blocker_matcher.blocker_rows(
        project, precis_by_content, closed=closed
    ):
        # One alert per item, not per (item, blocker): a dataset closing two
        # blockers at once is one piece of good news, and saying it twice makes
        # it read like two.
        if not match.fires() or match.content_id in seen:
            continue
        content = contents.get(match.content_id)
        if content is None:
            continue
        seen.add(match.content_id)
        out.append(
            Candidate(
                project=project,
                content=content,
                trigger=ProjectAlert.Trigger.UNBLOCKS,
                evidence=match.as_dict(),
            )
        )
    return out


def timeline_candidates(
    project, contents, *, reader=None, today: date | None = None
) -> list[Candidate]:
    """Venues that just became reachable from this project's next milestone.

    ``fits`` only, not ``tight``: "you could just about make this" is a line in
    the report's venue section, not a reason to interrupt someone's morning.
    """
    rows = timeline_matcher.timeline_rows(
        project, list(contents), reader=reader, today=today
    )
    out = []
    for row in rows:
        if row.status != timeline_matcher.FITS:
            continue
        content = contents.get(row.content_id)
        if content is None:
            continue
        out.append(
            Candidate(
                project=project,
                content=content,
                trigger=ProjectAlert.Trigger.TIMELINE,
                evidence=row.as_dict(),
            )
        )
    return out


def deadline_moved_candidates(
    project, saved_content_ids, *, buffer_days: int, today: date
) -> list[Candidate]:
    """Deadlines that moved on something the reader saved and is due soon.

    Narrow on purpose (open decision OD2): saved, dated, inside the buffer, and
    *changed*. This is the one alert that can reach a weekly-cadence reader
    between Mondays, so it earns that by being the one case where waiting until
    Monday costs something irreversible.
    """
    if not saved_content_ids:
        return []
    rows = ContentDeadline.objects.filter(
        content_id__in=list(saved_content_ids),
        changed_at__isnull=False,
        due_date__gte=today,
        due_date__lte=today + timedelta(days=buffer_days),
    ).select_related("content")
    out = []
    for row in rows:
        if row.previous_due_date is None or row.previous_due_date == row.due_date:
            continue
        out.append(
            Candidate(
                project=project,
                content=row.content,
                trigger=ProjectAlert.Trigger.DEADLINE_MOVED,
                evidence={
                    "due_date": row.due_date.isoformat(),
                    "previous_due_date": row.previous_due_date.isoformat(),
                    "days": (row.due_date - today).days,
                    "round_label": row.round_label or row.label or "",
                    "moved_earlier": row.due_date < row.previous_due_date,
                },
            )
        )
    return out


def team_gap_candidates(project, target_filter, contents) -> list[Candidate]:
    out = []
    seen: set[str] = set()
    for gap in team_matcher.team_gaps(target_filter, list(contents.values())):
        if not gap.is_gap or gap.content_id in seen:
            continue
        content = contents.get(gap.content_id)
        if content is None:
            continue
        seen.add(gap.content_id)
        out.append(
            Candidate(
                project=project,
                content=content,
                trigger=ProjectAlert.Trigger.TEAM_GAP,
                evidence=gap.as_dict(),
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Deciding and persisting
# --------------------------------------------------------------------------- #
def rank_candidates(candidates: list[Candidate]) -> list[Candidate]:
    """Trigger priority first, then strongest evidence within a trigger."""

    def key(candidate: Candidate):
        evidence = candidate.evidence or {}
        strength = evidence.get("score")
        if strength is None:
            strength = evidence.get("claim_similarity", 0.0)
        # A moved deadline's urgency is how few days are left, so fewer sorts
        # first — inverted here so one comparator serves both kinds of evidence.
        if candidate.trigger == ProjectAlert.Trigger.DEADLINE_MOVED:
            strength = 1.0 / (1 + max(evidence.get("days", 0), 0))
        return (candidate.rank, -float(strength or 0.0))

    return sorted(candidates, key=key)


def persist(candidates: list[Candidate], target_filter: dict, *, today: date,
            cap: int | None = None) -> AlertRun:
    """Write the day's alerts, capped, skipping any that ever fired before.

    The cap decides *status*, not existence: everything above it is stored as
    ``held`` so the Monday weekly can pick it up. Dropping the overflow would mean
    a reader never hears about the fourth thing at all, which is a worse answer
    than hearing about it on Monday.
    """
    limit = settings.PROJECT_ALERT_DAILY_CAP if cap is None else cap
    run = AlertRun(considered=len(candidates))
    fired = 0
    for candidate in rank_candidates(candidates):
        if not _enabled(candidate.trigger):
            run.skipped_disabled += 1
            continue
        status = (
            ProjectAlert.Status.OPEN if fired < limit else ProjectAlert.Status.HELD
        )
        try:
            _row, created = ProjectAlert.objects.get_or_create(
                **target_filter,
                project=candidate.project,
                content=candidate.content,
                trigger=candidate.trigger,
                defaults={
                    "evidence": candidate.evidence,
                    "fired_on": today,
                    "status": status,
                },
            )
        except IntegrityError:  # pragma: no cover - raced with another run
            run.duplicates += 1
            continue
        if not created:
            # Fired before. The weekly reports what happened to it since; it is
            # never raised a second time (plan 6.6).
            run.duplicates += 1
            continue
        if status == ProjectAlert.Status.OPEN:
            fired += 1
            run.fired += 1
        else:
            run.held += 1
    return run


def evaluate_for_user(user, *, today: date | None = None) -> AlertRun:
    """Every alert one person's projects earn today."""
    from apps.content.briefing import report_projects_for_user

    today = today or timezone.localdate()
    return _evaluate(
        target_filter={"target_user": user},
        projects=report_projects_for_user(user),
        reader=user,
        today=today,
    )


def evaluate_for_lab(lab, *, today: date | None = None) -> AlertRun:
    """Every alert a lab's **shared** projects earn today.

    Shared only: a lab alert reaches the lab's channel and every member's lab
    report, and an unshared project's name does not belong on either (plan 0.2).
    """
    from apps.content.briefing import report_projects_for_lab

    today = today or timezone.localdate()
    return _evaluate(
        target_filter={"target_lab": lab},
        projects=report_projects_for_lab(lab),
        reader=lab,
        today=today,
    )


def _candidate_contents(project, reader) -> tuple[dict, dict]:
    """``({content_id: item}, {content_id: précis})`` for one project's slate.

    The slate, not the feed: an alert is about something that surfaced, and a
    matcher walking the whole accumulated feed would raise an alert about a paper
    from March on the day a project first states a blocker.
    """
    from tools.recommendation.models import ItemComprehension

    from apps.content.briefing import CATEGORY_TYPES, report_scores

    today = timezone.localdate().isoformat()
    contents: dict = {}
    for content_type in CATEGORY_TYPES.values():
        for score in report_scores({"target_project": project}, content_type, today):
            contents[str(score.content_id)] = score.content
    if not contents:
        return {}, {}

    known = known_matcher.known_literature(project, reader)
    precis_by_content: dict = {}
    rows = ItemComprehension.objects.filter(content_id__in=list(contents))
    for precis in rows:
        key = str(precis.content_id)
        is_known, revised, _how = known.verdict(contents[key], precis)
        # A paper the team already has is not news — unless it was revised, which
        # is the one case where re-surfacing something known is right.
        if is_known and not revised:
            contents.pop(key, None)
            continue
        precis_by_content[key] = precis
    return contents, precis_by_content


def _evaluate(*, target_filter: dict, projects: list, reader, today: date) -> AlertRun:
    from tools.retrieval.models import SavedOpportunity

    from apps.content.timeline_settings import effective_timeline

    total = AlertRun()
    candidates: list[Candidate] = []
    saves_filter = (
        {"target_lab": reader}
        if "target_lab" in target_filter
        else {"user": reader, "target_lab": None}
    )
    saved_ids = set(
        SavedOpportunity.objects.filter(**saves_filter)
        .exclude(content__isnull=True)
        .values_list("content_id", flat=True)
    )

    for project in projects:
        contents, precis_by_content = _candidate_contents(project, reader)
        if not contents:
            continue
        timeline = effective_timeline(project, reader)
        changed = developments_for(project, reader)
        candidates.extend(
            overlap_candidates(
                project,
                precis_by_content,
                contents,
                dropped_methods=changed.get("method_dropped", ()),
            )
        )
        candidates.extend(
            blocker_candidates(
                project,
                precis_by_content,
                contents,
                closed=changed.get("blocker_closed", ()),
            )
        )
        candidates.extend(
            timeline_candidates(project, contents, reader=reader, today=today)
        )
        candidates.extend(
            deadline_moved_candidates(
                project,
                saved_ids & {str(key) for key in contents},
                buffer_days=timeline.buffer_days,
                today=today,
            )
        )
        candidates.extend(team_gap_candidates(project, target_filter, contents))

    written = persist(candidates, target_filter, today=today)
    # The bell, for every cadence. Cadence governs Discord and nothing else, and
    # this is the surface that makes that true (plan 3.7).
    from apps.content.alert_report import notify, open_alerts

    notify(open_alerts(target_filter, today))
    total.considered = written.considered
    total.fired = written.fired
    total.held = written.held
    total.duplicates = written.duplicates
    total.skipped_disabled = written.skipped_disabled
    return total
