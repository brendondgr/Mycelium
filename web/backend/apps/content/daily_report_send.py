"""Orchestrate the daily "Mylo Report" Discord DM for all eligible users.

The delivery half of the daily PDF report. Eligibility is the intersection of three
gates already owned elsewhere:

* **entitled + active** — ``apps.content.tasks.select_users`` (holds
  ``SCHEDULED_REPORTS``; Free accounts are on-demand and never pushed a run),
* **linked + opted in + reachable** — ``resolve.report_recipient_user_ids`` (an
  ACTIVE Discord identity, ``daily_report_opt_out`` false, not a known-blocked DM).

The run is deliberately **phased** (the product brief's ordering), not interleaved:

1. compile every recipient's :class:`~apps.content.daily_report.ReportData`,
2. render every report to a PDF on disk (a throwaway temp dir),
3. send every PDF as a personal DM, then
4. delete the temp dir — the PDFs never linger.

The ``compile_fn`` / ``render_fn`` / ``send_fn`` seams are injected so tests can
drive the whole flow without a database of scores or a live Discord. A failure for
one user is caught and counted; it never sinks the batch.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from apps.content import reminders_discord
from apps.content.daily_report import ReportData, compile_report_for_user
from apps.content.daily_report_pdf import render_report_pdf
from apps.integrations.services import resolve

logger = logging.getLogger(__name__)

CompileFn = Callable[[object], ReportData]
RenderFn = Callable[[ReportData], bytes]
# send_fn(user, report_data, pdf_bytes, filename) -> outcome with a bool `.ok`.
SendFn = Callable[..., object]

REPORT_TITLE = "Your daily research report"


@dataclass
class SendSummary:
    eligible: int = 0
    compiled: int = 0
    rendered: int = 0
    sent: int = 0
    unreachable: int = 0
    errors: int = 0
    error_detail: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "eligible": self.eligible,
            "compiled": self.compiled,
            "rendered": self.rendered,
            "sent": self.sent,
            "unreachable": self.unreachable,
            "errors": self.errors,
        }


def _default_send(user, data: ReportData, pdf_bytes: bytes, filename: str):
    return reminders_discord.send_personal_report(
        user,
        title=REPORT_TITLE,
        body=data.summary_line() + "\nYour full report is attached as a PDF.",
        filename=filename,
        pdf_bytes=pdf_bytes,
    )


def eligible_recipients(usernames: list[str] | None):
    """The users who should receive the daily report DM, in a stable order."""
    from apps.content.tasks import select_users

    users = select_users(usernames)
    reachable = resolve.report_recipient_user_ids(users)
    return [u for u in users if u.id in reachable]


def run_daily_report_send(
    usernames: list[str] | None = None,
    *,
    compile_fn: CompileFn = compile_report_for_user,
    render_fn: RenderFn = render_report_pdf,
    send_fn: SendFn = _default_send,
    report_dir: str | None = None,
    log: Callable[[str], None] = logger.info,
) -> SendSummary:
    """Compile → render → send → cleanup for every eligible user. Never raises."""
    summary = SendSummary()
    recipients = eligible_recipients(usernames)
    summary.eligible = len(recipients)
    log(f"daily report: {summary.eligible} eligible recipient(s)")
    if not recipients:
        return summary

    workdir = (
        Path(report_dir)
        if report_dir
        else Path(tempfile.mkdtemp(prefix="mylo-report-"))
    )
    workdir.mkdir(parents=True, exist_ok=True)
    try:
        # Phase 1 — compile every recipient's day.
        compiled: list[tuple[object, ReportData]] = []
        for user in recipients:
            try:
                compiled.append((user, compile_fn(user)))
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

        # Phase 3 — send every PDF (read back from disk, per the brief's ordering).
        for user, data, path, filename in rendered:
            try:
                outcome = send_fn(user, data, path.read_bytes(), filename)
            except Exception as exc:  # noqa: BLE001
                summary.errors += 1
                summary.error_detail.append(f"{user.get_username()}: send — {exc}")
                logger.warning("daily report send failed for %s", user, exc_info=True)
                continue
            if getattr(outcome, "ok", False):
                summary.sent += 1
            else:
                summary.unreachable += 1
    finally:
        # Phase 4 — delete the generated PDFs no matter what happened above.
        if report_dir is None:
            shutil.rmtree(workdir, ignore_errors=True)

    log(
        f"daily report: {summary.sent} sent, {summary.unreachable} unreachable, "
        f"{summary.errors} error(s)"
    )
    return summary
