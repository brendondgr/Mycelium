"""Ingest Pivot-RP grants/conferences into the content store (import or scrape).

    # Import the tool's already-scraped output (unattended-safe, no browser):
    uv run --project web/backend python web/backend/manage.py ingest_pivot \
        --source json --area grants --path /path/to/pivot_funding_results.json

    # Read the tool's shared SQLite store (both areas):
    uv run --project web/backend python web/backend/manage.py ingest_pivot \
        --source db --path /path/to/pivot.db

    # Best-effort live refresh (only if a valid saved Pivot session exists):
    uv run --project web/backend python web/backend/manage.py ingest_pivot \
        --source scrape --topic "agentic ai" --topic "knowledge graphs"

Upserts into ``content.ContentItem`` (type grant/conference), preserving each
item's immutable ``first_seen``, embedding new/changed items, and — unless
``--no-prune`` — deleting grants past their deadline and conferences past their
event date. ``--no-embed`` stores rows with ``embedding=NULL``.
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from apps.scraper.pivot.importer import iter_pivot
from apps.scraper.pivot.ingest import ingest_pivot


class Command(BaseCommand):
    help = "Import or scrape Pivot grants/conferences into the content store."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            choices=["json", "db", "scrape"],
            default="json",
            help="json/db read the tool's output; scrape drives the browser.",
        )
        parser.add_argument(
            "--path",
            action="append",
            dest="paths",
            metavar="FILE",
            help="Source file(s) for --source json/db (repeatable).",
        )
        parser.add_argument(
            "--area",
            choices=["grants", "conferences"],
            help="Area for --source json when it can't be inferred from the file.",
        )
        parser.add_argument(
            "--topic",
            action="append",
            dest="topics",
            metavar="TEXT",
            help="Search topic for --source scrape (repeatable).",
        )
        parser.add_argument(
            "--no-embed",
            action="store_true",
            help="Skip embedding; upsert rows with embedding=NULL.",
        )
        parser.add_argument(
            "--no-prune",
            action="store_true",
            help="Keep expired grants/conferences instead of deleting them.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Build items and report, but do not write to the database.",
        )

    def handle(self, *args, **options):
        source = options["source"]
        embed = not options["no_embed"]
        prune = not options["no_prune"]

        if source in ("json", "db"):
            paths = options.get("paths")
            if not paths:
                raise CommandError(f"--source {source} needs at least one --path.")
            area = options.get("area")
            pairs = list(iter_pivot(paths, area if source == "json" else None))
        else:  # scrape (best-effort; no-op without a saved session / Playwright)
            from apps.scraper.pivot.scrape import refresh

            topics = [t for t in (options.get("topics") or []) if t and t.strip()]
            pairs = list(refresh(topics=topics, log=self.stdout.write))

        self.stdout.write(f"collected {len(pairs)} record(s) from {source}")
        if not pairs:
            self.stdout.write(self.style.WARNING("nothing to ingest"))
            return

        if options["dry_run"]:
            from collections import Counter

            counts = Counter(area for area, _ in pairs)
            self.stdout.write(json.dumps(dict(counts), indent=2))
            self.stdout.write(self.style.SUCCESS("dry run — nothing written"))
            return

        summary = ingest_pivot(
            pairs, embed=embed, prune=prune, log=self.stdout.write
        )
        self.stdout.write(json.dumps(summary.as_dict(), indent=2))
        self.stdout.write(
            self.style.SUCCESS(
                f"{summary.created} new, {summary.updated} updated, "
                f"{summary.embedded} embedded, {summary.pruned} pruned"
            )
        )
