"""The weekly's "What changed" — what Mylo's understanding did this week, for whom.

Ambient Plan 09. Every change that took effect this week (``AppliedChange``,
read through ``apps.ambient.read``) is numbered ``[O#]`` and rendered by code,
never by the model: the rows are facts about the reader's own record, and the
model has nothing to add to "you confirmed it on Tuesday" except the chance of
getting it wrong.

Two streams, kept apart by the query rather than by the renderer:

- **Your understanding** — a person's own changes (explorations, confirmed
  understanding, profile edits, undos). Personal weekly only.
- **Projects** — developments recorded or confirmed, stated state accepted,
  undone. A person's weekly carries the changes on their projects (their own,
  and lab-visible ones on lab projects they are on); a lab weekly carries only
  lab-visible changes on the projects the lab shares. A personal change cannot
  reach a lab packet because the lab query cannot match one.

The project rows also travel inside each project's packet, so the synthesis
call may say why an item matters now ("your blocker on annotation cost is what
this addresses [P3][O2]") — and the verifier removes any sentence citing an
``[O#]`` the packet does not hold.

The one interpretive line — "you confirmed an exploration of X, so this week's
papers give it more attention" — is written by code from a confirmed
exploration row, and only when explorations actually move the ranking
(``AMBIENT_DRIFT_ENABLED``). Saying it while they do not would be a false
sentence about the reader's own report.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.utils import timezone

#: Which profile field an edit wrote, as a reader would say it.
FIELD_LABELS = {
    "interests.areas": "interests",
    "interests.clusters": "themes",
    "interests.skills": "skills",
    "interests.learning_goals": "learning goals",
    "interests.preferences": "preferences",
    "interests.trajectory": "direction",
    "slow.blockers": "blockers",
    "slow.method": "method",
}

#: Where an answer was given, as a report says it.
SURFACES = {"dm": "on Discord", "web": "on the web", "told": ""}

PERSONAL_KINDS = frozenset(
    {
        "exploration_confirmed",
        "exploration_kept",
        "exploration_dropped",
        "understanding_confirmed",
        "profile_edit",
    }
)


def _bounds(start: date, today: date) -> tuple[datetime, datetime]:
    """The week as aware instants: Monday 00:00 to the end of ``today``."""
    zone = timezone.get_current_timezone()
    since = timezone.make_aware(datetime.combine(start, time.min), zone)
    until = timezone.make_aware(
        datetime.combine(today + timedelta(days=1), time.min), zone
    )
    return since, until


def _day(iso: str) -> str:
    try:
        return date.fromisoformat(iso).strftime("%a %-d %b")
    except ValueError:
        return iso


def mylo_and_you_url() -> str:
    """The Mylo & you page, or "" when the instance has no public origin."""
    base = str(getattr(settings, "DISCORD_APP_BASE_URL", "") or "").rstrip("/")
    return f"{base}/app/mylo-and-you" if base else ""


def _linked(text: str, url: str) -> str:
    """``[text](url)``, or the plain text when there is no URL to point at."""
    return f"[{text}]({url})" if url else text


def collect(packet, *, target_filter: dict, projects: list, reader, today: date):
    """Fill the packet's change rows (numbered ``[O#]``) and the lines around
    them. Never raises: a weekly without its change log is still a weekly."""
    try:
        _collect(
            packet,
            target_filter=target_filter,
            projects=projects,
            reader=reader,
            today=today,
        )
    except Exception:  # noqa: BLE001 - the change log must not cost the report
        import logging

        logging.getLogger(__name__).exception("weekly changes unavailable")
        packet.changes = []


def _collect(packet, *, target_filter, projects, reader, today):
    from apps.ambient.read import answers_between, changes_between

    is_lab = "target_lab" in target_filter
    since, until = _bounds(packet.week_start, today)
    rows = changes_between(
        since=since,
        until=until,
        user=None if is_lab else reader,
        projects=projects,
    )
    if is_lab:
        # Belt and braces on the rule the query already enforces.
        project_ids = {str(p.pk) for p in projects}
        rows = [
            row
            for row in rows
            if row["visibility"] == "lab" and row["project_id"] in project_ids
        ]
    # An undo whose change is in the same week is the "(since undone)" on that
    # change's row, not a second row (EXP-2026-09-017 run 1).
    this_week = {row["id"] for row in rows}
    rows = [row for row in rows if row.get("undo_of") not in this_week]
    numbered = [{**row, "n": n} for n, row in enumerate(rows, start=1)]
    packet.changes = numbered

    by_project = {p.project_id: p for p in packet.projects}
    for row in numbered:
        project = by_project.get(row["project_id"])
        if project is not None and row["kind"] not in PERSONAL_KINDS:
            project.changes.append(
                {
                    "id": f"O{row['n']}",
                    "what": _project_text(row, reader=reader, is_lab=is_lab),
                    "on": row["on"],
                }
            )

    if is_lab:
        return
    packet.answers = answers_between(reader, since=since, until=until)
    from tools.delivery.briefing import by_attention

    ordered, leader = by_attention(reader, list(projects))
    if leader:
        packet.attention_lead = next(
            (p.name for p in ordered if str(p.pk) == str(leader)), ""
        )
    from tools.delivery.models import ReflectionProposal

    packet.proposals_waiting = ReflectionProposal.objects.filter(
        target_user=reader,
        status=ReflectionProposal.Status.PENDING,
        evidence__source="conversation",
    ).count()


def _who(row, *, reader, is_lab) -> str:
    if not is_lab and row["by_id"] == getattr(reader, "pk", None):
        return "you"
    return row["by_name"]


def _personal_text(row) -> str:
    where = SURFACES.get(row["surface"], "")
    where = f" {where}" if where else ""
    day = _day(row["on"])
    topic = f"**{row['topic']}**"
    kind = row["kind"]
    if kind == "exploration_confirmed":
        text = f"{topic} — in your reports; you confirmed it{where} on {day}."
    elif kind == "exploration_kept":
        text = f"{topic} — still exploring; you kept it{where} on {day}."
    elif kind == "exploration_dropped":
        text = f"{topic} — no longer explored, from {day}."
    elif kind == "understanding_confirmed":
        text = f"{topic} — confirmed as yours{where} on {day}."
    elif kind == "profile_edit":
        field = FIELD_LABELS.get(row["field"], "profile")
        text = f"{topic} — added to your {field}{where} on {day}."
    else:  # undone
        text = f"{topic} — undone on {day}."
    if row["undone"]:
        text = text[:-1] + " (since undone)."
    return text


def _project_text(row, *, reader, is_lab) -> str:
    who = _who(row, reader=reader, is_lab=is_lab)
    day = _day(row["on"])
    kind = row["kind"]
    topic = row["topic"]
    if kind == "development_recorded":
        told = "you told Mylo" if who == "you" else f"{who} told Mylo"
        text = f"{topic} — {told} on {day}."
    elif kind == "development_confirmed":
        text = f"{topic} — confirmed by {who} on {day}."
    elif kind == "state_edit":
        field = FIELD_LABELS.get(row["field"], "state")
        text = f"the stated {field} changed ({topic}) — accepted by {who} on {day}."
    elif kind == "undone":
        text = f"{topic} — undone by {who} on {day}."
    else:
        text = f"{topic} — {row['kind_label'].lower()} on {day}."
    if row["undone"]:
        text = text[:-1] + " (since undone)."
    return text


def interpretation(packet) -> str:
    """The one code-framed line about what a confirmed exploration does to this
    week's papers — only when explorations move the ranking at all."""
    if not getattr(settings, "AMBIENT_DRIFT_ENABLED", False):
        return ""
    confirmed = [
        row
        for row in packet.changes
        if row["kind"] == "exploration_confirmed" and not row["undone"]
    ]
    if not confirmed:
        return ""
    row = confirmed[-1]
    weekday = date.fromisoformat(row["on"]).strftime("%A")
    return (
        f"You confirmed an exploration of **{row['topic']}** on {weekday}, so this "
        f"week's papers give it more attention [O{row['n']}]. "
        f"Not right? {_linked('Tell me', mylo_and_you_url())}."
    )


def what_changed_block(packet, *, reader=None) -> str:
    """The section, rendered by code. Empty when nothing changed."""
    changes = getattr(packet, "changes", None) or []
    is_lab = packet.surface == "channel"
    personal = [row for row in changes if row["kind"] in PERSONAL_KINDS]
    if is_lab:
        personal = []
    project_rows = [
        row
        for row in changes
        if row["kind"] not in PERSONAL_KINDS and row["project_id"]
    ]
    undos = [
        row
        for row in changes
        if row["kind"] == "undone" and not row["project_id"] and not is_lab
    ]
    answers = getattr(packet, "answers", {}) or {}
    lead = getattr(packet, "attention_lead", "")
    waiting = getattr(packet, "proposals_waiting", 0)
    if not (personal or project_rows or undos or answers or lead or waiting):
        return ""

    lines = ["## What changed"]
    if personal or undos or answers:
        lines.append("### Your understanding")
        for row in personal + undos:
            lines.append(f"- {_personal_text(row)} [O{row['n']}]")
        answered = sum(answers.values())
        if answered:
            where = ", ".join(
                f"{count} {SURFACES.get(surface) or 'elsewhere'}"
                for surface, count in sorted(answers.items())
            )
            noun = "question" if answered == 1 else "questions"
            lines.append(
                f"- You answered {answered} of Mylo's {noun} this week ({where})."
            )
        line = interpretation(packet)
        if line:
            lines.append("")
            lines.append(line)
    if project_rows or lead or waiting:
        lines.append("### Projects")
        for row in project_rows:
            text = _project_text(row, reader=reader, is_lab=is_lab)
            lines.append(f"- **{row['project_name']}** — {text} [O{row['n']}]")
        if lead:
            lines.append(f"- Most of your conversation this week went to **{lead}**.")
        if waiting:
            noun = "change" if waiting == 1 else "changes"
            verb = "is" if waiting == 1 else "are"
            lines.append(
                f"- {waiting} suggested {noun} to a project's stated state {verb} "
                "waiting for you on its page."
            )
    if not is_lab:
        lines.append("")
        where = _linked("Mylo & you", mylo_and_you_url())
        lines.append(
            f"See, edit or undo any of these on {where}."
        )
    return "\n".join(lines)


# -- the daily's one line (Plan 09 steps 5 and 7) -----------------------------------

#: What a development that took effect does to the alerts, as a reader would
#: want to be told. Only the two changes the alerts act on (``alerts.py``).
_DEVELOPMENT_EFFECT = {
    "blocker_closed": (
        "no longer blocks it, so Mylo stopped flagging items that address it"
    ),
    "method_dropped": "was dropped, so Mylo no longer flags overlap on it",
}


def changed_today(*, reader, projects, is_lab: bool, now=None) -> list[str]:
    """The lines a daily carries about what took effect since yesterday's run.

    A person's daily: a yes that edited their profile or a project's stated
    state, and a development that changed what the alerts flag. A lab's daily:
    only a stated-state change accepted on a project the lab shares (OD-09a —
    the weekly is the unit for developments). Never raises.
    """
    try:
        return _changed_today(reader=reader, projects=projects, is_lab=is_lab, now=now)
    except Exception:  # noqa: BLE001 - a daily without this line is still a daily
        import logging

        logging.getLogger(__name__).exception("changed-today lines unavailable")
        return []


def _changed_today(*, reader, projects, is_lab, now):
    from apps.ambient.read import changes_between, developments_in_effect

    now = now or timezone.now()
    since = now - timedelta(hours=24)
    lines = []
    rows = changes_between(
        since=since, until=now, user=None if is_lab else reader, projects=projects
    )
    for row in rows:
        if row["undone"]:
            continue
        if row["kind"] == "state_edit" and row["project_id"]:
            field = FIELD_LABELS.get(row["field"], "state")
            who = _who(row, reader=reader, is_lab=is_lab)
            lines.append(
                f"**{row['project_name']}** — the stated {field} changed "
                f"({row['topic']}), accepted by {who}."
            )
        elif row["kind"] == "profile_edit" and not is_lab:
            field = FIELD_LABELS.get(row["field"], "profile")
            lines.append(f"**{row['topic']}** — added to your {field}; you said yes.")
    if is_lab:
        return lines
    for project in projects:
        for development in developments_in_effect(
            project, reader=reader, changes=tuple(_DEVELOPMENT_EFFECT)
        ):
            took_effect = (
                development.decided_at
                if development.status == "confirmed"
                else development.recorded_on
            )
            if took_effect is None or not (since <= took_effect <= now):
                continue
            lines.append(
                f"**{project.name}** — {development.topic} "
                f"{_DEVELOPMENT_EFFECT[development.change]}."
            )
    return lines


def with_changed_today(attention: str, lines: list[str]) -> str:
    """The "Needs your attention" section with the day's change lines added."""
    if not lines:
        return attention
    block = "\n".join(["### Changed today", *[f"- {line}" for line in lines]])
    return "\n\n".join([attention or "## Needs your attention", block])
