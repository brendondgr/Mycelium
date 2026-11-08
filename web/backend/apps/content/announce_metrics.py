"""What announcements are doing, measured (plan Phase 8).

Read-only. Every number comes from rows the announcement path already writes:
``Announcement`` (posted / held / skipped, with the reason), ``AnnouncementReaction``
(Interested, Remind me, Not for us with its reason, web link clicks with their
surface), and the bindings' route health. The department half adds what the
detector and lab-fit did: the reason mix, how much of a department's slate is
department-level at all, and the lab-fit scores behind "Labs that could lead".

Thresholds are never changed here: the output is recorded as an experiment first
(``docs/research/experiments/``), and any change is decided from that record.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.utils import timezone
from tools.recommendation.models import RelevanceScore
from tools.retrieval.models import (
    Announcement,
    AnnouncementNudge,
    AnnouncementReaction,
    AnnouncementSettings,
    ContentItem,
)

from apps.content import dept_level
from apps.integrations.models import DiscordTargetBinding

_KINDS = (
    ContentItem.Type.GRANT,
    ContentItem.Type.FELLOWSHIP,
    ContentItem.Type.CONFERENCE,
)


def _held_class(reason: str) -> str:
    """A skip reason, grouped: the editor's own skips, or the usability check."""
    if reason.startswith("Mylo:"):
        return "editor"
    text = reason.lower()
    for key, words in (
        ("deadline_passed", ("deadline has passed", "closed")),
        ("too_soon", ("buffer",)),
        ("eligibility", ("eligible",)),
        ("applicant", ("apply", "applicant", "institution")),
        ("country", ("country", "countries")),
        ("award", ("award",)),
    ):
        if any(w in text for w in words):
            return key
    return "other"


def _rate(part: int, whole: int) -> float | None:
    return round(part / whole, 4) if whole else None


def compute(since: date, until: date | None = None) -> dict:
    """Metrics for announcements created in ``[since, until]`` (inclusive)."""
    from apps.content import announce, lab_fit
    from apps.integrations.services import resolve

    until = until or timezone.localdate()
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(since, time.min), tz)
    end = timezone.make_aware(datetime.combine(until + timedelta(days=1), time.min), tz)
    anns = list(
        Announcement.objects.filter(created_at__gte=start, created_at__lt=end)
        .select_related("target_lab", "target_department", "content")
        .prefetch_related("reactions", "posts", "nudges")
    )
    targets: dict[str, dict] = {}
    for ann in anns:
        key = (
            f"lab:{ann.target_lab.slug}"
            if ann.target_lab_id
            else f"department:{ann.target_department_id}"
        )
        t = targets.setdefault(
            key,
            {
                "kind": "lab" if ann.target_lab_id else "department",
                "name": (ann.target_lab or ann.target_department).name,
                "posted": 0,
                "posted_by_kind": Counter(),
                "posted_by_origin": Counter(),
                "held": 0,
                "held_by_class": Counter(),
                "seeded_seen": 0,
                "with_interested": 0,
                "interested_people": 0,
                "with_remind": 0,
                "guest_reminder_people": 0,
                "not_for_us": 0,
                "not_for_us_reasons": [],
                "link_clicks": 0,
                "link_click_people": set(),
                "link_clicks_by_surface": Counter(),
                "dept_reasons": Counter(),
                "lab_fit_top": [],
                "labs_named": Counter(),
            },
        )
        if ann.state in (Announcement.State.POSTED, Announcement.State.CLOSED):
            t["posted"] += 1
            t["posted_by_kind"][ann.category] += 1
            t["posted_by_origin"][ann.origin] += 1
            reactions = list(ann.reactions.all())
            interested = {
                r.user_id
                for r in reactions
                if r.kind == AnnouncementReaction.Kind.INTERESTED
            }
            t["with_interested"] += bool(interested)
            t["interested_people"] += len(interested)
            guests = {
                n.discord_user_id
                for n in ann.nudges.all()
                if n.user_id is None and n.source == AnnouncementNudge.Source.REMIND
            }
            t["guest_reminder_people"] += len(guests)
            t["with_remind"] += bool(guests) or any(
                r.kind == AnnouncementReaction.Kind.REMIND for r in reactions
            )
            for r in reactions:
                if r.kind == AnnouncementReaction.Kind.NOT_FOR_US:
                    t["not_for_us"] += 1
                    if r.reason:
                        t["not_for_us_reasons"].append(r.reason)
                elif r.kind == AnnouncementReaction.Kind.LINK_CLICK:
                    t["link_clicks"] += 1
                    t["link_click_people"].add(r.user_id)
                    t["link_clicks_by_surface"][r.reason or "unknown"] += 1
            if ann.target_department_id:
                alignment = ann.alignment or {}
                for reason in alignment.get("dept_reasons") or []:
                    t["dept_reasons"][reason.get("key", "")] += 1
                people = alignment.get("people") or []
                t["lab_fit_top"].append(
                    max((p.get("fit") or 0 for p in people), default=None)
                )
                t["labs_named"][len(people)] += 1
        elif ann.state == Announcement.State.SKIPPED:
            t["held"] += 1
            t["held_by_class"][_held_class(ann.skip_reason)] += 1
        elif ann.state == Announcement.State.SEEDED_SEEN:
            t["seeded_seen"] += 1

    today = timezone.localdate()
    for row in AnnouncementSettings.objects.filter(
        target_department__isnull=False
    ).select_related("target_department"):
        key = f"department:{row.target_department_id}"
        t = targets.setdefault(
            key, {"kind": "department", "name": row.target_department.name}
        )
        target = announce.Target("department", row.target_department, row)
        slate = announce.slate_rows(target, today)
        t["slate_rows"] = len(slate)
        t["slate_dept_level"] = sum(
            bool(dept_level.reasons(r.content.metadata)) for r in slate
        )
        t["slate_dept_level_rate"] = _rate(t["slate_dept_level"], t["slate_rows"])
        scored = RelevanceScore.objects.filter(
            target_department=row.target_department, content__type__in=_KINDS
        ).select_related("content")
        t["scored_rows"] = scored.count()
        level = [r for r in scored if dept_level.reasons(r.content.metadata)]
        t["scored_dept_level"] = len(level)
        labs = lab_fit.candidates(row.target_department)
        fits = sorted(
            round(f["fit"], 4)
            for r in level
            for f in lab_fit.rank(r.content, labs, floor=-1.0, limit=len(labs))
        )
        t["lab_fit_all_scores"] = fits
        t["lab_fit_floor"] = getattr(settings, "LAB_FIT_COSINE_FLOOR", 0.45)
        t["labs_with_vector"] = len(labs)

    health = {"routes": 0, "ok": 0, "failing": 0, "unchecked": 0}
    for binding in DiscordTargetBinding.objects.filter(
        state=DiscordTargetBinding.State.ACTIVE
    ):
        for purpose, route in resolve.routes_for_binding(binding).items():
            if purpose not in ("grants", "fellowships", "conferences"):
                continue
            health["routes"] += 1
            key = {True: "ok", False: "failing"}.get(route.ok, "unchecked")
            health[key] += 1

    out_targets = {}
    for key, t in targets.items():
        posted = t.get("posted", 0)
        row = {k: v for k, v in t.items() if k != "link_click_people"}
        for k, v in list(row.items()):
            if isinstance(v, Counter):
                row[k] = dict(v)
        if "posted" in t:
            row["link_click_people"] = len(t["link_click_people"])
            row["interested_rate"] = _rate(t["with_interested"], posted)
            row["remind_rate"] = _rate(t["with_remind"], posted)
            row["not_for_us_rate"] = _rate(t["not_for_us"], posted)
        out_targets[key] = row
    return {
        "window": {"since": since.isoformat(), "until": until.isoformat()},
        "detector_version": dept_level.VERSION,
        "targets": out_targets,
        "route_health": health,
    }
