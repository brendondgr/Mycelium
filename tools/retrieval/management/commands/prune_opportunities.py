"""Delete expired grants/conferences/fellowships (the daily prune, decoupled).

In the daily chain this runs **after** the reminder tick (R2), so a moved deadline
is always seen live before its item can be deleted. Deleting an item fires the
prune → reminder-stale signal (``tools.delivery.signals``) as a backstop:

    uv run --project web/backend python web/backend/manage.py prune_opportunities

Uses :func:`tools.retrieval.collect.ingest.prune_expired` — the one ``prune_expired``
the whole opportunity surface converges on (plan Phase 4/6): it is type-scoped
(``type__in=[GRANT, CONFERENCE, FELLOWSHIP]``), not source-scoped, so it covers
every source id, including the ones the open collector introduces, without
needing to know their names.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from tools.retrieval.collect.ingest import prune_expired


class Command(BaseCommand):
    help = "Delete expired opportunities whose actionable date has passed."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--today",
            default=None,
            metavar="YYYY-MM-DD",
            help="Reference date for expiry. Default: today.",
        )
        parser.add_argument(
            "--stale-only",
            action="store_true",
            help=(
                "Only remove dateless conferences the collector has stopped "
                "re-seeing (skip the ordinary past-deadline sweep). This is the "
                "one-off purge of listings that accumulated while nothing could "
                "expire them."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be removed without deleting anything.",
        )

    def handle(self, *args, **options) -> None:
        pruned = prune_expired(
            today=options.get("today"),
            log=self.stdout.write,
            stale_only=options.get("stale_only", False),
            dry_run=options.get("dry_run", False),
        )
        verb = "Would prune" if options.get("dry_run") else "Pruned"
        self.stdout.write(self.style.SUCCESS(f"{verb} {pruned} item(s)."))
