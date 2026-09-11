"""Orchestrate the daily "Mylo Report" Discord DM for all eligible users.

The delivery half of the daily PDF report. Eligibility is the intersection of three
gates already owned elsewhere:

* **entitled + active** — ``apps.content.tasks.select_users`` (holds
  ``SCHEDULED_REPORTS``; Free accounts are on-demand and never pushed a run),
* **linked + opted in + reachable** — ``resolve.report_recipient_user_ids`` (an
  ACTIVE Discord identity, ``daily_report_opt_out`` false, not a known-blocked DM).

The run is deliberately **phased** (the product brief's ordering), not interleaved:

1. compile every recipient's :class:`~apps.content.daily_report.ReportData`,
2. render every report to a PDF on disk,
3. **queue** every PDF as a personal DM.

Phase 3 used to send, and phase 4 deleted the PDFs immediately afterwards. Now that
delivery is queued, those bytes have to outlive this batch — the drain may run minutes
later, and an outage means later still. So the reports are written to a durable
directory (``DISCORD_OUTBOX_ATTACHMENT_DIR``) rather than a throwaway temp dir, and the
outbox retention sweep deletes each file once its row has actually settled. A report
that cannot be read at delivery time is a permanent failure, not an endless retry.

The ``compile_fn`` / ``render_fn`` / ``send_fn`` seams are injected so tests can
drive the whole flow without a database of scores or a live Discord. A failure for
one user is caught and counted; it never sinks the batch.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from django.conf import settings

from apps.content import delivery, discord_embeds, reminders_discord
from apps.content.daily_report import ReportData, compile_report_for_user
from apps.content.daily_report_pdf import render_report_pdf
from apps.content.urgent_alerts import send_urgent_alerts
from apps.integrations.services import resolve

logger = logging.getLogger(__name__)

CompileFn = Callable[[object], ReportData]
RenderFn = Callable[[ReportData], bytes]
# send_fn(user, report_data, path, filename) -> outcome with a bool `.ok`.
SendFn = Callable[..., object]
# urgent_fn(usernames, on=) -> a summary with `.sent`, `.errors`, `.error_detail`.
# Injected for the same reason the three above are: this module's flow is
# exercised without a database, and the urgent pass reads one.
UrgentFn = Callable[..., object]

REPORT_TITLE = "Your daily research report"


@dataclass
class SendSummary:
    eligible: int = 0
    #: Recipients whose day had no entrants and no alerts, so nothing was sent.
    quiet: int = 0
    #: Between-Monday deadline alerts sent to opted-in weekly-cadence readers.
    urgent: int = 0
    compiled: int = 0
    rendered: int = 0
    sent: int = 0
    unreachable: int = 0
    errors: int = 0
    error_detail: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "eligible": self.eligible,
            "quiet": self.quiet,
            "urgent": self.urgent,
            "compiled": self.compiled,
            "rendered": self.rendered,
            "sent": self.sent,
            "unreachable": self.unreachable,
            "errors": self.errors,
        }


def _alert_lines(target_filter: dict):
    """Today's open alerts as ``(project, trigger, title, url)`` rows.

    Read here rather than carried on ``ReportData``: the post is the only surface
    that wants them in this shape, and the document renders the full blocks.
    """
    from apps.content.alert_report import block_for, discord_lines, open_alerts

    return discord_lines([block_for(alert) for alert in open_alerts(target_filter)])


def _default_send(user, data: ReportData, path: Path, filename: str):
    local_date = delivery.local_today(user)
    return reminders_discord.send_personal_report(
        user,
        title=REPORT_TITLE,
        body=data.message_body(),
        # The overview-and-statistics embed (plan Phase 1). ``title``/``body``
        # stay filled so the plain path is still reachable, and so the outcome
        # log records what the post was about.
        embed=discord_embeds.personal_report_embed(
            data, data.stats, alerts=_alert_lines({"target_user": user})
        ),
        filename=filename,
        attachment_path=str(path),
        dedupe_key=delivery.daily_report_key(user, local_date),
        # Compiled in the nightly run, delivered at the recipient's morning. A
        # send hour already past means the run finished late, and the row is due
        # at once rather than held for a day (see ``delivery.send_time``).
        not_before=delivery.send_time(user, local_date),
    )


def _report_dir() -> Path:
    """Where a queued report waits for its send.

    Durable by necessity, not preference: the bytes must survive until the drain
    reaches the row, which may be minutes away and, during an outage, longer. The lab
    report (:mod:`.lab_digest`) writes its PDF to the same directory, so both are
    swept by the same outbox retention pass.
    """
    return Path(getattr(settings, "DISCORD_OUTBOX_ATTACHMENT_DIR", "data/outbox"))


def eligible_recipients(usernames: list[str] | None, *, on: date | None = None):
    """The users who should receive the daily report DM, in a stable order.

    Four gates, in order of how expensive they are to check: entitled and active
    (``select_users``), then **cadence** — whether a daily push is even due to this
    person on their own local date (plan 0.4) — then linked, opted in and reachable.

    The cadence gate is the one that was missing. Everyone linked to Discord got a
    post every day, whatever they chose in onboarding. A weekly-cadence reader is
    dropped here on a Tuesday and their briefing is still written; they simply are
    not interrupted about it until Monday.
    """
    from apps.content.tasks import select_users

    users = select_users(usernames)
    due = [
        user
        for user in users
        if delivery.DAILY
        in delivery.push_kinds(
            delivery.user_cadence(user), on or delivery.local_today(user)
        )
    ]
    reachable = resolve.report_recipient_user_ids(due)
    return [u for u in due if u.id in reachable]


def run_daily_report_send(
    usernames: list[str] | None = None,
    *,
    on: date | None = None,
    compile_fn: CompileFn = compile_report_for_user,
    urgent_fn: UrgentFn = send_urgent_alerts,
    render_fn: RenderFn = render_report_pdf,
    send_fn: SendFn = _default_send,
    report_dir: str | None = None,
    log: Callable[[str], None] = logger.info,
) -> SendSummary:
    """Compile → render → queue, for every eligible user. Never raises."""
    summary = SendSummary()
    recipients = eligible_recipients(usernames, on=on)
    summary.eligible = len(recipients)
    log(f"daily report: {summary.eligible} eligible recipient(s)")
    if not recipients:
        return summary

    workdir = Path(report_dir) if report_dir else _report_dir()
    workdir.mkdir(parents=True, exist_ok=True)
    # Phase 1 — compile every recipient's day.
    compiled: list[tuple[object, ReportData]] = []
    for user in recipients:
        try:
            data = compile_fn(user)
            if data.stats.is_quiet:
                # Nothing entered a top list and nothing raised an alert, so
                # there is nothing to interrupt anyone about (plan H7). Their web
                # report still shows the day as quiet, which is the honest place
                # for "no news" to live.
                summary.quiet += 1
                continue
            compiled.append((user, data))
            summary.compiled += 1
        except Exception as exc:  # noqa: BLE001 — one user never sinks the batch
            summary.errors += 1
            summary.error_detail.append(f"{user.get_username()}: compile — {exc}")
            logger.warning("report compile failed for %s", user, exc_info=True)

    # Phase 2 — render every report to a PDF on disk.
    rendered: list[tuple[object, ReportData, Path, str]] = []
    for user, data in compiled:
        try:
            pdf = render_fn(data)
            filename = f"mylo-report-{user.get_username()}-{data.generated_on}.pdf"
            path = workdir / filename
            path.write_bytes(pdf)
            rendered.append((user, data, path, filename))
            summary.rendered += 1
        except Exception as exc:  # noqa: BLE001
            summary.errors += 1
            summary.error_detail.append(f"{user.get_username()}: render — {exc}")
            logger.warning("daily report render failed for %s", user, exc_info=True)

    # Phase 3 — queue every PDF. The file stays put until the row settles.
    for user, data, path, filename in rendered:
        try:
            outcome = send_fn(user, data, path, filename)
        except Exception as exc:  # noqa: BLE001
            summary.errors += 1
            summary.error_detail.append(f"{user.get_username()}: send — {exc}")
            logger.warning("daily report send failed for %s", user, exc_info=True)
            continue
        if getattr(outcome, "ok", False):
            summary.sent += 1
        else:
            # Not reachable, so nothing was queued — drop the file now rather
            # than leave it for a sweep that only knows about outbox rows.
            #
            # Unless the caller named the directory itself: an explicit
            # ``report_dir`` (``--save-dir``) means "keep these, I want to look
            # at them", and every unreachable recipient is precisely the case
            # worth looking at. Deleting them here made ``--save-dir`` delete
            # exactly the files it promises to keep, which is how it behaved
            # with ``--dry-run`` — whose stub sender is never "ok" by design.
            if not report_dir:
                path.unlink(missing_ok=True)
            summary.unreachable += 1

    # The one exception to "weekly cadence means Mondays" (open decision OD2).
    # Run from the daily stage rather than its own because it is the same
    # question asked of the same people on the same schedule — and because a
    # separate stage is a separate thing to forget to wire into the chain.
    urgent = urgent_fn(usernames, on=on)
    summary.urgent = urgent.sent
    summary.errors += urgent.errors
    summary.error_detail.extend(urgent.error_detail)

    log(
        f"daily report: {summary.sent} queued, {summary.quiet} quiet, "
        f"{summary.urgent} urgent, {summary.unreachable} unreachable, "
        f"{summary.errors} error(s)"
    )
    return summary
