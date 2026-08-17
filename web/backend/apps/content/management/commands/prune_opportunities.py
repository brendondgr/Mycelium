"""Delete expired grants/conferences/fellowships (the daily prune, decoupled).

In the daily chain this runs **after** the reminder tick (R2), so a moved deadline
is always seen live before its item can be deleted. Deleting an item fires the
prune → reminder-stale signal (``apps.content.signals``) as a backstop:

    uv run --project web/backend python web/backend/manage.py prune_opportunities

Uses :func:`apps.scraper.collect.ingest.prune_expired` — the one ``prune_expired``
the whole opportunity surface converges on (plan Phase 4/6): it is type-scoped
(``type__in=[GRANT, CONFERENCE, FELLOWSHIP]``), not source-scoped, so it covers
every source id, including the ones the open collector introduces, without
needing to know their names.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.scraper.collect.ingest import prune_expired


class Command(BaseCommand):
    help = "Delete expired opportunities whose actionable date has passed."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--today",
            default=None,
            metavar="YYYY-MM-DD",
            help="Reference date for expiry. Default: today.",
        )

    def handle(self, *args, **options) -> None:
        pruned = prune_expired(today=options.get("today"), log=self.stdout.write)
        self.stdout.write(self.style.SUCCESS(f"Pruned {pruned} expired item(s)."))
