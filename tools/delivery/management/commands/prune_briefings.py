"""Delete written daily briefings older than the retention window.

The Reports page reads ``DailyBriefing`` history, so the table now grows one row
per target per day. This is the sweep that bounds it — a pure deletion of expired
rows, safe in the daily chain because it neither rewrites nor rescores anything
Mylo already wrote:

    uv run --project web/backend python web/backend/manage.py prune_briefings

The window is ``settings.BRIEFING_RETENTION_DAYS`` (flat for every plan). Only the
markdown is retained; the DM'd PDF is an outbox attachment with its own sweep.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from tools.delivery.models import DailyBriefing


class Command(BaseCommand):
    help = "Delete daily briefings older than BRIEFING_RETENTION_DAYS."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--today",
            default=None,
            metavar="YYYY-MM-DD",
            help="Reference date for the cutoff. Default: today.",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=None,
            help="Override the retention window (default: BRIEFING_RETENTION_DAYS).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be deleted without deleting it.",
        )

    def handle(self, *args, **options) -> None:
        today = self._reference_date(options.get("today"))
        days = options.get("days")
        if days is None:
            days = settings.BRIEFING_RETENTION_DAYS
        if days < 0:
            raise CommandError("Retention window must not be negative.")

        # Strictly older: the boundary day itself is still inside the window.
        cutoff = today - timedelta(days=days)
        expired = DailyBriefing.objects.filter(generated_on__lt=cutoff)

        if options.get("dry_run"):
            count = expired.count()
            self.stdout.write(
                f"Would delete {count} briefing(s) generated before {cutoff}."
            )
            return

        count, _ = expired.delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Pruned {count} briefing(s) generated before {cutoff}."
            )
        )

    def _reference_date(self, raw: str | None) -> date:
        if not raw:
            return timezone.localdate()
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError as exc:
            raise CommandError(f"--today must be YYYY-MM-DD, got {raw!r}.") from exc
