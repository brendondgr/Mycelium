"""Give every open conference thread its continent tag (one-off, re-runnable).

Conference threads posted before continent tags existed carry none, so a forum
filtered by continent misses them. This patches each open thread's tags through
the outbox — no rename, no edit, no reply — and refreshes the location the
announcement stores. Re-running it queues nothing new for a thread already done.

    uv run --project web/backend python web/backend/manage.py \\
        retag_announcement_threads --dry-run
"""

from __future__ import annotations

from collections import Counter

from django.core.management.base import BaseCommand

from tools.delivery import announce, discord_announcements


class Command(BaseCommand):
    help = "Add continent tags to open conference announcement threads."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options) -> None:
        dry_run = options["dry_run"]
        if not dry_run and not announce.enabled():
            self.stdout.write(
                "Opportunity announcements are switched off; nothing to do."
            )
            return
        rows = discord_announcements.retag_conference_threads(dry_run=dry_run)
        verb = "Would retag" if dry_run else "Queued retags for"
        self.stdout.write(f"{verb} {len(rows)} thread(s).")
        for continent, n in Counter(r["continent"] for r in rows).most_common():
            self.stdout.write(f"  {continent}: {n}")
