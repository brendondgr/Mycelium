"""Write the Monday weekly: one synthesis call per project, then the frame.

The daily reports a run. The weekly reports a **week and a project** — what
happened to the work, not what arrived in the feed — and that is a different
document with a different failure mode. A daily that overstates something is
corrected tomorrow; a weekly that is confidently wrong about a project's own
research is wrong in the reader's own domain and takes the rest of the report's
credibility with it.

Four things hold it to the ground:

1. **A closed packet** (:mod:`tools.delivery.weekly_build`). The model sees the
   week's items, the project's stated claim, the matchers' rows, and what the
   reader did — and nothing else.
2. **Citations.** Every factual sentence about an item carries ``[P#]``.
3. **The verifier** (:mod:`tools.delivery.weekly_verify`), which removes any
   sentence whose citation does not resolve or whose numbers the packet does not
   contain.
4. **A code frame.** The deadline horizon, the movement counts, the checked
   footer and the references block are rendered from structured data. A model
   renumbering the references would silently re-point every citation in the
   document (plan H6).

A model that is unreachable does not stop the weekly. Each project falls back to
a deterministic section built from the same packet, which is shorter and says
less but says nothing that is not in the packet — the same contract the daily's
fallback has always had.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date

from django.utils import timezone

from tools.delivery.report_grammar import references_block
from tools.delivery.weekly_packet import WeeklyPacket
from tools.delivery.weekly_verify import Verification, verify_body

logger = logging.getLogger(__name__)

CompleteFn = Callable[[str, str], str | None]

#: Bumped whenever the prompt or the section contract below changes.
WEEKLY_VERSION = "w2"

#: Words per project section. The ceiling is enforced by trimming whole sentences
#: (plan H5) rather than by asking the model nicely, because a model asked for
#: 700 words writes 900 and the reader pays for the difference.
PROJECT_WORD_CEILING = 700
OVERVIEW_WORD_CEILING = 700

_SYSTEM = (
    "You are Mylo, writing one project's week for the researcher who owns it. "
    "You are given a closed evidence packet: numbered items, the project's own "
    "stated claim, what the deterministic matchers computed, and what the "
    "reader did this week. Write markdown.\n"
    "Rules:\n"
    "- Every factual sentence about an item ends with its citation, like [P3]. "
    "A sentence you cannot cite is a sentence you must not write.\n"
    "- Never state a number, a date, or a day count that is not in the packet. "
    "The matchers computed those; you copy them.\n"
    "- No percentages, no scores, no 'relevance', no encouragement.\n"
    "- An item the packet marks as already alerted gets a status line — what "
    "happened to it since — not a fresh write-up.\n"
    "- Say what to DO. A sentence a reader cannot act on is a sentence that "
    "wasted their Monday.\n"
    "- If the packet does not support a section, omit the section.\n"
    "- The packet may list this week's changes to the project, numbered like "
    "O2. When an item bears directly on one — a blocker it addresses, a method "
    "just dropped — you may say so in one sentence citing both, like [P3][O2]. "
    "Never invent a connection, and never restate a change on its own.\n"
    "- Under 'Funding and team' you MAY name members the packet lists as "
    "covering a requirement, and you may say which stated research area of "
    "theirs matched. Say nothing else about any person — never their "
    "citizenship, career stage, or eligibility for anything."
)

_OVERVIEW_SYSTEM = (
    "You are Mylo, opening a researcher's weekly report. You are given each "
    "project's section, already written and already checked. Write at most five "
    "numbered lines: the five things that most need a decision this week, most "
    "urgent first, each naming the project and citing its item like [P3]. "
    "Introduce no new fact and no new number. Markdown only."
)


def _project_prompt(packet: WeeklyPacket, project) -> str:
    import json

    return (
        f"Week of {packet.week_start.isoformat()} to {packet.week_end.isoformat()}.\n"
        f"Write the section for the project below, under 700 words.\n\n"
        "Suggested structure (adapt or omit as the packet supports):\n"
        "  ### Flagged earlier this week   (status lines, not rewrites)\n"
        "  ### Threats to your contribution\n"
        "  ### Use now\n"
        "  ### Venues that fit your timeline\n"
        "  ### Funding and team\n\n"
        f"PACKET\n{json.dumps(project.as_dict(), indent=1, default=str)}"
    )


def _trim_words(text: str, ceiling: int) -> str:
    """Cut to ``ceiling`` words on a sentence boundary (plan H5).

    Whole sentences only. A section that stops mid-clause reads as a bug in the
    product, and the reader cannot tell whether the missing half mattered.
    """
    words = text.split()
    if len(words) <= ceiling:
        return text
    from tools.delivery.weekly_verify import sentences

    kept: list[str] = []
    used = 0
    for sentence in sentences(text):
        count = len(sentence.split())
        if used + count > ceiling:
            break
        kept.append(sentence)
        used += count
    return " ".join(kept).strip() or " ".join(words[:ceiling])


def _fallback_section(project) -> str:
    """A project's week with no model involved.

    Built entirely from the packet's own structured rows, so it says less than a
    written section and nothing the packet does not contain. It is the baseline
    product rather than a degraded one — the same contract the daily's fallback
    has always had.
    """
    lines: list[str] = []
    if project.stage:
        lines.append(f"Stage: {project.stage}.")
    if project.already_alerted:
        noun = "alert" if len(project.already_alerted) == 1 else "alerts"
        lines.append(
            f"{len(project.already_alerted)} {noun} raised earlier this week."
        )
    fits = [row for row in project.timeline_rows if row.get("status") == "fits"]
    if fits:
        nearest = fits[0]
        lines.append(
            f"{len(fits)} venue(s) reachable from your next milestone; "
            f"the nearest closes {nearest.get('due_date')}."
        )
    gaps = [gap for gap in project.team_gaps if gap.get("is_gap")]
    covered = [gap for gap in project.team_gaps if not gap.get("is_gap")]
    if gaps:
        needs = ", ".join(gap["requirement"] for gap in gaps[:3])
        lines.append(f"Requires expertise nobody on the team lists: {needs}.")
    for gap in covered[:2]:
        names = ", ".join(match["name"] for match in gap.get("covered_by") or [])
        if names:
            lines.append(f"Best suited to {gap['requirement']}: {names}.")
    if project.entered:
        lines.append(f"{project.entered} item(s) entered this project's lists.")
    if not lines:
        lines.append("Nothing moved for this project this week.")
    return " ".join(lines)


def write_project_section(
    packet: WeeklyPacket, project, *, complete: CompleteFn | None = None
) -> tuple[str, str]:
    """One project's section. Returns ``(markdown, origin)``."""
    if project.is_quiet:
        # Two lines, by design (plan A.2). A quiet project still appears — a
        # project that vanishes from the weekly reads as one that was dropped.
        return _fallback_section(project), "fallback"
    ask = complete if complete is not None else _settings_complete()
    try:
        raw = ask(_SYSTEM, _project_prompt(packet, project))
    except Exception as exc:  # noqa: BLE001 — degrade, never raise
        logger.warning("weekly synthesis unavailable for %s (%s)", project.label, exc)
        raw = None
    prose = (raw or "").strip()
    if not prose:
        return _fallback_section(project), "fallback"
    return _trim_words(prose, PROJECT_WORD_CEILING), "llm"


def write_overview(
    packet: WeeklyPacket, sections: list[tuple[str, str]], *,
    complete: CompleteFn | None = None,
) -> tuple[str, str]:
    """"Your week in five lines". Returns ``(markdown, origin)``."""
    if not sections:
        return "", ""
    ask = complete if complete is not None else _settings_complete()
    body = "\n\n".join(f"## Project · {label}\n{text}" for label, text in sections)
    try:
        raw = ask(_OVERVIEW_SYSTEM, body)
    except Exception as exc:  # noqa: BLE001
        logger.warning("weekly overview unavailable (%s)", exc)
        raw = None
    prose = (raw or "").strip()
    if prose:
        return _trim_words(prose, OVERVIEW_WORD_CEILING), "llm"
    return _overview_fallback(packet), "fallback"


def _overview_fallback(packet: WeeklyPacket) -> str:
    lines = []
    for index, project in enumerate(packet.projects, start=1):
        if project.is_quiet:
            continue
        alerts = len(project.already_alerted)
        bits = []
        if alerts:
            bits.append(f"{alerts} alert(s) raised")
        if project.entered:
            bits.append(f"{project.entered} item(s) entered its lists")
        lines.append(f"{index}. **{project.label}** — " + ", ".join(bits) + ".")
        if len(lines) >= 5:
            break
    return "\n".join(lines)


def personal_block(packet: WeeklyPacket) -> str:
    """The reader's own entrants, as reference rows rendered by code.

    Deterministic rather than written: these are items with no project to judge
    them against, so there is nothing for a synthesis call to say beyond what the
    per-item write-up already said. Listing them costs nothing and leaves a
    reader with no projects holding a real document rather than an empty one.
    """
    if not packet.personal:
        return ""
    lines = ["## Personal"]
    for index, item in enumerate(packet.personal, start=1):
        linked = f"[{item.title}]({item.url})" if item.url else item.title
        verdict = (item.writeup or {}).get("verdict") or ""
        meta = " · ".join(bit for bit in ("**NEW**", verdict.title()) if bit)
        lines.append(f"{index}. **{linked}** — {meta} [P{item.n}]")
        beats = (item.writeup or {}).get("beats") or []
        if beats:
            lines.append(f"{beats[0]} [P{item.n}]")
    return "\n".join(lines)


def deadline_horizon_block(packet: WeeklyPacket) -> str:
    """The next ten weeks, as a table rendered by code (plan A.2).

    A table, and not the model's: every date and day count in it is a matcher's,
    and the buffer each verdict used is named beside it so a reader who disagrees
    with "not viable" can see which of their own settings produced it.
    """
    rows = packet.deadline_horizon
    if not rows:
        return ""
    lines = [
        "## Deadline horizon · next 10 weeks",
        "",
        "| Due | What | Fit | Buffer |",
        "|---|---|---|---|",
    ]
    for row in rows[:20]:
        fit = row.get("status", "")
        if row.get("anticipated"):
            fit += " (anticipated)"
        lines.append(
            f"| {row.get('due_date', '')} | {row.get('venue', '')} | {fit} | "
            f"{row.get('buffer_days', '')} ({row.get('buffer_source', '')}) |"
        )
    return "\n".join(lines)


def compose_weekly(
    packet: WeeklyPacket,
    *,
    complete: CompleteFn | None = None,
    entails=None,
) -> tuple[str, Verification, str]:
    """The whole weekly body. Returns ``(markdown, verification, origin)``.

    Verification runs over the model-written half only: the code frame's numbers
    are the matchers' own, and running them through a check for "is this in the
    packet" would be asking the packet whether it contains itself.
    """
    sections: list[tuple[str, str]] = []
    used_llm = False
    for project in packet.projects:
        text, origin = write_project_section(packet, project, complete=complete)
        used_llm = used_llm or origin == "llm"
        sections.append((project.label, text))

    overview, overview_origin = write_overview(packet, sections, complete=complete)
    used_llm = used_llm or overview_origin == "llm"

    personal = personal_block(packet)
    written = "\n\n".join(
        part
        for part in (
            ("## Your week in five lines\n" + overview) if overview else "",
            *[f"## Project · {label}\n{text}" for label, text in sections],
            personal,
        )
        if part
    )
    checked, record = verify_body(written, packet, entails=entails)

    from tools.delivery.weekly_changes import what_changed_block

    frame = [
        # What changed (ambient Plan 09): the reader's own record, rendered by
        # code, so it sits in the frame rather than in the checked prose.
        what_changed_block(packet, reader=getattr(packet, "reader", None)),
        deadline_horizon_block(packet),
        # Mylo's reflection sits between the body and the references: it is about
        # the reader rather than about the corpus, so it closes the argument
        # rather than interrupting it.
        packet.reflection,
        references_block(packet.references()),
    ]
    footer = record.footer()
    if footer:
        frame.append(f"_{footer}_")

    body = "\n\n".join(part for part in [checked, *frame] if part.strip())
    if not body.strip():
        # A blank document is the one thing a weekly must never be. Saying so is
        # the honest answer to a week in which nothing entered anything, and it
        # is a different sentence from a week the run failed to write.
        body = (
            "Nothing entered your lists this week, and no project changed course. "
            "Mylo will keep watching; your feeds and search still hold everything "
            "matched so far."
        )
    return body, record, ("llm" if used_llm else "fallback")


def _settings_complete() -> CompleteFn:
    def ask(system: str, prompt: str) -> str | None:
        from apps.core.llm import LLMMessage, build_llm_client

        client = build_llm_client(component="weekly_report")
        response = client.complete(
            [LLMMessage("system", system), LLMMessage("user", prompt)],
        )
        return response.content

    return ask


def generate_weekly_for_user(user, *, complete=None, today: date | None = None):
    """Build, write, check and persist one person's weekly. Returns the row."""
    from tools.delivery.briefing import report_projects_for_user
    from tools.delivery.weekly_build import SURFACE_DM, build_weekly_packet

    today = today or timezone.localdate()
    packet = build_weekly_packet(
        target_filter={"target_user": user},
        projects=report_projects_for_user(user),
        reader=user,
        surface=SURFACE_DM,
        label=str(user.id),
        today=today,
    )
    return _persist(packet, {"user": user}, complete=complete, today=today)


def generate_weekly_for_lab(lab, *, complete=None, today: date | None = None):
    """The same for a lab or a department — **shared projects only** (plan 0.2 /
    H4), and only those whose scope reaches the server the weekly is posted to
    (``Org.post_width``): one body is both the web weekly and the post."""
    from tools.delivery.org_scope import org
    from tools.delivery.weekly_build import SURFACE_CHANNEL, build_weekly_packet

    scope = org(lab)
    today = today or timezone.localdate()
    packet = build_weekly_packet(
        target_filter=scope.target_filter,
        projects=scope.shared_projects(scope.post_width()),
        reader=scope.obj,
        surface=SURFACE_CHANNEL,
        label=scope.key,
        today=today,
    )
    return _persist(packet, scope.owner, complete=complete, today=today)


def _persist(packet, owner: dict, *, complete, today: date):
    from tools.delivery.models import DailyBriefing

    body, record, origin = compose_weekly(packet, complete=complete)
    briefing, _created = DailyBriefing.objects.update_or_create(
        **owner,
        generated_on=packet.week_start,
        kind=DailyBriefing.Kind.WEEKLY,
        defaults={
            "context_version": packet.context_version,
            "body": body,
            "origin": (
                DailyBriefing.Origin.LLM
                if origin == "llm"
                else DailyBriefing.Origin.FALLBACK
            ),
            "verification": record.as_dict(),
        },
    )
    return briefing
