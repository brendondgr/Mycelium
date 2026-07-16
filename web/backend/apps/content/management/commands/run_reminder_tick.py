"""Run the daily reminder tick (compute-on-read fire of due reminders).

Ordered in the daily run **after** opportunity ingest + the ContentDeadline rebuild
and **before** prune (R2), so it always reads live deadlines. Idempotent within a day
— re-running fires nothing already sealed:

    uv run --project web/backend python web/backend/manage.py run_reminder_tick
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.content.reminders_announce import announce_deadline_changes
from apps.content.reminders_tick import run_tick


class Command(BaseCommand):
    help = "Fire due deadline reminders + announce moved deadlines (once per day)."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--today",
            default=None,
            metavar="YYYY-MM-DD",
            help="Reference date to fire against. Default: today.",
        )

    def handle(self, *args, **options) -> None:
        today = None
        raw = options.get("today")
        if raw:
            today = timezone.datetime.fromisoformat(raw).date()
        result = run_tick(today)
        moved = announce_deadline_changes(today)
        self.stdout.write(
            self.style.SUCCESS(
                "Reminder tick: "
                f"{result.fired} fired, {result.notifications} notifications, "
                f"{result.staled} stale, {result.fired_out} fired-out "
                f"(of {result.scanned} active); "
                f"{moved.announced} deadline-moved notices."
            )
        )
