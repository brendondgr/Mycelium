"""Match grants, conferences, and fellowships to every target (the 1am job).

An untargeted run covers every entitled user, every lab on an active subscription,
and their in-cap active projects — the same target set as the Celery task.

    uv run --project web/backend python web/backend/manage.py run_daily_opportunities
    uv run --project web/backend python web/backend/manage.py run_daily_opportunities \
        --user brendondgr --no-llm --no-prune

Runs inline by default (best for a smoke test); ``--async`` dispatches the Celery
task. This command never scrapes — collection is its own scheduled stage
(``apps.scraper.collect``, run by ``manual_all.py`` before this command, plan
Phase 12); matching always runs over whatever that stage last wrote.
``--no-prune`` keeps expired grants/conferences instead of deleting them,
via :func:`apps.content.opportunities.run_daily_opportunities_batch`.
``--no-llm`` uses the deterministic fallback scoring for grants/conferences
(fellowships always use the rule engine); ``--dry-run`` computes but
persists nothing.

There used to be a matching ``--no-ingest`` flag here, plumbed through to an
``ingest`` parameter on ``run_daily_opportunities_batch`` that never actually
gated anything once the open collector moved ingestion into its own Phase 12
stage — a no-op flag documented as toggling the prune step, which it did not.
Removed rather than left lying, since a flag whose help text describes
behaviour the code does not have is worse than no flag.
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from apps.content.opportunities import run_daily_opportunities_batch
from apps.content.tasks import select_departments, select_targets, select_users


class Command(BaseCommand):
    help = "Match grants/conferences/fellowships to users (retrieve, score, pin)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--user",
            "-u",
            action="append",
            dest="usernames",
            help="Limit to this user. Repeat for several. Default: all active users.",
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
                prune=not options["no_prune"],
            )
            self.stdout.write(self.style.SUCCESS(f"Dispatched task {result.id}"))
            return

        users = select_users(usernames)
        # A full run also matches each entitled lab and in-cap project, matching the
        # Celery task and the briefing/digest stages; a --user run stays user-scoped.
        labs, projects = select_targets(usernames)
        departments = select_departments(usernames)
        self.stdout.write(
            f"Matching opportunities for {len(users)} user(s), {len(labs)} lab(s), "
            f"{len(projects)} project(s), {len(departments)} department(s)…"
        )

        # ``--no-llm`` forces the deterministic fallback by injecting a complete
        # seam that always returns nothing usable (mirrors run_daily_suggestions).
        complete = (lambda _prompt: None) if options["no_llm"] else None

        batch = run_daily_opportunities_batch(
            users,
            labs=labs,
            projects=projects,
            departments=departments,
            areas=("grants", "conferences", "fellowships"),
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
