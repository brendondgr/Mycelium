"""Trigger a literature scan from the CLI.

    uv run --project web/backend python web/backend/manage.py scan_literature \
        --query "agentic ai in healthcare" --query "quantum cybersecurity"

Runs inline by default (handy for a smoke test); pass ``--async`` to dispatch
the Celery task instead. ``--no-embed`` skips embedding (scrape + dedup + upsert
only). ``--source`` may be repeated to restrict sources.
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from apps.scraper.ingest import scan
from apps.scraper.sources.registry import DEFAULT_SOURCES


class Command(BaseCommand):
    help = "Scan OpenAlex/PubMed/Semantic Scholar and ingest papers into the RAG store."

    def add_arguments(self, parser):
        parser.add_argument(
            "--query",
            "-q",
            action="append",
            dest="queries",
            metavar="TEXT",
            help="A search query. Repeat for several (each runs across every source).",
        )
        parser.add_argument(
            "--months-back",
            type=int,
            default=2,
            help="Months before today the publication window starts (default 2).",
        )
        parser.add_argument(
            "--months-forward",
            type=int,
            default=1,
            help="How many months after today the publication window ends (default 1).",
        )
        parser.add_argument(
            "--source",
            action="append",
            dest="sources",
            choices=list(DEFAULT_SOURCES),
            help="Restrict to a source (repeatable). Default: all sources.",
        )
        parser.add_argument(
            "--no-embed",
            action="store_true",
            help="Skip embedding; scrape, dedup, and upsert rows with embedding=NULL.",
        )
        parser.add_argument(
            "--async",
            action="store_true",
            dest="run_async",
            help="Dispatch the Celery task instead of running inline.",
        )

    def handle(self, *args, **options):
        queries = [q for q in (options.get("queries") or []) if q and q.strip()]
        if not queries:
            raise CommandError("Provide at least one --query.")

        embed = not options["no_embed"]
        sources = options.get("sources")

        if options["run_async"]:
            from apps.scraper.tasks import scan_literature

            result = scan_literature.delay(
                queries,
                months_back=options["months_back"],
                months_forward=options["months_forward"],
                sources=sources,
                embed=embed,
            )
            self.stdout.write(self.style.SUCCESS(f"Dispatched scan task {result.id}"))
            return

        self.stdout.write(
            f"Scanning {len(queries)} quer(y/ies) across {sources or 'all sources'}…"
        )
        summary = scan(
            queries,
            months_back=options["months_back"],
            months_forward=options["months_forward"],
            sources=sources,
            embed=embed,
        )
        self.stdout.write(json.dumps(summary.as_dict(), indent=2))
        msg = (
            f"{summary.new} new of {summary.unique} unique "
            f"({summary.embedded} embedded, {summary.upserted} upserted) "
            f"over {summary.window}"
        )
        if summary.embedding_skipped_reason:
            self.stdout.write(
                self.style.WARNING(
                    f"embedding skipped: {summary.embedding_skipped_reason}"
                )
            )
        self.stdout.write(self.style.SUCCESS(msg))
