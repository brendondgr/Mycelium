"""The lab's Discord post, and the report PDF that follows it.

A lab binds an updates channel in ``/setup`` and Mylo posts there once its
cadence says a post is due. The post is **two rows**, in this order:

1. **The post** — an overview of what kind of day it was, then statistics:
   overnight volume, how selective the match was, what entered a top list, the
   splits by category, theme and shared project, and the deadline horizon.
2. **The report as an attached PDF** — the same document each member gets by DM,
   compiled for the lab. Pasting the report into the channel as message text was
   tried and is wrong: a day's report runs to thousands of words, and a channel
   that receives all of it every morning is a channel people mute.

The post used to be a tally by research theme and nothing else — names and
numbers. It could not answer the question a reader opens it with, which is
whether that was a lot or a little: "Knowledge graphs & agents — 5 papers" is the
same five whether Mylo read two thousand papers or forty. The numbers now come
from :class:`~apps.content.report_stats.ReportStats`, derived from the very
:class:`~apps.content.daily_report.ReportData` the attached PDF renders, so there
is one theme count rather than two that disagree.

Three things it deliberately is not:

* **Not a second source of truth.** It reads the same ``RelevanceScore`` rows and
  the same ``DailyBriefing`` the lab's feed and portal read.
* **Not a ping.** ``allowed_mentions.parse`` stays empty and no member is tagged —
  which matters more now that the report names who each item suits. It is an
  update, not a summons.
* **Not a channel that speaks when it has nothing to say.** A day with no alerts
  and nothing new posts nothing at all (plan H7). The web still shows the day.
"""

from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from apps.content import delivery, discord_embeds
from apps.content.daily_report import ReportData, compile_report_for_lab
from apps.content.daily_report_pdf import render_report_pdf
from apps.content.models import DailyBriefing
from apps.integrations.services import outbox, resolve

logger = logging.getLogger(__name__)

#: The line above the attached PDF. Discord shows the file card underneath it.
REPORT_MESSAGE = "Today's full report is attached."


# --------------------------------------------------------------------------- #
# Eligibility
# --------------------------------------------------------------------------- #
def eligible_labs(labs, *, on: date | None = None, kind: str = delivery.DAILY) -> list:
    """Labs that should receive a channel post today.

    Every condition is checked here rather than trusted from setup time:

    * **cadence** — a post of this shape is due to this lab on its *own* local date
      (plan 0.4). The lab's briefing is still written and its members still see it
      on the web; only the channel waits;
    * the bot add-on is **live now** — a lapsed plan goes quiet, and the check has to
      happen at delivery or it never happens at all;
    * the guild link is active;
    * an updates channel is bound. **A blank binding is a deliberate opt-out and is
      respected in silence** — no warning, no incident. A lab that turned this off
      should not be told about it every morning.

    ``kind`` is what is being sent — :data:`delivery.DAILY` or
    :data:`delivery.WEEKLY`. Passing it rather than assuming "daily" is what lets
    the Monday weekly reach a weekly-cadence lab through the same gate.
    """
    from apps.billing.entitlements import Feature, lab_has_feature

    out = []
    for lab in labs:
        local_date = on or delivery.local_today(lab)
        if kind not in delivery.push_kinds(delivery.lab_cadence(lab), local_date):
            continue
        if not lab_has_feature(lab, Feature.BOT_SERVER):
            continue
        # Ambient Plan 11: a lab whose Slack workspace is its primary surface
        # gets its posts there (``slack_reports``), not twice.
        from apps.content.slack_reports import slack_is_primary

        if slack_is_primary(lab):
            continue
        link = resolve.primary_server_for_lab(lab, "updates")
        if link is None or link.state != resolve.GUILD_ACTIVE:
            continue
        if not resolve.get_updates_channel_for_lab(lab):
            continue
        out.append(lab)
    return out


# --------------------------------------------------------------------------- #
# Sending
# --------------------------------------------------------------------------- #
def queue_lab_digest(
    lab,
    *,
    on: date | None = None,
    data: ReportData | None = None,
    alerts=None,
):
    """Queue one channel post for one lab, once per day.

    ``dedupe_key`` is ``lab_digest:<lab>:<date>`` and the outbox enforces it as a
    database uniqueness constraint, so re-running the daily pipeline is a no-op
    rather than a second post. That is the whole of the idempotency guarantee — no
    separate ledger, no "have I sent today?" query that could race.

    ``data`` is passed in by the command, which compiles the lab's day once and
    hands the same object to this and to :func:`queue_lab_report`; compiling twice
    would double the work and, worse, could produce two different mornings if a
    score landed between them.
    """
    on = on or timezone.localdate()
    data = data if data is not None else compile_report_for_lab(lab)
    if alerts is None:
        from apps.content.alert_report import block_for, discord_lines, open_alerts

        alerts = discord_lines(
            [block_for(alert) for alert in open_alerts({"target_lab": lab}, on)]
        )
    from apps.content.briefing import report_projects_for_lab
    from apps.content.weekly_changes import changed_today

    # Ambient Plan 09: a stated-state change accepted today is one line in the
    # day's post — never a post of its own, and never a development (OD-09a).
    changes = changed_today(
        reader=lab, projects=report_projects_for_lab(lab), is_lab=True
    )
    if is_quiet(data) and not changes:
        # Nothing new and nothing wrong. A daily "I found nothing" post trains
        # people to ignore the channel, which costs more than the silence does
        # (plan H7). The lab's web report still shows the day.
        return None, False

    channel_id = resolve.get_updates_channel_for_lab(lab)
    if not channel_id:
        return None, False

    return outbox.enqueue_channel(
        dedupe_key=delivery.lab_digest_key(lab, on),
        kind="lab_digest",
        channel_id=channel_id,
        lab=lab,
        embed=discord_embeds.lab_post_embed(
            data, data.stats, alerts=alerts, changes=changes
        ),
        subject_type="lab_digest",
        subject_id=str(lab.id),
        not_before=delivery.send_time(lab, on),
    )


def is_quiet(data: ReportData) -> bool:
    """Whether this day has nothing to push — see :attr:`ReportStats.is_quiet`."""
    return data.stats.is_quiet


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


def queue_lab_report(
    lab,
    *,
    on: date | None = None,
    data: ReportData | None = None,
    workdir: Path | None = None,
):
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

    data = data if data is not None else compile_report_for_lab(lab)
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
        dedupe_key=delivery.lab_report_key(lab, on),
        kind="lab_report",
        channel_id=channel_id,
        lab=lab,
        content=REPORT_MESSAGE,
        attachment_path=str(path),
        attachment_filename=path.name,
        subject_type="lab_report",
        subject_id=str(lab.id),
        # One second after the summary, so the outbox — which claims by
        # (next_attempt_at, id) — still posts the file under the counts it
        # belongs to once both rows are held for the same local hour.
        not_before=delivery.send_time(lab, on) + timedelta(seconds=1),
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
