"""Rebuild the ``ContentDeadline`` projection for every opportunity (backfill).

The projection is normally rebuilt inline on each opportunity upsert; this command
backfills existing items (e.g. right after the R0 migration lands) or repairs the
projection after a manual edit. It runs with change-detection **off** so a bulk
rebuild over historical data never manufactures a wave of phantom "moved" signals:

    uv run --project web/backend python web/backend/manage.py rebuild_content_deadlines
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.utils import timezone

from tools.retrieval.deadlines_projection import rebuild_all


class Command(BaseCommand):
    help = "Rebuild the ContentDeadline projection for all opportunities."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--today",
            default=None,
            metavar="YYYY-MM-DD",
            help="Reference date for deadline selection. Default: today.",
        )

    def handle(self, *args, **options) -> None:
        today = options.get("today") or timezone.now().date().isoformat()
        count = rebuild_all(today, detect_changes=False)
        self.stdout.write(
            self.style.SUCCESS(f"Rebuilt deadline projection for {count} item(s).")
        )
