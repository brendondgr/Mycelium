"""Print (or write) the announcement measures for a window (plan Phase 8).

Read-only. The output is meant to be recorded as an experiment before any
threshold changes:

    uv run --no-sync --project web/backend python web/backend/manage.py \
        announcement_metrics --since 2026-11-01 --json out.json
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.content import announce_metrics


class Command(BaseCommand):
    help = "Measure what opportunity announcements are doing."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--since", default=None, metavar="YYYY-MM-DD")
        parser.add_argument("--until", default=None, metavar="YYYY-MM-DD")
        parser.add_argument("--json", default="", metavar="PATH")

    def handle(self, *args, **options) -> None:
        today = timezone.localdate()
        since = (
            date.fromisoformat(options["since"])
            if options["since"]
            else today - timedelta(days=30)
        )
        until = date.fromisoformat(options["until"]) if options["until"] else today
        result = announce_metrics.compute(since, until)
        text = json.dumps(result, indent=2, sort_keys=True, default=str)
        if options["json"]:
            with open(options["json"], "w", encoding="utf-8") as fh:
                fh.write(text + "\n")
            self.stdout.write(f"Wrote {options['json']}")
        else:
            self.stdout.write(text)
