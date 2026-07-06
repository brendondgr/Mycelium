"""Match Pivot grants & conferences to every user (the 1am job, on demand).

    uv run --project web/backend python web/backend/manage.py run_daily_opportunities
    uv run --project web/backend python web/backend/manage.py run_daily_opportunities \
        --user brendondgr --no-llm --no-ingest

Runs inline by default (best for a smoke test); ``--async`` dispatches the Celery
task. ``--no-ingest`` skips the best-effort scrape (match the existing corpus);
``--no-prune`` keeps expired items; ``--no-llm`` uses the deterministic fallback
scoring; ``--dry-run`` computes but persists nothing.
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from apps.content.opportunities import run_daily_opportunities_batch
from apps.content.tasks import select_users


class Command(BaseCommand):
    help = "Match Pivot grants/conferences to users (retrieve, score, pin, persist)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--user",
            "-u",
            action="append",
            dest="usernames",
            help="Limit to this user. Repeat for several. Default: all active users.",
        )
        parser.add_argument(
            "--no-ingest",
            action="store_true",
            help="Skip the best-effort Pivot refresh; match the existing corpus.",
        )
        parser.add_argument(
            "--no-prune",
            action="store_true",
            help="Keep expired grants/conferences instead of deleting them.",
        )
        parser.add_argument(
            "--no-llm",
            action="store_true",
            help="Use deterministic fallback scoring instead of the language model.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run the pipeline but persist no RelevanceScore rows.",
        )
        parser.add_argument(
            "--async",
            action="store_true",
            dest="run_async",
            help="Dispatch the Celery task instead of running inline.",
        )

    def handle(self, *args, **options):
        usernames = options.get("usernames")

        if options["run_async"]:
            from apps.content.tasks import run_daily_opportunities

            result = run_daily_opportunities.delay(
                usernames,
                ingest=not options["no_ingest"],
                prune=not options["no_prune"],
            )
            self.stdout.write(self.style.SUCCESS(f"Dispatched task {result.id}"))
            return

        users = select_users(usernames)
        self.stdout.write(f"Matching opportunities for {len(users)} user(s)…")

        # ``--no-llm`` forces the deterministic fallback by injecting a complete
        # seam that always returns nothing usable (mirrors run_daily_suggestions).
        complete = (lambda _prompt: None) if options["no_llm"] else None

        batch = run_daily_opportunities_batch(
            users,
            ingest=not options["no_ingest"],
            prune=not options["no_prune"],
            persist=not options["dry_run"],
            complete=complete,
            log=self.stdout.write,
        )
        self.stdout.write(json.dumps(batch.as_dict(), indent=2))
        ok = sum(1 for r in batch.results if r.status == "ok")
        new = sum(r.new for r in batch.results)
        self.stdout.write(
            self.style.SUCCESS(f"{ok}/{len(batch.results)} runs ok, {new} new items")
        )
