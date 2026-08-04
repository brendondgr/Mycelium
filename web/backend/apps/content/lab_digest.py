"""The lab's daily digest, posted to the channel it already configured.

A lab binds an updates channel in ``/setup``, sees a success confirmation, and — until
now — waits forever. Nothing ever posted there. This is the missing send.

The post is **two parts**, in this order:

1. **A summary**: how much Mylo found, broken down by research theme — the theme's
   name and its counts, nothing else. The first version of this named three example
   items under every theme, which read as a wall of half-sentences and truncated
   conference titles, and still answered neither "how much?" nor "what did it say?".
2. **The report as an attached PDF** — the same document each member already gets by
   DM, compiled for the lab. Pasting the report into the channel as message text was
   tried and is wrong: a day's report runs to thousands of words, and a channel that
   receives all of it every morning is a channel people mute.

Two things it deliberately is not:

* **Not a second source of truth.** It reads the same ``RelevanceScore`` rows and the
  same ``DailyBriefing`` the lab's feed and portal read, so neither the summary nor
  the PDF can drift from what the portal shows.
* **Not a ping.** ``allowed_mentions.parse`` stays empty and no member is tagged —
  which matters more now that the report names who each item suits. It is an update,
  not a summons.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from apps.content.briefing import LAB_BRIEFING_CATEGORIES, _suggested_scores
from apps.content.daily_report import compile_report_for_lab
from apps.content.daily_report_pdf import render_report_pdf
from apps.content.models import ContentItem, DailyBriefing
from apps.integrations.services import outbox, resolve

logger = logging.getLogger(__name__)

#: Themes shown before the post stops being scannable. Matches the cluster ceiling.
MAX_THEMES = 8

#: The line above the attached PDF. Discord shows the file card underneath it.
REPORT_MESSAGE = "Today's full report is attached."

_CATEGORY_TYPE = {
    "papers": ContentItem.Type.PAPER,
    "grants": ContentItem.Type.GRANT,
    "conferences": ContentItem.Type.CONFERENCE,
    "fellowships": ContentItem.Type.FELLOWSHIP,
}
_NOUN = {
    "papers": "paper",
    "grants": "grant",
    "conferences": "conference",
    "fellowships": "fellowship",
}


@dataclass
class ThemeBlock:
    """One research theme's share of the day — its name and how much it found."""

    label: str
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.counts.values())


@dataclass
class LabDigest:
    lab_name: str
    lab_slug: str
    on: date
    total: int = 0
    counts: dict[str, int] = field(default_factory=dict)
    themes: list[ThemeBlock] = field(default_factory=list)
    #: Items carrying no theme attribution, as one count block (never itemised).
    ungrouped: ThemeBlock | None = None

    @property
    def is_empty(self) -> bool:
        return self.total == 0


def compile_lab_digest(lab, *, on: date | None = None) -> LabDigest:
    """Gather the lab's day from the same scores its feed and briefing read."""
    on = on or timezone.localdate()
    digest = LabDigest(lab_name=lab.name, lab_slug=lab.slug, on=on)

    by_theme: dict[str, ThemeBlock] = {}
    ungrouped = ThemeBlock(label="Not yet themed")
    for category in LAB_BRIEFING_CATEGORIES:
        content_type = _CATEGORY_TYPE.get(category)
        if content_type is None:
            continue
        scores = _suggested_scores({"target_lab": lab}, content_type)
        if not scores:
            continue
        digest.counts[category] = len(scores)
        digest.total += len(scores)
        for score in scores:
            label = score.signals.get("cluster_label") or ""
            block = (
                by_theme.setdefault(label, ThemeBlock(label=label))
                if label
                else ungrouped
            )
            block.counts[category] = block.counts.get(category, 0) + 1

    # Busiest theme first: a channel post is skimmed, so the lab's main focus should
    # be the first thing read, not whichever category happened to sort first.
    ordered = sorted(by_theme.values(), key=lambda b: -b.total)
    digest.themes = ordered[:MAX_THEMES]
    digest.ungrouped = ungrouped if ungrouped.total else None
    return digest


# --------------------------------------------------------------------------- #
# Eligibility
# --------------------------------------------------------------------------- #
def eligible_labs(labs) -> list:
    """Labs that should receive a channel digest today.

    Every condition is checked here rather than trusted from setup time:

    * the bot add-on is **live now** — a lapsed plan goes quiet, and the check has to
      happen at delivery or it never happens at all;
    * the guild link is active;
    * an updates channel is bound. **A blank binding is a deliberate opt-out and is
      respected in silence** — no warning, no incident. A lab that turned this off
      should not be told about it every morning.
    """
    from apps.billing.entitlements import Feature, lab_has_feature

    out = []
    for lab in labs:
        if not lab_has_feature(lab, Feature.BOT_SERVER):
            continue
        link = resolve.get_guild_link_for_lab(lab)
        if link is None or link.state != resolve.GUILD_ACTIVE:
            continue
        if not resolve.get_updates_channel_for_lab(lab):
            continue
        out.append(lab)
    return out


# --------------------------------------------------------------------------- #
# Sending
# --------------------------------------------------------------------------- #
def queue_lab_digest(lab, *, on: date | None = None, digest: LabDigest | None = None):
    """Queue one channel post for one lab, once per day.

    ``dedupe_key`` is ``lab_digest:<lab>:<date>`` and the outbox enforces it as a
    database uniqueness constraint, so re-running the daily pipeline is a no-op
    rather than a second post. That is the whole of the idempotency guarantee — no
    separate ledger, no "have I sent today?" query that could race.
    """
    on = on or timezone.localdate()
    digest = digest or compile_lab_digest(lab, on=on)
    if digest.is_empty:
        # Nothing found today. A daily "I found nothing" post trains people to
        # ignore the channel, which costs more than the silence does.
        return None, False

    channel_id = resolve.get_updates_channel_for_lab(lab)
    if not channel_id:
        return None, False

    return outbox.enqueue_channel(
        dedupe_key=f"lab_digest:{lab.id}:{on:%Y-%m-%d}",
        kind="lab_digest",
        channel_id=channel_id,
        lab=lab,
        embed=digest_embed(digest),
        subject_type="lab_digest",
        subject_id=str(lab.id),
    )


def _tally(counts: dict[str, int], *, bold: bool = False) -> str:
    """"3 papers · 51 grants · 75 conferences" — the one phrasing used throughout."""
    parts = []
    for category, n in counts.items():
        noun = _NOUN.get(category, category)
        number = f"**{n}**" if bold else str(n)
        parts.append(f"{number} {noun}{'' if n == 1 else 's'}")
    return " · ".join(parts)


def digest_embed(digest: LabDigest) -> dict:
    """The channel post: how much Mylo found, by theme. Names and numbers only.

    Example items used to sit under every theme — three truncated titles, each with a
    percentage. In a channel that read as noise: too long to skim, too little to act
    on, and it repeated what the report immediately below now says properly. A reader
    scanning this wants one thing, which is where today's work landed.

    Bounded by construction rather than truncation: at most eight themes plus one
    "not yet themed" row, each a single line, well inside Discord's 25 fields and
    6000 characters.
    """
    embed = {
        "title": f"{digest.lab_name} — what Mylo found today",
        "description": _tally(digest.counts, bold=True) or "A quiet day.",
        "color": 0x3B7A57,
        "fields": [],
    }
    blocks = list(digest.themes)
    # With no themes at all the "not yet themed" row would just restate the tally
    # directly above it, so a lab that has not organised its focus simply gets the
    # one line rather than the same numbers twice.
    if digest.ungrouped is not None and blocks:
        blocks.append(digest.ungrouped)
    for block in blocks:
        embed["fields"].append(
            {
                "name": block.label,
                "value": _tally(block.counts) or "—",
                "inline": False,
            }
        )

    base = str(getattr(settings, "DISCORD_APP_BASE_URL", "") or "").rstrip("/")
    if base:
        embed["url"] = f"{base}/app/daily"
    embed["footer"] = {"text": "The full report is attached below."}
    return embed


# --------------------------------------------------------------------------- #
# The report, attached as a PDF
# --------------------------------------------------------------------------- #
def report_dir() -> Path:
    """Where a queued report waits for its send.

    Durable by necessity, not preference: the bytes must survive until the drain
    reaches the row, which may be minutes away and, during an outage, longer. Shared
    with the personal report (:mod:`.daily_report_send`), and swept by the outbox's
    own retention pass once a row settles.
    """
    return Path(getattr(settings, "DISCORD_OUTBOX_ATTACHMENT_DIR", "data/outbox"))


def report_filename(lab, on: date) -> str:
    return f"mylo-report-{lab.slug}-{on:%Y-%m-%d}.pdf"


def queue_lab_report(lab, *, on: date | None = None, workdir: Path | None = None):
    """Render the lab's day to a PDF and queue it as an attachment on the summary's
    channel.

    The same document a member receives by DM, compiled for the lab: cover, contents,
    the written report, the top articles and opportunities, then the full appendix.
    Reusing :mod:`.daily_report`/:mod:`.daily_report_pdf` wholesale is the point — a
    lab's report should not be a different artefact from a person's, and a second
    renderer would drift from the first within a release.

    Queued after the summary, and the outbox claims by ``(next_attempt_at, id)`` and
    delivers one at a time, so the file lands under the counts it belongs to.
    ``dedupe_key`` is ``lab_report:<lab>:<date>``, so re-running the daily chain is a
    no-op rather than a second upload.

    Returns ``True`` when a row was queued. A lab with nothing to report queues
    nothing — the summary still posts, and the day is not spent explaining absence.
    """
    on = on or timezone.localdate()
    channel_id = resolve.get_updates_channel_for_lab(lab)
    if not channel_id:
        return False

    data = compile_report_for_lab(lab)
    if not data.total_count and not data.briefing_markdown.strip():
        return False

    workdir = workdir or report_dir()
    workdir.mkdir(parents=True, exist_ok=True)
    path = workdir / report_filename(lab, on)
    # Written through a temp file and moved into place: the path is deterministic per
    # (lab, day), so a re-run would otherwise truncate a file the drain might be
    # reading at that moment. os.replace is atomic, so a reader sees one whole PDF or
    # the other, never half of each.
    staged = path.with_name(path.name + ".part")
    staged.write_bytes(render_report_pdf(data))
    os.replace(staged, path)

    _row, created = outbox.enqueue_channel(
        dedupe_key=f"lab_report:{lab.id}:{on:%Y-%m-%d}",
        kind="lab_report",
        channel_id=channel_id,
        lab=lab,
        content=REPORT_MESSAGE,
        attachment_path=str(path),
        attachment_filename=path.name,
        subject_type="lab_report",
        subject_id=str(lab.id),
    )
    return bool(created)


def written_briefing_body(lab) -> str:
    """The lab's written daily report, or an empty string when none exists yet."""
    briefing = DailyBriefing.latest_for(lab=lab)
    return (briefing.body or "") if briefing is not None else ""


def written_briefing_line(lab) -> str:
    """The first line of the lab's written briefing, if one exists."""
    body = written_briefing_body(lab)
    for line in body.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line
    return ""
