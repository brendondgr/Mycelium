"""Today's alerts, as the report and the Discord post read them.

The matchers decide *what* fired and the evidence behind it; this decides how it
is said. Every sentence here is written from stored evidence in code — the dates,
the day counts, the blocker it matched, the requirement nobody covers — so the
report's numbers are the matchers' numbers and no model is asked to reproduce
them (plan H2, and the reason the daily costs no extra model calls in Phase 4).

The shape follows Appendix A.1: a short block per alert, headed by the project
and the trigger, carrying what happened, what to do, and the caveat. Model prose
sits *beside* this in Phase 5; nothing here waits for it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from django.utils import timezone

from tools.delivery.models import ProjectAlert

#: What each trigger is called on the page. Verbs where the reader acts, nouns
#: where they only need to know.
TRIGGER_LABELS = {
    ProjectAlert.Trigger.OVERLAP_RISK: "overlap risk",
    ProjectAlert.Trigger.UNBLOCKS: "unblocks",
    ProjectAlert.Trigger.TIMELINE: "fits your timeline",
    ProjectAlert.Trigger.DEADLINE_MOVED: "deadline moved",
    ProjectAlert.Trigger.TEAM_GAP: "team gap",
}


@dataclass
class AlertBlock:
    """One alert, ready to render in any of the three surfaces."""

    project_label: str
    trigger: str
    trigger_label: str
    title: str
    url: str
    #: ``[(label, sentence)]`` — the bulleted beats under the title.
    beats: list[tuple[str, str]] = field(default_factory=list)
    content_id: str = ""

    def as_markdown(self, index: int) -> str:
        """The report's item grammar, so both renderers already parse it."""
        linked = f"[{self.title}]({self.url})" if self.url else self.title
        lines = [f"{index}. **{linked}** — **NEW**"]
        lines += [f"- **{label}:** {sentence}" for label, sentence in self.beats]
        return "\n".join(lines)


def _days(value: int | None, noun: str = "day") -> str:
    if value is None:
        return ""
    return f"{value} {noun}{'' if abs(value) == 1 else 's'}"


def _overlap_beats(evidence: dict) -> list[tuple[str, str]]:
    beats = [
        (
            "What overlaps",
            "It reports a result close to the contribution this project claims.",
        )
    ]
    differences = evidence.get("differences") or []
    if differences:
        # Deterministic and literal: these are the project's own planned
        # components and data the paper's précis never mentions. The model may
        # phrase it later; it may not choose what is on the list.
        beats.append(
            (
                "Where you still differ",
                "It does not mention " + ", ".join(differences[:3]) + ".",
            )
        )
    beats.append(
        (
            "Do this week",
            "Read it against your framing and decide whether your claim still "
            "stands where it is.",
        )
    )
    return beats


def _blocker_beats(evidence: dict) -> list[tuple[str, str]]:
    blocker = evidence.get("blocker_text") or "a blocker you listed"
    offer = evidence.get("offer") or ""
    beats = [("Unblocks", f"What it offers speaks to {blocker}.")]
    if offer:
        beats.append(("On offer", offer))
    beats.append(
        ("Do this week", "Check the licence and whether it fits your setup.")
    )
    return beats


def _timeline_beats(evidence: dict) -> list[tuple[str, str]]:
    due = evidence.get("due_date") or ""
    slack = evidence.get("slack_days")
    milestone = evidence.get("milestone_what") or "your milestone"
    buffer_days = evidence.get("buffer_days")
    source = evidence.get("buffer_source") or ""
    line = f"Due {due}"
    if slack is not None:
        line += f", {_days(slack)} after {milestone}"
    if buffer_days is not None:
        line += f" — above your {_days(buffer_days)} buffer"
        if source:
            line += f" ({source})"
    beats = [("Fits your timeline", line + ".")]
    if evidence.get("anticipated"):
        beats.append(
            (
                "Caveat",
                "This date is projected from the last cycle, not published.",
            )
        )
    return beats


def _deadline_beats(evidence: dict) -> list[tuple[str, str]]:
    previous = evidence.get("previous_due_date") or ""
    due = evidence.get("due_date") or ""
    direction = "earlier" if evidence.get("moved_earlier") else "later"
    beats = [
        ("What changed", f"The deadline moved {direction}, from {previous} to {due}.")
    ]
    days = evidence.get("days")
    if days is not None:
        beats.append(("Now due in", _days(days) + "."))
    return beats


def _team_gap_beats(evidence: dict) -> list[tuple[str, str]]:
    requirement = evidence.get("requirement") or "expertise it names"
    return [
        ("Team gap", f"It requires {requirement}, which nobody on the team lists."),
        (
            "Do this week",
            "Decide whether to bring someone in, or let this one go.",
        ),
    ]


_BEATS = {
    ProjectAlert.Trigger.OVERLAP_RISK: _overlap_beats,
    ProjectAlert.Trigger.UNBLOCKS: _blocker_beats,
    ProjectAlert.Trigger.TIMELINE: _timeline_beats,
    ProjectAlert.Trigger.DEADLINE_MOVED: _deadline_beats,
    ProjectAlert.Trigger.TEAM_GAP: _team_gap_beats,
}


def block_for(alert: ProjectAlert) -> AlertBlock:
    """One stored alert as a renderable block."""
    metadata = (getattr(alert.content, "metadata", None) or {}) if alert.content else {}
    build = _BEATS.get(alert.trigger, lambda _e: [])
    return AlertBlock(
        project_label=alert.project.name if alert.project_id else "",
        trigger=alert.trigger,
        trigger_label=TRIGGER_LABELS.get(alert.trigger, alert.trigger),
        title=metadata.get("title") or metadata.get("name") or "(untitled)",
        url=getattr(alert.content, "source_url", "") or "",
        beats=build(alert.evidence or {}),
        content_id=str(alert.content_id or ""),
    )


def open_alerts(target_filter: dict, day: date | None = None) -> list[ProjectAlert]:
    """Today's open alerts for one target, in the order the report shows them."""
    day = day or timezone.localdate()
    return list(
        ProjectAlert.objects.filter(
            **target_filter, fired_on=day, status=ProjectAlert.Status.OPEN
        )
        .select_related("project", "content")
        .order_by("project__name", "trigger")
    )


def attention_section(blocks: list[AlertBlock]) -> str:
    """The report's "Needs your attention" section, or ``""`` when nothing fired.

    Rendered in code, not by the model: every number in it came from a matcher,
    and a section the model composed could put a different one in.
    """
    if not blocks:
        return ""
    lines = ["## Needs your attention"]
    index = 1
    current = ""
    for block in blocks:
        heading = f"{block.project_label} · {block.trigger_label}"
        if heading != current:
            lines.append(f"### {heading}")
            current = heading
        lines.append(block.as_markdown(index))
        index += 1
    return "\n\n".join(lines)


def discord_lines(blocks: list[AlertBlock]) -> list[tuple[str, str, str, str]]:
    """``(project, trigger, title, url)`` rows for the post's attention field."""
    return [
        (block.project_label, block.trigger_label, block.title, block.url)
        for block in blocks
    ]


def notify(alerts: list[ProjectAlert]) -> int:
    """Put today's alerts on the reader's bell. Returns how many were new.

    Fires for **every** cadence (plan 3.7). Cadence governs Discord and nothing
    else, and the bell is the surface that makes that true: a weekly-cadence
    reader who opens the app on a Wednesday sees the same two alerts a
    daily-cadence reader was DM'd that morning.

    ``dedupe_key`` mirrors the alert's own uniqueness — target, project, item,
    trigger — so a re-run of the nightly chain adds nothing, and an alert that
    fired once is never re-announced.
    """
    from apps.accounts.models import Lab

    from tools.delivery.models import Notification

    made = 0
    for alert in alerts:
        reader = alert.target_user
        if reader is None or isinstance(alert.target, Lab):
            # A lab alert belongs to the lab's surfaces. Fanning it out to every
            # member's bell would make one finding ring eight times, and the lab
            # report already carries it.
            continue
        key = (
            f"project_alert:{reader.id}:{alert.project_id}:"
            f"{alert.content_id}:{alert.trigger}"
        )
        if Notification.objects.filter(dedupe_key=key).exists():
            continue
        block = block_for(alert)
        Notification.objects.create(
            user=reader,
            kind=Notification.Kind.PROJECT_ALERT,
            content=alert.content,
            title=f"{block.project_label} · {block.trigger_label}",
            body=block.title,
            url=block.url,
            dedupe_key=key,
        )
        made += 1
    return made
