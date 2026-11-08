"""High-signal recommendation alerts (reminders R7) — the brutal gate + shadow.

The same shape as the LLM suggestion gate: **abstention is a feature.** If nothing
clears the floor, send nothing. An alert that fires most days is a digest, and digests
are out of scope. This module only decides *what would qualify* and (optionally, once
calibrated) delivers it **in-app only** (D-10). The floor is a placeholder until the
shadow report is run over the real corpus (D-14), so ``shadow_report`` measures
alerts-per-user-per-week *before* any delivery is wired on.

Gate (all required), read off the ``signals`` blob already persisted per match:

* ``suggested is True`` — the item cleared the match-percent floor and is surfaced
  (NB: ``suggested`` means *passed*, not abstained — the source plan's wording was
  inverted; see the reconciliation table in the plan doc).
* ``match_percent >= HIGH_SIGNAL_FLOOR``
* ``is_new`` and still fresh (``pinned_until >= today``) — a months-old item is not news
* ``source == "llm"`` — a rules-fallback reason isn't strong enough to interrupt
* an actionable deadline exists and is ``[MIN, MAX]`` days out — not past, not years off

Then: ``<= HIGH_SIGNAL_WEEKLY_CAP`` per user per week (top by match_percent, rest
dropped silently), and ``dedupe_key = high_signal:{user}:{content}`` so a given item
alerts a given user once, ever.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from django.conf import settings
from django.utils import timezone
from tools.recommendation.models import RelevanceScore
from tools.retrieval.models import ContentItem, Notification

_OPPORTUNITY_TYPES = (
    ContentItem.Type.GRANT,
    ContentItem.Type.CONFERENCE,
    ContentItem.Type.FELLOWSHIP,
)


@dataclass
class Candidate:
    score: RelevanceScore
    match_percent: int
    days_to_deadline: int

    @property
    def content_id(self) -> str:
        return str(self.score.content_id)


def _parse_date(value) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def high_signal_candidates(
    user,
    *,
    today: date,
    floor: int | None = None,
    deadline_min: int | None = None,
    deadline_max: int | None = None,
) -> list[Candidate]:
    """The items that clear the whole gate for ``user``, strongest first (no cap)."""
    if floor is None:
        floor = settings.HIGH_SIGNAL_FLOOR
    if deadline_min is None:
        deadline_min = settings.HIGH_SIGNAL_DEADLINE_MIN_DAYS
    if deadline_max is None:
        deadline_max = settings.HIGH_SIGNAL_DEADLINE_MAX_DAYS
    today_iso = today.isoformat()

    scores = RelevanceScore.objects.filter(
        target_user=user, content__type__in=_OPPORTUNITY_TYPES
    ).select_related("content")

    candidates: list[Candidate] = []
    for score in scores:
        sig = score.signals or {}
        if not sig.get("suggested"):
            continue
        if not sig.get("is_new"):
            continue
        pinned_until = sig.get("pinned_until")
        if not (pinned_until and pinned_until >= today_iso):  # still fresh only
            continue
        if sig.get("source") != "llm":
            continue
        match_percent = sig.get("match_percent")
        if not isinstance(match_percent, int) or match_percent < floor:
            continue
        due = _parse_date(sig.get("deadline_date"))
        if due is None:
            continue
        days = (due - today).days
        if not (deadline_min <= days <= deadline_max):
            continue
        candidates.append(Candidate(score, match_percent, days))

    candidates.sort(key=lambda c: (-c.match_percent, c.days_to_deadline))
    return candidates


def deliver_high_signal(
    user, *, today: date, cap: int | None = None, floor=None
) -> int:
    """Create in-app high-signal notifications for ``user`` (respecting cap + dedupe).

    Returns the number delivered. Abstains (returns 0) when nothing clears the floor
    or the weekly cap is already spent. In-app only (D-10).
    """
    cap = settings.HIGH_SIGNAL_WEEKLY_CAP if cap is None else cap
    now = timezone.now()
    sent_this_week = Notification.objects.filter(
        user=user,
        kind=Notification.Kind.HIGH_SIGNAL,
        created_at__gte=now - timedelta(days=7),
    ).count()
    remaining = cap - sent_this_week
    if remaining <= 0:
        return 0

    delivered = 0
    for candidate in high_signal_candidates(user, today=today, floor=floor):
        if delivered >= remaining:
            break
        dedupe = f"high_signal:{user.id}:{candidate.content_id}"
        if Notification.objects.filter(dedupe_key=dedupe).exists():
            continue  # alerted once, ever
        title, body = _copy(candidate)
        Notification.objects.create(
            user=user,
            kind=Notification.Kind.HIGH_SIGNAL,
            content=candidate.score.content,
            title=title,
            body=body,
            url=_url(candidate.score),
            dedupe_key=dedupe,
        )
        delivered += 1
    return delivered


def shadow_report(users, *, today: date, floor: int | None = None) -> dict:
    """Measure alerts/user/week at ``floor`` without delivering anything (D-14)."""
    floor = settings.HIGH_SIGNAL_FLOOR if floor is None else floor
    cap = settings.HIGH_SIGNAL_WEEKLY_CAP
    per_user = []
    for user in users:
        n = len(high_signal_candidates(user, today=today, floor=floor))
        if n:
            per_user.append(n)
    total = sum(per_user)
    return {
        "floor": floor,
        "weekly_cap": cap,
        "users_scanned": len(users),
        "users_with_candidates": len(per_user),
        "total_candidates": total,
        "max_per_user": max(per_user, default=0),
        "mean_per_alerted_user": round(total / len(per_user), 2) if per_user else 0,
        "would_be_capped_dropped": sum(max(0, n - cap) for n in per_user),
    }


def _copy(candidate: Candidate) -> tuple[str, str]:
    meta = candidate.score.content.metadata or {}
    title = meta.get("title") or meta.get("name") or "A strong match for your work"
    reason = candidate.score.signals.get("reason") or "A strong match for your profile."
    body = f"{reason} ({candidate.days_to_deadline} days to the deadline)."
    return title, body


def _url(score: RelevanceScore) -> str:
    meta = score.content.metadata or {}
    return meta.get("website") or meta.get("external_url") or score.content.source_url
