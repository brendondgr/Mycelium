"""Measure what one nightly run actually did.

The daily run used to announce itself with a single line — "all stages finished"
— which confirms the pipeline did not crash and says nothing about whether it was
worth running. This module is the measurement half of the replacement: it reads
the rows the run just wrote and turns them into the numbers an operator needs to
answer "is this system earning its keep, and where is it straining?".

Five groups, matching the questions worth asking:

* **Coverage** — how many users, labs, departments, and projects the run was
  actually for. This is recomputed from the same selectors the pipeline itself
  uses (:func:`tools.recommendation.tasks.select_users` / ``select_targets``), not from
  a
  count of rows written, so a run that covered ten labs and produced nothing for
  three of them still reports ten.
* **Discovery** — how much genuinely new content entered the store. Re-scraping a
  known item upserts it in place, so ``created_at`` on the day is exactly the
  count of items the world gained, not the count the scrapers touched.
* **Recommendations** — how much of that discovery Mylo actually put in front of
  someone, split by category and by the kind of target it was matched to.
* **LLM** — calls, failures, and token spend per component, from the ledger
  :mod:`apps.core.llm_usage` writes as the calls happen.
* **Delivery** — briefings written versus reports that reached Discord.
* **Collaboration** — searches, what they returned, feedback, the appearance
  cap, and the harm checks (collaboration-network plan CN-08). Counts only.

Two honesty constraints run through the whole module. First, **delivery is
queued, not instant**: the outbox drains on its own timer, so a report enqueued
minutes ago is legitimately still pending, and the report distinguishes queued
from delivered rather than implying loss. Second, **departments are not a scoring
target today** — the pipeline scores users, labs, and projects — so the
department number is reported as the departments whose plans brought labs into
the run, which is the true statement available.

Everything is read-only. Collecting analytics must never change what the run
produced.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from django.db.models import Count, Sum
from django.utils import timezone

#: Content categories, in the order every surface presents them.
CATEGORIES = ("papers", "grants", "fellowships", "conferences")

#: How many days of history the trend section covers (today inclusive).
TREND_DAYS = 7

_CATEGORY_BY_TYPE = {
    "paper": "papers",
    "grant": "grants",
    "fellowship": "fellowships",
    "conference": "conferences",
}

CATEGORY_LABELS = {
    "papers": "Papers",
    "grants": "Grants",
    "fellowships": "Fellowships",
    "conferences": "Conferences",
}

TARGET_LABELS = {
    "user": "People",
    "lab": "Labs",
    "project": "Projects",
    "department": "Departments",
}


@dataclass
class Coverage:
    """Who the run was for."""

    users: int = 0
    labs: int = 0
    departments: int = 0
    projects: int = 0

    @property
    def total_targets(self) -> int:
        return self.users + self.labs + self.projects


@dataclass
class Discovery:
    """New content that entered the store on the run's day, by category."""

    counts: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    def get(self, category: str) -> int:
        return int(self.counts.get(category, 0))


@dataclass
class Recommendations:
    """Matches Mylo wrote — the items it actually put in front of someone."""

    by_category: dict[str, int] = field(default_factory=dict)
    by_target: dict[str, int] = field(default_factory=dict)
    member_suggestions: int = 0
    member_suggestions_delivered: int = 0

    @property
    def total(self) -> int:
        return sum(self.by_category.values())


@dataclass
class ComponentUsage:
    """One component's slice of the day's LLM spend."""

    component: str
    calls: int = 0
    failures: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class LLMUsage:
    """The day's LLM totals plus the per-component breakdown."""

    components: list[ComponentUsage] = field(default_factory=list)

    @property
    def calls(self) -> int:
        return sum(c.calls for c in self.components)

    @property
    def failures(self) -> int:
        return sum(c.failures for c in self.components)

    @property
    def prompt_tokens(self) -> int:
        return sum(c.prompt_tokens for c in self.components)

    @property
    def completion_tokens(self) -> int:
        return sum(c.completion_tokens for c in self.components)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def failure_rate(self) -> float:
        """Share of calls that raised, 0.0–1.0. Zero calls means zero failures."""
        return (self.failures / self.calls) if self.calls else 0.0


@dataclass
class Delivery:
    """Reports written, and how far each got toward a human."""

    briefings_users: int = 0
    briefings_labs: int = 0
    briefings_fallback: int = 0
    reports_queued: int = 0
    reports_delivered: int = 0
    reports_failed: int = 0
    reports_scheduled: int = 0
    digests_queued: int = 0
    digests_delivered: int = 0
    digests_failed: int = 0
    digests_scheduled: int = 0

    @property
    def briefings_generated(self) -> int:
        return self.briefings_users + self.briefings_labs

    @property
    def reports_pending(self) -> int:
        """Queued, not settled, and **due** — the number worth worrying about.

        Rows held for a recipient's local send hour (``not_before``, plan 0.3) are
        not late, they are waiting on purpose. Counting them as pending made the
        analytics report open every morning with a backlog that resolves itself by
        breakfast, which is how a health number stops being read.
        """
        settled = self.reports_delivered + self.reports_failed
        return max(0, self.reports_queued - settled - self.reports_scheduled)

    @property
    def digests_pending(self) -> int:
        settled = self.digests_delivered + self.digests_failed
        return max(0, self.digests_queued - settled - self.digests_scheduled)


@dataclass
class DeliveryTelemetry:
    """Who chose what, and when they actually read it (plan 8.3).

    The four numbers that say whether the cadence redesign worked, and one that
    says it cannot be answered. Kept separate from :class:`Delivery`, which
    counts what the run *did*; this counts what people *chose* and *did back*.

    ``lab_channel_mutes`` is permanently ``None`` and that is the honest value:
    Discord does not tell a bot when a channel is muted, so the one obvious
    measure of whether a lab post is unwelcome is not observable. Reporting a
    zero there would be inventing a reassurance.
    """

    cadence_daily: int = 0
    cadence_weekly: int = 0
    lab_cadence_daily: int = 0
    lab_cadence_weekly: int = 0
    urgent_alerts_opted_in: int = 0
    dm_opt_outs: int = 0
    #: ``{weekday name: engagement events}`` over the trend window. The question
    #: it answers is whether weekday delivery lands: a Tuesday report nobody
    #: opens until Friday is a Friday report with extra steps.
    opens_by_weekday: dict = field(default_factory=dict)
    lab_channel_mutes: int | None = None

    def as_dict(self) -> dict:
        return {
            "cadence_daily": self.cadence_daily,
            "cadence_weekly": self.cadence_weekly,
            "lab_cadence_daily": self.lab_cadence_daily,
            "lab_cadence_weekly": self.lab_cadence_weekly,
            "urgent_alerts_opted_in": self.urgent_alerts_opted_in,
            "dm_opt_outs": self.dm_opt_outs,
            "opens_by_weekday": dict(self.opens_by_weekday),
            "lab_channel_mutes": self.lab_channel_mutes,
        }


@dataclass
class TrendPoint:
    """One earlier day, for the trend section."""

    day: date
    discovered: int = 0
    recommendations: int = 0
    llm_calls: int = 0
    total_tokens: int = 0


@dataclass
class Listening:
    """How much conversation Mylo heard, and why the rest was dropped.

    Counts only. A report about how much was heard must not become a report
    about *who* was heard, which is why every number here is per-server and
    per-reason and none is per-person — the ledger never records the latter.

    The dropped figures are the useful half. A server with listening on and
    everything landing in ``dropped_not_opted_in`` is not broken; it is one
    where nobody has opted in yet, which is a different conversation to have
    with that lab than a misconfigured exclusion.
    """

    sources_listening: int = 0
    sources_active_today: int = 0
    heard: int = 0
    stored: int = 0
    dropped_not_opted_in: int = 0
    dropped_unlinked: int = 0
    dropped_free_tier: int = 0
    dropped_excluded_channel: int = 0
    dropped_too_short: int = 0
    dropped_bot: int = 0
    dropped_lapsed: int = 0
    dropped_other: int = 0
    #: What the reading and the dialogue did with it (ambient Plan 10, step
    #: 12). Counts only, like everything above.
    observations: int = 0
    observations_rule: int = 0
    findings_to_ask: int = 0
    questions_asked: int = 0
    questions_answered: int = 0
    answered_yes: int = 0
    answered_no: int = 0
    answered_later: int = 0
    changes_applied: int = 0
    changes_undone: int = 0
    proposals_raised: int = 0

    @property
    def dropped(self) -> int:
        return (
            self.dropped_not_opted_in
            + self.dropped_unlinked
            + self.dropped_free_tier
            + self.dropped_excluded_channel
            + self.dropped_too_short
            + self.dropped_bot
            + self.dropped_lapsed
            + self.dropped_other
        )


@dataclass
class RunAnalytics:
    """Everything the daily analytics report shows, for one day."""

    generated_on: date
    coverage: Coverage = field(default_factory=Coverage)
    discovery: Discovery = field(default_factory=Discovery)
    recommendations: Recommendations = field(default_factory=Recommendations)
    llm: LLMUsage = field(default_factory=LLMUsage)
    delivery: Delivery = field(default_factory=Delivery)
    telemetry: DeliveryTelemetry = field(default_factory=DeliveryTelemetry)
    listening: Listening = field(default_factory=Listening)
    trend: list[TrendPoint] = field(default_factory=list)
    #: ``apps.collab.evaluation.daily_counts`` plus ``harm`` — flat counts.
    collaboration: dict = field(default_factory=dict)

    def headline(self) -> str:
        """One sentence in Mylo's voice, for the top of the report."""
        cov = self.coverage
        who = _plural(cov.users, "person", "people")
        labs = _plural(cov.labs, "lab", "labs")
        return (
            f"Mylo ran for {who} and {labs}, found "
            f"{self.discovery.total:,} new item(s), and wrote "
            f"{self.recommendations.total:,} recommendation(s)."
        )

    def as_dict(self) -> dict:
        """A JSON-serializable snapshot — the wire format the host reporter reads.

        The nightly run posts its Discord summary from the host, outside Django,
        so this dict (not the dataclass) is the contract between the two halves.
        Keep it flat and boring; add keys rather than reshaping existing ones.
        """
        return {
            "generated_on": self.generated_on.isoformat(),
            "headline": self.headline(),
            "coverage": {
                "users": self.coverage.users,
                "labs": self.coverage.labs,
                "departments": self.coverage.departments,
                "projects": self.coverage.projects,
            },
            "discovery": {
                category: self.discovery.get(category) for category in CATEGORIES
            }
            | {"total": self.discovery.total},
            "recommendations": {
                "total": self.recommendations.total,
                "by_category": {
                    category: int(self.recommendations.by_category.get(category, 0))
                    for category in CATEGORIES
                },
                "by_target": dict(self.recommendations.by_target),
                "member_suggestions": self.recommendations.member_suggestions,
                "member_suggestions_delivered": (
                    self.recommendations.member_suggestions_delivered
                ),
            },
            "llm": {
                "calls": self.llm.calls,
                "failures": self.llm.failures,
                "prompt_tokens": self.llm.prompt_tokens,
                "completion_tokens": self.llm.completion_tokens,
                "total_tokens": self.llm.total_tokens,
                "components": [
                    {
                        "component": c.component,
                        "calls": c.calls,
                        "failures": c.failures,
                        "prompt_tokens": c.prompt_tokens,
                        "completion_tokens": c.completion_tokens,
                    }
                    for c in self.llm.components
                ],
            },
            "delivery": {
                "briefings_generated": self.delivery.briefings_generated,
                "briefings_users": self.delivery.briefings_users,
                "briefings_labs": self.delivery.briefings_labs,
                "briefings_fallback": self.delivery.briefings_fallback,
                "reports_queued": self.delivery.reports_queued,
                "reports_delivered": self.delivery.reports_delivered,
                "reports_failed": self.delivery.reports_failed,
                "reports_pending": self.delivery.reports_pending,
                "reports_scheduled": self.delivery.reports_scheduled,
                "digests_queued": self.delivery.digests_queued,
                "digests_delivered": self.delivery.digests_delivered,
                "digests_failed": self.delivery.digests_failed,
                "digests_pending": self.delivery.digests_pending,
                "digests_scheduled": self.delivery.digests_scheduled,
            },
            "telemetry": self.telemetry.as_dict(),
            "listening": {
                "sources_listening": self.listening.sources_listening,
                "sources_active_today": self.listening.sources_active_today,
                "heard": self.listening.heard,
                "stored": self.listening.stored,
                "dropped": self.listening.dropped,
                "dropped_not_opted_in": self.listening.dropped_not_opted_in,
                "dropped_unlinked": self.listening.dropped_unlinked,
                "dropped_free_tier": self.listening.dropped_free_tier,
                "dropped_excluded_channel": (
                    self.listening.dropped_excluded_channel
                ),
                "dropped_too_short": self.listening.dropped_too_short,
                "dropped_bot": self.listening.dropped_bot,
                "dropped_lapsed": self.listening.dropped_lapsed,
            },
            "collaboration": dict(self.collaboration),
            "trend": [
                {
                    "day": point.day.isoformat(),
                    "discovered": point.discovered,
                    "recommendations": point.recommendations,
                    "llm_calls": point.llm_calls,
                    "total_tokens": point.total_tokens,
                }
                for point in self.trend
            ],
        }


def _plural(count: int, one: str, many: str) -> str:
    return f"{count:,} {one if count == 1 else many}"


# --- collectors ------------------------------------------------------------- #
def collect_coverage() -> Coverage:
    """Who this run covers, asked of the pipeline's own selectors.

    Departments are counted separately because they are not a scoring target: a
    department plan brings its labs into ``select_targets``, and the department
    itself is never scored. The number therefore means "departments whose plan
    put labs in tonight's run".
    """
    from apps.billing.models import Subscription

    from tools.recommendation.tasks import select_targets, select_users

    users = select_users(None)
    labs, projects = select_targets(None)
    departments = (
        Subscription.objects.filter(
            status=Subscription.Status.ACTIVE, scope_department__isnull=False
        )
        .values("scope_department_id")
        .distinct()
        .count()
    )
    return Coverage(
        users=len(users),
        labs=len(labs),
        departments=departments,
        projects=len(projects),
    )


def collect_discovery(day: date) -> Discovery:
    """Content items first created on ``day``, by category."""
    from tools.retrieval.models import ContentItem

    rows = (
        ContentItem.objects.filter(created_at__date=day)
        .values("type")
        .annotate(n=Count("id"))
    )
    counts = {category: 0 for category in CATEGORIES}
    for row in rows:
        category = _CATEGORY_BY_TYPE.get(row["type"])
        if category:
            counts[category] = int(row["n"])
    return Discovery(counts=counts)


def collect_recommendations(day: date) -> Recommendations:
    """Relevance scores written on ``day``, by category and by target kind."""
    from tools.delivery.models import MemberSuggestion
    from tools.recommendation.models import RelevanceScore

    scores = RelevanceScore.objects.filter(created_at__date=day)

    by_category = {category: 0 for category in CATEGORIES}
    for row in scores.values("content__type").annotate(n=Count("id")):
        category = _CATEGORY_BY_TYPE.get(row["content__type"])
        if category:
            by_category[category] = int(row["n"])

    # One aggregate pass rather than four COUNT queries: the target is a set of
    # mutually exclusive nullable FKs, so a null-count per column is the split.
    totals = scores.aggregate(
        user=Count("target_user"),
        lab=Count("target_lab"),
        project=Count("target_project"),
        department=Count("target_department"),
    )
    by_target = {key: int(value or 0) for key, value in totals.items()}

    suggestions = MemberSuggestion.objects.filter(created_at__date=day)
    return Recommendations(
        by_category=by_category,
        by_target=by_target,
        member_suggestions=suggestions.count(),
        member_suggestions_delivered=suggestions.filter(suggested=True).count(),
    )


def collect_llm_usage(day: date) -> LLMUsage:
    """The day's LLM ledger, heaviest component first."""
    from apps.core.models import LLMUsageDaily

    rows = LLMUsageDaily.objects.filter(day=day)
    components = [
        ComponentUsage(
            component=row.component,
            calls=int(row.calls),
            failures=int(row.failures),
            prompt_tokens=int(row.prompt_tokens),
            completion_tokens=int(row.completion_tokens),
        )
        for row in rows
    ]
    components.sort(key=lambda c: (-c.total_tokens, -c.calls, c.component))
    return LLMUsage(components=components)


def collect_delivery(day: date) -> Delivery:
    """Briefings written on ``day``, and how far their Discord messages got."""
    from apps.integrations.models import DiscordOutboxMessage

    from tools.delivery.models import DailyBriefing

    briefings = DailyBriefing.objects.filter(generated_on=day)
    delivery = Delivery(
        briefings_users=briefings.filter(user__isnull=False).count(),
        briefings_labs=briefings.filter(lab__isnull=False).count(),
        briefings_fallback=briefings.filter(
            origin=DailyBriefing.Origin.FALLBACK
        ).count(),
    )

    outbox = DiscordOutboxMessage.objects.filter(created_at__date=day)
    now = timezone.now()
    for kinds, queued, delivered, failed, scheduled in (
        (
            ("daily_report", "weekly_report", "urgent_alert"),
            "reports_queued",
            "reports_delivered",
            "reports_failed",
            "reports_scheduled",
        ),
        (
            ("lab_digest", "lab_weekly"),
            "digests_queued",
            "digests_delivered",
            "digests_failed",
            "digests_scheduled",
        ),
    ):
        rows = outbox.filter(kind__in=kinds)
        setattr(delivery, queued, rows.count())
        setattr(
            delivery,
            delivered,
            rows.filter(status=DiscordOutboxMessage.Status.SENT).count(),
        )
        setattr(
            delivery,
            failed,
            rows.filter(
                status__in=(
                    DiscordOutboxMessage.Status.FAILED,
                    DiscordOutboxMessage.Status.DEAD,
                )
            ).count(),
        )
        # Held for a local send hour, not stuck. A future ``next_attempt_at`` is
        # the only way a row is deliberately not due yet (plan 0.3).
        setattr(
            delivery,
            scheduled,
            rows.filter(
                status__in=(
                    DiscordOutboxMessage.Status.PENDING,
                    DiscordOutboxMessage.Status.SENDING,
                ),
                next_attempt_at__gt=now,
            ).count(),
        )
    return delivery


def collect_telemetry(day: date, *, days: int = TREND_DAYS) -> DeliveryTelemetry:
    """What people chose, and when they read what arrived (plan 8.3)."""
    from apps.accounts.models import LabWatchPreference, WatchCadence, WatchPreference
    from apps.integrations.models import DiscordIdentity

    from tools.recommendation.models import RelevanceEvent

    telemetry = DeliveryTelemetry(
        cadence_daily=WatchPreference.objects.filter(
            cadence=WatchCadence.DAILY
        ).count(),
        cadence_weekly=WatchPreference.objects.filter(
            cadence=WatchCadence.WEEKLY
        ).count(),
        lab_cadence_daily=LabWatchPreference.objects.filter(
            cadence=WatchCadence.DAILY
        ).count(),
        lab_cadence_weekly=LabWatchPreference.objects.filter(
            cadence=WatchCadence.WEEKLY
        ).count(),
        urgent_alerts_opted_in=WatchPreference.objects.filter(
            urgent_alerts=True
        ).count(),
        dm_opt_outs=DiscordIdentity.objects.filter(
            daily_report_opt_out=True
        ).count(),
    )

    # Which weekday people actually engage on. A Tuesday report nobody opens
    # until Friday is a Friday report with extra steps, and that is a thing the
    # send hour and the cadence matrix can be changed in response to.
    names = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    counts = dict.fromkeys(names, 0)
    rows = RelevanceEvent.objects.filter(
        created_at__date__gte=day - timedelta(days=days),
        created_at__date__lte=day,
        action__in=(
            RelevanceEvent.Action.VIEW,
            RelevanceEvent.Action.OPEN_EXTERNAL,
            RelevanceEvent.Action.SAVE,
        ),
    ).values_list("created_at", flat=True)
    for created in rows:
        counts[names[created.weekday()]] += 1
    telemetry.opens_by_weekday = counts
    return telemetry


def collect_trend(day: date, *, days: int = TREND_DAYS) -> list[TrendPoint]:
    """A short history so a single night can be read against its neighbours.

    Grouped in Python from three cheap aggregates rather than a date-truncated
    GROUP BY per model, because the window is a week and the readability is worth
    more here than the round trip.
    """
    from apps.core.models import LLMUsageDaily

    from tools.recommendation.models import RelevanceScore
    from tools.retrieval.models import ContentItem

    start = day - timedelta(days=max(0, days - 1))
    span = (day - start).days + 1
    window = [start + timedelta(days=offset) for offset in range(span)]
    points = {d: TrendPoint(day=d) for d in window}

    for row in (
        ContentItem.objects.filter(
            created_at__date__gte=start, created_at__date__lte=day
        )
        .values("created_at__date")
        .annotate(n=Count("id"))
    ):
        point = points.get(row["created_at__date"])
        if point:
            point.discovered = int(row["n"])

    for row in (
        RelevanceScore.objects.filter(
            created_at__date__gte=start, created_at__date__lte=day
        )
        .values("created_at__date")
        .annotate(n=Count("id"))
    ):
        point = points.get(row["created_at__date"])
        if point:
            point.recommendations = int(row["n"])

    for row in (
        LLMUsageDaily.objects.filter(day__gte=start, day__lte=day)
        .values("day")
        .annotate(
            calls=Sum("calls"),
            prompt=Sum("prompt_tokens"),
            completion=Sum("completion_tokens"),
        )
    ):
        point = points.get(row["day"])
        if point:
            point.llm_calls = int(row["calls"] or 0)
            point.total_tokens = int(row["prompt"] or 0) + int(row["completion"] or 0)

    return [points[d] for d in window]


def collect_listening(day: date) -> Listening:
    """Ambient listening volume for ``day``.

    Read through ``apps.ambient.read`` — the ledger's one door for the rest of
    the backend — so this module never touches an ambient model directly.
    """
    from apps.ambient.read import listening_totals, understanding_totals

    from tools.delivery.models import ReflectionProposal

    totals = listening_totals(day)
    understood = understanding_totals(day)
    return Listening(
        observations=understood["observations"],
        observations_rule=understood["observations_rule"],
        findings_to_ask=understood["findings_to_ask"],
        questions_asked=understood["questions_asked"],
        questions_answered=understood["questions_answered"],
        answered_yes=understood["answered_yes"],
        answered_no=understood["answered_no"],
        answered_later=understood["answered_later"],
        changes_applied=understood["changes_applied"],
        changes_undone=understood["changes_undone"],
        proposals_raised=ReflectionProposal.objects.filter(
            created_at__date=day, evidence__source="conversation"
        ).count(),
        sources_listening=totals["sources_listening"],
        sources_active_today=totals["sources_active_today"],
        heard=totals["heard"],
        stored=totals["stored"],
        dropped_not_opted_in=totals["dropped_not_opted_in"],
        dropped_unlinked=totals["dropped_unlinked"],
        dropped_free_tier=totals["dropped_free_tier"],
        dropped_excluded_channel=totals["dropped_excluded_channel"],
        dropped_too_short=totals["dropped_too_short"],
        dropped_bot=totals["dropped_bot"],
        dropped_lapsed=totals["dropped_lapsed"],
        dropped_other=totals["dropped_other"],
    )


def collect_collaboration(day: date) -> dict:
    """The day's collaboration counts and harm checks — never a name."""
    from apps.collab.evaluation import daily_counts, harm_checks

    start = timezone.make_aware(datetime.combine(day, datetime.min.time()))
    return {
        **daily_counts(day),
        "harm": harm_checks(start, start + timedelta(days=1)),
    }


def collect_run_analytics(day: date | None = None) -> RunAnalytics:
    """Assemble the whole picture for ``day`` (default: today, local time)."""
    run_day = day or timezone.localdate()
    return RunAnalytics(
        generated_on=run_day,
        coverage=collect_coverage(),
        discovery=collect_discovery(run_day),
        recommendations=collect_recommendations(run_day),
        llm=collect_llm_usage(run_day),
        delivery=collect_delivery(run_day),
        telemetry=collect_telemetry(run_day),
        listening=collect_listening(run_day),
        trend=collect_trend(run_day),
        collaboration=collect_collaboration(run_day),
    )
