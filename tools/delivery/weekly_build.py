"""Build one week's evidence packet for one target and one surface.

Reads the same rows every other surface reads — the week's slates, the stored
précis and write-ups, the alerts that fired, the matchers' own output, and what
the reader did — and numbers them. After this runs, the synthesis call sees the
packet and nothing else (see :mod:`tools.delivery.weekly_packet`).

Two decisions worth stating.

**The week, not the day.** A daily reports one run; the weekly reports seven, so
"entered" means entered at any point Monday to Sunday and an item that entered on
Tuesday and left on Friday is still part of the week's story. The slates
themselves are per-run, so the week is assembled from the alerts and the current
slate together rather than from a stored history that does not exist.

**Already-alerted items are in the packet, marked** (plan 6.6). The weekly's job
for them is to report what *happened* — saved, opened, revised, still untouched —
not to raise them again. Raising them again is exactly how a weekly becomes a
digest of the dailies, which is a thing nobody reads twice.
"""

from __future__ import annotations

from datetime import date, timedelta

from django.utils import timezone

from tools.delivery.matchers import known_literature as known_matcher
from tools.delivery.matchers import team_gap as team_matcher
from tools.delivery.matchers import timeline as timeline_matcher
from tools.delivery.weekly_packet import (
    HORIZON_WEEKS,
    ITEMS_PER_PROJECT,
    PacketItem,
    ProjectPacket,
    WeeklyPacket,
)

#: Surfaces a packet can be built for. A packet records which one it is, so it
#: cannot be handed to the wrong renderer by accident (plan H4).
SURFACE_DM = "dm"
SURFACE_CHANNEL = "channel"


def week_start(today: date | None = None) -> date:
    """The Monday of ``today``'s week — the weekly's key and its dedupe key.

    Monday rather than "seven days back", so a weekly re-run on Tuesday after an
    outage re-finds Monday's row instead of queueing a second copy of the week.
    """
    today = today or timezone.localdate()
    return today - timedelta(days=today.weekday())


def entered_this_week(signals: dict | None, start: date, end: date) -> bool:
    """Whether a row entered its slate at any point in the week being reported.

    The daily's ``is_entrant`` asks about one run. A weekly written on a quiet
    Monday would otherwise be an empty document about six busy days, which is the
    opposite of what the report is for.
    """
    entered = str((signals or {}).get("entered_top_on") or "")[:10]
    if not entered:
        return False
    try:
        when = date.fromisoformat(entered)
    except ValueError:
        return False
    return start <= when <= end


def _precis_block(precis) -> dict:
    if precis is None:
        return {}
    fields = ("problem", "method", "setting", "claim", "limitations", "reusable")
    return {
        field: getattr(precis, field, "")
        for field in fields
        if getattr(precis, field, "")
    }


def _writeup_block(signals: dict, cluster_id: str = "") -> dict:
    from tools.recommendation.cluster_fit import stored_writeup

    writeups = (signals or {}).get("writeups") or {}
    entry = stored_writeup(signals, cluster_id) if cluster_id else None
    if entry is None and isinstance(writeups, dict) and writeups:
        entry = next(iter(writeups.values()))
    if not isinstance(entry, dict):
        return {}
    return {
        key: entry[key]
        for key in ("verdict", "beats", "caveat", "differs")
        if entry.get(key)
    }


def _reader_signals(content_id: str, saved: dict, seen: set) -> dict:
    """What the reader did with this item. The weekly reports status, not prose."""
    out: dict = {}
    if content_id in saved:
        out["saved"] = saved[content_id]
    out["opened"] = content_id in seen
    return out


def build_project_packet(
    project,
    *,
    target_filter: dict,
    reader,
    numbering,
    today: date,
    saved: dict,
    seen: set,
) -> ProjectPacket:
    """One project's week."""
    from tools.delivery.briefing import CATEGORY_TYPES, report_scores
    from tools.delivery.models import ProjectAlert
    from tools.recommendation.models import ItemComprehension

    state = getattr(project, "state", None)
    packet = ProjectPacket(
        project_id=str(project.id),
        label=project.name,
        stage=str((getattr(state, "fast", None) or {}).get("stage") or ""),
        state_slow=getattr(state, "slow", None) or {},
        state_fast=getattr(state, "fast", None) or {},
        days_since_confirmed=(
            state.days_since_confirmed(today) if state is not None else None
        ),
    )

    iso = today.isoformat()
    scores: list = []
    for content_type in CATEGORY_TYPES.values():
        scores.extend(report_scores({"target_project": project}, content_type, iso))
    contents = {str(score.content_id): score.content for score in scores}
    by_content = {str(score.content_id): score for score in scores}

    alerts = list(
        ProjectAlert.objects.filter(
            **target_filter,
            project=project,
            fired_on__gte=week_start(today),
        ).select_related("content")
    )
    packet.already_alerted = [
        {
            "item": str(alert.content_id),
            "trigger": alert.trigger,
            "on": alert.fired_on.isoformat(),
        }
        for alert in alerts
    ]
    triggers: dict[str, list[str]] = {}
    for alert in alerts:
        triggers.setdefault(str(alert.content_id), []).append(alert.trigger)
        contents.setdefault(str(alert.content_id), alert.content)

    precis_rows = {
        str(row.content_id): row
        for row in ItemComprehension.objects.filter(content_id__in=list(contents))
    }
    literature = known_matcher.known_literature(project, reader)

    # Alerted items first, then entrants, then the rest of the slate. The order
    # is the packet's only steer on what matters, and it is the same order the
    # report's own sections use.
    def rank(content_id: str) -> tuple:
        score = by_content.get(content_id)
        signals = (score.signals if score is not None else {}) or {}
        return (
            0 if content_id in triggers else 1,
            0 if entered_this_week(signals, week_start(today), today) else 1,
            signals.get("top_rank") or 999,
        )

    for content_id in sorted(contents, key=rank)[:ITEMS_PER_PROJECT]:
        content = contents[content_id]
        precis = precis_rows.get(content_id)
        metadata = content.metadata or {}
        _is_known, revised, _how = literature.verdict(content, precis)
        signals = (by_content[content_id].signals if content_id in by_content else {})
        packet.items.append(
            PacketItem(
                n=next(numbering),
                content_id=content_id,
                title=metadata.get("title") or metadata.get("name") or "(untitled)",
                url=content.source_url or "",
                kind=content.type,
                source=content.source,
                precis=_precis_block(precis),
                writeup=_writeup_block(signals or {}),
                matchers=triggers.get(content_id, []),
                reader_signals=_reader_signals(content_id, saved, seen),
                revised_on=today.isoformat() if revised else "",
            )
        )
        if entered_this_week(signals, week_start(today), today):
            packet.entered += 1

    packet.timeline_rows = [
        row.as_dict()
        for row in timeline_matcher.timeline_rows(
            project,
            list(contents),
            reader=reader,
            today=today,
            horizon_days=HORIZON_WEEKS * 7,
        )
    ]
    # On a lab surface the weekly is allowed to name who a call suits (plan D6,
    # reversing the daily's no-names rule for the weekly only). So the covered
    # requirements travel too, not just the gaps — "best suited: Brendon, whose
    # profile lists knowledge graphs" is the sentence that turns a grant into an
    # assignment, and it is only sayable with the names attached.
    #
    # Names and stated research areas only. Fellowship eligibility — citizenship,
    # career stage — never reaches a channel (invariant 7): it was given for a
    # different purpose, and a channel is not where someone finds out their
    # colleagues can see it.
    packet.team_gaps = [
        gap.as_dict()
        for gap in team_matcher.team_gaps(target_filter, list(contents.values()))
    ]
    return packet


def build_weekly_packet(
    *,
    target_filter: dict,
    projects: list,
    reader,
    surface: str,
    label: str,
    today: date | None = None,
) -> WeeklyPacket:
    """The whole week, numbered and closed.

    Numbering runs across the entire packet rather than per project, so ``[P7]``
    means one thing in the document. Per-project numbering would make a citation
    ambiguous the moment the overview mentioned two projects in one sentence.
    """
    from tools.delivery.models import ProjectItemSeen, SavedOpportunity

    today = today or timezone.localdate()
    start = week_start(today)
    numbering = iter(range(1, 500))

    saves_filter = (
        {"target_lab": reader}
        if "target_lab" in target_filter
        else {"user": reader, "target_lab": None}
    )
    saved = {
        str(row.content_id): row.created_at.date().isoformat()
        for row in SavedOpportunity.objects.filter(**saves_filter).exclude(
            content__isnull=True
        )
    }
    seen = {
        str(row.content_id)
        for row in ProjectItemSeen.objects.filter(project__in=projects)
    }

    packet = WeeklyPacket(
        packet_id=f"weekly:{label}:{start.isoformat()}",
        surface=surface,
        week_start=start,
    )
    for project in projects:
        packet.projects.append(
            build_project_packet(
                project,
                target_filter=target_filter,
                reader=reader,
                numbering=numbering,
                today=today,
                saved=saved,
                seen=seen,
            )
        )

    # The reader's own week, beside their projects'. A weekly for someone with no
    # projects was an empty document — and "you have no projects" is not a thing
    # to tell somebody every Monday. Their entrants are still their week.
    packet.personal = _personal_items(
        target_filter, numbering=numbering, today=today, saved=saved, seen=seen
    )

    packet.deadline_horizon = [
        row
        for project_packet in packet.projects
        for row in project_packet.timeline_rows
        if row.get("due_date")
    ]
    packet.deadline_horizon.sort(key=lambda row: row["due_date"])
    packet.engagement = {
        "saved": len(saved),
        "opened": len(seen),
    }
    packet.reflection = _reflect(packet, target_filter, projects, reader, today)
    # What changed this week (ambient Plan 09): numbered [O#], the project rows
    # also inside each project's packet. Personal rows never reach a lab packet.
    from tools.delivery.briefing import context_version
    from tools.delivery.weekly_changes import collect

    packet.reader = reader
    collect(
        packet,
        target_filter=target_filter,
        projects=projects,
        reader=reader,
        today=today,
    )
    is_lab = "target_lab" in target_filter
    packet.context_version = context_version(
        {"lab": reader} if is_lab else {"user": reader}, projects
    )
    return packet


def _personal_items(
    target_filter: dict, *, numbering, today: date, saved: dict, seen: set
) -> list[PacketItem]:
    """The reader's own entrants this week — the half that is not a project.

    Entrants only, and capped: the weekly's job for the personal feed is "here is
    what earned a place", not a second copy of the standing list the web already
    holds.
    """
    from tools.delivery.briefing import CATEGORY_TYPES, report_scores
    from tools.recommendation.models import ItemComprehension

    # The **week**, not the day. A daily reports one run; this reports seven, and
    # asking the daily's "did it enter today" would make every weekly written on
    # a quiet Monday an empty document about six busy days.
    iso = today.isoformat()
    start = week_start(today)
    entrants = []
    for content_type in CATEGORY_TYPES.values():
        for score in report_scores(target_filter, content_type, iso):
            if entered_this_week(score.signals, start, today):
                entrants.append(score)
    if not entrants:
        return []

    entrants.sort(key=lambda score: (score.signals or {}).get("top_rank") or 999)
    entrants = entrants[:ITEMS_PER_PROJECT]
    precis_rows = {
        str(row.content_id): row
        for row in ItemComprehension.objects.filter(
            content_id__in=[score.content_id for score in entrants]
        )
    }
    out = []
    for score in entrants:
        content = score.content
        metadata = content.metadata or {}
        content_id = str(score.content_id)
        out.append(
            PacketItem(
                n=next(numbering),
                content_id=content_id,
                title=metadata.get("title") or metadata.get("name") or "(untitled)",
                url=content.source_url or "",
                kind=content.type,
                source=content.source,
                precis=_precis_block(precis_rows.get(content_id)),
                writeup=_writeup_block(score.signals or {}),
                reader_signals=_reader_signals(content_id, saved, seen),
            )
        )
    return out


def _reflect(packet, target_filter, projects, reader, today):
    """Run the deterministic proposal rules, store what is new, render the block.

    Stored *and* rendered here so the weekly and the accept/reject surface show
    the same proposals: a block naming an r4 the Projects page has never heard of
    is exactly the kind of inconsistency that makes a reader stop trusting both.
    """
    from tools.delivery import reflection
    from tools.delivery.models import IgnoredItem, ReflectionProposal, SavedOpportunity

    if not projects:
        return ""
    reflection.expire_stale(today)

    is_lab = "target_lab" in target_filter
    saves_filter = (
        {"target_lab": reader} if is_lab else {"user": reader, "target_lab": None}
    )
    # The snapshot is the fallback rather than an afterthought: a save outlives
    # the item's prune by design, and a reader's pattern of saves is exactly the
    # history that spans a prune.
    saved_titles = [
        title
        for title in (
            (row.content.metadata or {}).get("title")
            if row.content_id
            else (row.snapshot or {}).get("title")
            for row in SavedOpportunity.objects.filter(**saves_filter).select_related(
                "content"
            )
        )
        if title
    ]
    # A lab has no personal ignores, so it contributes no exclusion evidence —
    # one member's dismissal is not the lab's opinion.
    dismissed_titles = (
        []
        if is_lab
        else [
            (row.content.metadata or {}).get("title") or ""
            for row in IgnoredItem.objects.filter(user=reader).select_related(
                "content"
            )
        ]
    )

    proposals = []
    by_id = {str(project.id): project for project in projects}
    for project_packet in packet.projects:
        project = by_id.get(project_packet.project_id)
        if project is None:
            continue
        proposals.extend(
            reflection.propose_for_project(
                project,
                saved_titles=saved_titles,
                dismissed_titles=dismissed_titles,
                timeline_rows=project_packet.timeline_rows,
                today=today,
            )
        )
    reflection.persist(proposals, target_filter, today=today)

    pending = list(
        ReflectionProposal.objects.filter(
            **target_filter, status=ReflectionProposal.Status.PENDING
        ).select_related("project")
    )
    return reflection.reflection_block(pending)
