"""Run the plan's §8 smoke checklist against the live database.

Twelve system checks, not unit tests: each asks a question about the thing that
is actually deployed — this cadence matrix, these outbox rows, this lab's
projects — which is the class of failure a test suite cannot see, because every
test builds its own world.

    manage.py smoke_reports [--today YYYY-MM-DD] [--send]

``--send`` enables S11, which re-runs the real send stage to prove it queues
nothing new. It is off by default because it is the one check with a side effect,
and "prove the idempotency" is not a reason to surprise anyone.

Exits non-zero on any failure, so it can gate a release.
"""

from __future__ import annotations

from datetime import date

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Run the reports smoke checklist (plan §8) against the live data."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--today",
            help="Run the day-scoped checks against this date (YYYY-MM-DD).",
        )
        parser.add_argument(
            "--send",
            action="store_true",
            help="Include S11, which re-runs the real send stage.",
        )

    def handle(self, *args, **options) -> None:
        from apps.content.smoke_reports import FAIL, SKIP, run_checklist

        raw = options.get("today")
        try:
            today = date.fromisoformat(raw) if raw else None
        except ValueError as exc:
            raise CommandError(f"--today must be YYYY-MM-DD, got {raw!r}") from exc

        checks = run_checklist(today=today, send=bool(options.get("send")))
        for check in checks:
            style = {
                FAIL: self.style.ERROR,
                SKIP: self.style.WARNING,
            }.get(check.status, self.style.SUCCESS)
            self.stdout.write(style(check.line()))

        failed = [check for check in checks if check.status == FAIL]
        skipped = [check for check in checks if check.status == SKIP]
        self.stdout.write("")
        summary = (
            f"{len(checks) - len(failed) - len(skipped)} passed, "
            f"{len(failed)} failed, {len(skipped)} skipped"
        )
        if failed:
            raise CommandError(summary)
        self.stdout.write(self.style.SUCCESS(summary))
