"""How the collaboration network is doing, in counts (plan CN-08).

Three readers:

* :func:`daily_counts` — what the nightly analytics report shows: searches,
  what they returned, feedback, the cap. **Counts only**: nothing here is per
  person, so a report about how the search is used can never become a report
  about who was searched for.
* :func:`harm_checks` — the six things that must never happen (plan CN-08
  §7). The collaboration daily task runs them over the last day and logs an
  error on any non-zero, so a leak is loud the morning after it happens.
* :func:`readiness` — whether search may widen to the next scope (plan CN-07
  step 1): the not-relevant rate under its target, nobody held at the
  appearance cap too often, no harm, and enough feedback to judge by.

Everything is read-only.
"""

from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from django.conf import settings
from django.db.models import Count
from django.utils import timezone

from . import consent
from .models import (
    Appearance,
    Audience,
    CollaborationSetting,
    MatchFeedback,
    SearchLog,
    SlotFeedback,
)

logger = logging.getLogger(__name__)

SCOPE_ORDER = [Audience.INSTITUTION, Audience.COUNTRY, Audience.ANYWHERE]


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = timezone.make_aware(datetime.combine(day, datetime.min.time()))
    return start, start + timedelta(days=1)


def _shown_rows(log: SearchLog) -> list[dict]:
    cached = log.cached or {}
    rows = [row for rows in cached.get("lanes", {}).values() for row in rows]
    return rows + list(cached.get("team", []))


# --- the daily numbers ---------------------------------------------------------


def daily_counts(day: date) -> dict:
    """The day's collaboration numbers, for the analytics report."""
    start, end = _day_bounds(day)
    logs = list(SearchLog.objects.filter(created_at__gte=start, created_at__lt=end))
    lanes = Counter()
    for log in logs:
        for lane, rows in (log.cached or {}).get("lanes", {}).items():
            lanes[lane] += len(rows)
    feedback = Counter(
        MatchFeedback.objects.filter(
            created_at__gte=start, created_at__lt=end
        ).values_list("kind", flat=True)
    )
    now = timezone.now()
    week = Appearance.objects.filter(week=_iso_week(now))
    per_candidate = Counter(week.values_list("candidate_id", flat=True))
    rated = feedback.get("save", 0) + feedback.get("not_relevant", 0)
    return {
        "searches": sum(1 for log in logs if log.lanes != ["team"]),
        "teams": sum(1 for log in logs if log.lanes == ["team"]),
        "searches_by_entry": dict(Counter(log.entry for log in logs)),
        "empty_searches": sum(1 for log in logs if not log.results),
        "results": sum(log.results for log in logs),
        "results_by_lane": dict(lanes),
        "saved": feedback.get("save", 0),
        "not_relevant": feedback.get("not_relevant", 0),
        "not_relevant_rate": round(feedback.get("not_relevant", 0) / rated, 4)
        if rated
        else None,
        "open_now": CollaborationSetting.objects.filter(
            open=True, expires_at__gt=now
        ).count(),
        "people_at_cap_this_week": sum(
            1 for n in per_candidate.values() if n >= settings.COLLAB_APPEARANCE_CAP
        ),
        "slot_feedback": dict(
            Counter(
                SlotFeedback.objects.filter(
                    created_at__gte=start, created_at__lt=end
                ).values_list("kind", flat=True)
            )
        ),
    }


def _iso_week(now) -> str:
    from .consent import iso_week

    return iso_week(now)


# --- harm checks -----------------------------------------------------------------

_TOLD_WORDS = re.compile(r"search|looked (you )?up|found you|appeared", re.I)


def harm_checks(since: datetime | None = None, until: datetime | None = None) -> dict:
    """Counts of what must be zero, over searches in ``[since, until)``.

    1. ``untraceable_evidence`` — a shown person's matched words trace to none
       of their declared or demonstrated edges or published-work facets (the
       only evidence the matcher may read); or a row's tier is anything else.
    2. ``outside_scope`` — a shown person outside audience ∩ scope, judged
       only where their setting has not changed since the search.
    3. ``candidate_told`` — a collaboration notification other than the
       renewal notice, or a renewal notice that mentions being searched for.
    4. ``private_concept_global`` — a global concept held only through
       conversation or project state. Conservative: it also flags a global
       concept whose declared holders have all since left it, for review.
    5. ``shown_while_off`` — a shown person whose setting was off or expired
       when the search ran (judged where it has not changed since).
    6. ``not_from_shortlist`` — a shown person who has no collaboration
       setting at all, or is the seeker: the model named someone the gate never
       offered.
    """
    from tools.retrieval.models import Notification

    from apps.knowledge.read import evidence_texts, privately_held_global_concepts

    from . import consent

    until = until or timezone.now()
    since = since or until - timedelta(days=1)
    logs = list(
        SearchLog.objects.filter(created_at__gte=since, created_at__lt=until)
        .select_related("seeker")
        .order_by("pk")
    )
    out = Counter(
        {
            key: 0
            for key in (
                "untraceable_evidence",
                "outside_scope",
                "candidate_told",
                "private_concept_global",
                "shown_while_off",
                "not_from_shortlist",
            )
        }
    )
    usernames = {row["username"] for log in logs for row in _shown_rows(log)}
    from django.contrib.auth import get_user_model

    people = {
        u.get_username(): u
        for u in get_user_model()
        .objects.filter(username__in=usernames)
        .select_related("verified_affiliation")
    }
    ids = [u.pk for u in people.values()]
    settings_of = {
        s.user_id: s for s in CollaborationSetting.objects.filter(user_id__in=ids)
    }
    evidence = evidence_texts(ids)

    for log in logs:
        seeker_place = consent.stored_place(log.seeker)
        for row in _shown_rows(log):
            person = people.get(row["username"])
            if person is None or person.pk == log.seeker_id:
                out["not_from_shortlist"] += 1
                continue
            setting = settings_of.get(person.pk)
            if setting is None:
                out["not_from_shortlist"] += 1
                continue
            covers = row.get("covers") or [row]
            for item in covers:
                if item.get("tier") not in ("declared", "demonstrated") or (
                    str(item.get("matched", "")).casefold()
                    not in evidence.get(person.pk, set())
                ):
                    out["untraceable_evidence"] += 1
            unchanged = setting.updated_at <= log.created_at
            if not unchanged:
                continue
            if not setting.is_open(log.created_at):
                out["shown_while_off"] += 1
            elif not consent.mutually_visible(
                consent.stored_place(person),
                setting.audience,
                seeker_place,
                log.scope,
            ):
                out["outside_scope"] += 1

    notices = Notification.objects.filter(created_at__gte=since, created_at__lt=until)
    out["candidate_told"] += (
        notices.filter(dedupe_key__startswith="collab")
        .exclude(kind=Notification.Kind.COLLAB_RENEWAL)
        .count()
    )
    out["candidate_told"] += sum(
        1
        for title, body in notices.filter(
            kind=Notification.Kind.COLLAB_RENEWAL
        ).values_list("title", "body")
        if _TOLD_WORDS.search(f"{title} {body}")
    )

    out["private_concept_global"] = privately_held_global_concepts()
    result = dict(out)
    result["searches_checked"] = len(logs)
    return result


def report_harm(since=None, until=None) -> dict:
    """Run the checks and log an error for any that is not zero."""
    result = harm_checks(since, until)
    failing = {k: v for k, v in result.items() if k != "searches_checked" and v}
    if failing:
        logger.error("collaboration harm checks failed: %s", failing)
    return result


# --- readiness to widen ----------------------------------------------------------


def concentration(weeks: int = 4, now=None) -> dict:
    """Appearances per person per week: Gini, and weeks anyone sat at the cap."""
    now = now or timezone.now()
    rows = (
        Appearance.objects.filter(created_at__gte=now - timedelta(weeks=weeks))
        .values("week", "candidate_id")
        .annotate(seekers=Count("seeker_id", distinct=True))
    )
    per_week: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        per_week[row["week"]].append(row["seekers"])
    cap = settings.COLLAB_APPEARANCE_CAP
    at_cap = [sum(1 for n in v if n >= cap) for v in per_week.values()]
    everyone = [n for v in per_week.values() for n in v]
    return {
        "weeks": len(per_week),
        "person_weeks": len(everyone),
        "person_weeks_at_cap": sum(at_cap),
        "share_at_cap": round(sum(at_cap) / len(everyone), 4) if everyone else None,
        "gini": _gini(everyone),
    }


def _gini(values: list[int]) -> float | None:
    values = sorted(values)
    n = len(values)
    if not n or not sum(values):
        return None
    cumulative = sum((i + 1) * v for i, v in enumerate(values))
    return round((2 * cumulative) / (n * sum(values)) - (n + 1) / n, 4)


def readiness(now=None) -> dict:
    """May search widen past ``COLLAB_MAX_SCOPE``? (plan CN-07 step 1)

    Judged over the last ``COLLAB_WIDEN_WINDOW_DAYS`` at the current scope.
    Widening itself stays a deliberate settings change; this only says whether
    the evidence allows it, and why not.
    """
    now = now or timezone.now()
    since = now - timedelta(days=settings.COLLAB_WIDEN_WINDOW_DAYS)
    feedback = Counter(
        MatchFeedback.objects.filter(created_at__gte=since).values_list(
            "kind", flat=True
        )
    )
    rated = feedback.get("save", 0) + feedback.get("not_relevant", 0)
    not_relevant = feedback.get("not_relevant", 0) / rated if rated else None
    spread = concentration(
        weeks=max(1, settings.COLLAB_WIDEN_WINDOW_DAYS // 7), now=now
    )
    harm = harm_checks(since, now)
    harmful = {k: v for k, v in harm.items() if k != "searches_checked" and v}
    reasons = []
    if rated < settings.COLLAB_WIDEN_MIN_RATINGS:
        reasons.append(
            f"only {rated} rated results; {settings.COLLAB_WIDEN_MIN_RATINGS} needed"
        )
    if (
        not_relevant is not None
        and not_relevant > settings.COLLAB_WIDEN_MAX_NOT_RELEVANT
    ):
        reasons.append(f"not-relevant rate {not_relevant:.2f} is above target")
    if (spread["share_at_cap"] or 0) > settings.COLLAB_WIDEN_MAX_SHARE_AT_CAP:
        reasons.append(f"{spread['share_at_cap']:.2%} of person-weeks at the cap")
    if harmful:
        reasons.append(f"harm checks failing: {sorted(harmful)}")
    # Never past the seeker ceiling: people are suggested only from the
    # seeker's own institution or country (consent.SEEKER_CEILING).
    current = consent.seeker_scope_limit()
    index = SCOPE_ORDER.index(current)
    widest = SCOPE_ORDER.index(consent.SEEKER_CEILING)
    return {
        "scope": current,
        "next_scope": SCOPE_ORDER[index + 1] if index < widest else None,
        "ready": not reasons and index < widest,
        "reasons": reasons,
        "rated": rated,
        "not_relevant_rate": round(not_relevant, 4)
        if not_relevant is not None
        else None,
        "concentration": spread,
        "harm": harm,
    }
