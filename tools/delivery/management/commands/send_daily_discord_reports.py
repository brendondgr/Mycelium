"""Send each eligible user their daily "Mylo Report" as a PDF Discord DM.

The final stage of the daily run (``manual_all.py``), after the briefing is written,
so the PDF embeds the freshest report. Eligibility = entitled + active
(``SCHEDULED_REPORTS``) ∩ linked + opted-in + reachable Discord identity. The flow
is phased: compile all → render all PDFs → send all → delete all (see
:mod:`tools.delivery.daily_report_send`).

    uv run --project web/backend python web/backend/manage.py send_daily_discord_reports
    ... --user brendondgr            # limit to one user (repeatable)
    ... --dry-run                    # compile + render, but do not send
    ... --save-dir /tmp/mylo-reports # keep the PDFs here (implies no cleanup)
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from tools.delivery.daily_report_send import REPORT_TITLE, run_daily_report_send


class Command(BaseCommand):
    help = "DM each eligible user their daily research report as a PDF."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--user",
            "-u",
            action="append",
            dest="usernames",
            metavar="USERNAME",
            help="Limit to this user. Repeat for several. Default: all eligible.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Compile and render PDFs but do not send any DM.",
        )
        parser.add_argument(
            "--save-dir",
            dest="save_dir",
            metavar="PATH",
            help="Write the PDFs here and keep them (no cleanup). For inspection.",
        )

    def handle(self, *args, **options) -> None:
        usernames = [u for u in (options.get("usernames") or []) if u and u.strip()]
        dry_run = bool(options.get("dry_run"))
        save_dir = options.get("save_dir")

        send_fn = None
        if dry_run:
            # The third argument is the rendered PDF's *path*, not its bytes --
            # `daily_report_send` writes the file to a workdir first and hands
            # the sender a path so the file survives until the outbox row
            # settles. This stub previously named it `pdf_bytes` and called
            # `len()` on it, which raised for every recipient: --dry-run, the
            # one flag whose whole job is checking a send before making it,
            # could not complete a single one.
            def send_fn(user, data, path, filename):  # noqa: ARG001
                size = path.stat().st_size if path.exists() else 0
                self.stdout.write(
                    f"  [dry-run] would DM {user.get_username()}: "
                    f'"{REPORT_TITLE}" + {filename} ({size:,} bytes)'
                )
                return type("_Skipped", (), {"ok": False})()

        kwargs = {"log": lambda msg: self.stdout.write(msg)}
        if usernames:
            kwargs["usernames"] = usernames
        if save_dir:
            kwargs["report_dir"] = save_dir
        if send_fn is not None:
            kwargs["send_fn"] = send_fn

        summary = run_daily_report_send(**kwargs)

        if summary.error_detail:
            for line in summary.error_detail:
                self.stderr.write(self.style.ERROR(f"  {line}"))

        style = self.style.WARNING if summary.errors else self.style.SUCCESS
        self.stdout.write(
            style(
                f"Daily report: {summary.eligible} eligible, "
                f"{summary.compiled} compiled, {summary.rendered} rendered, "
                f"{summary.sent} sent, {summary.unreachable} unreachable, "
                f"{summary.errors} error(s)."
            )
        )
