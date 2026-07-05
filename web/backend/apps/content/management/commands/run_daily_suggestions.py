"""Run the daily research-suggestion pipeline from the CLI.

    # everyone (sync)
    python manage.py run_daily_suggestions

    # just Brendon, force the offline fallback, smaller scan
    python manage.py run_daily_suggestions --user brendondgr --no-llm --query-limit 4

    # hand off to the worker
    python manage.py run_daily_suggestions --async

The same code path the Beat schedule uses, exposed for testing and manual runs.
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.content.pipeline import DEFAULT_SUGGESTIONS, run_daily_batch
from apps.content.runlog import new_run_log
from apps.content.tasks import run_daily_suggestions, select_users


class Command(BaseCommand):
    help = "Scan, RAG-retrieve, and suggest research papers per user."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--user",
            "-u",
            action="append",
            dest="usernames",
            metavar="USERNAME",
            help="Limit to this user. Repeat for several. Default: all active users.",
        )
        parser.add_argument(
            "--days-back",
            type=int,
            default=2,
            help="How many days back to scan publication dates (default 2).",
        )
        parser.add_argument(
            "--days-forward",
            type=int,
            default=7,
            help="How many days forward (ahead-of-print) to scan (default 7).",
        )
        parser.add_argument(
            "--source",
            action="append",
            dest="sources",
            metavar="NAME",
            help="Limit to this source (openalex/pubmed/semanticscholar). Repeatable.",
        )
        parser.add_argument("--query-limit", type=int, default=6)
        parser.add_argument("--top-k", type=int, default=20)
        parser.add_argument("--suggestions", type=int, default=DEFAULT_SUGGESTIONS)
        parser.add_argument(
            "--no-llm",
            action="store_true",
            help="Skip the language model; use the deterministic fallback only.",
        )
        parser.add_argument(
            "--no-embed",
            action="store_true",
            help="Skip embedding scanned papers (retrieval will find nothing new).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run the pipeline but do not write RelevanceScore rows.",
        )
        parser.add_argument(
            "--async",
            action="store_true",
            dest="is_async",
            help="Dispatch to Celery instead of running inline.",
        )

    def handle(self, *args, **options) -> None:
        usernames = [u for u in (options.get("usernames") or []) if u and u.strip()]
        common = dict(
            days_back=options["days_back"],
            days_forward=options["days_forward"],
            sources=options.get("sources"),
            query_limit=options["query_limit"],
            top_k=options["top_k"],
            suggestion_limit=options["suggestions"],
            embed=not options["no_embed"],
        )

        if options["is_async"]:
            task = run_daily_suggestions.delay(usernames or None, **common)
            self.stdout.write(self.style.SUCCESS(f"Dispatched task {task.id}."))
            return

        users = select_users(usernames or None)
        if not users:
            self.stdout.write(self.style.WARNING("No matching users."))
            return

        complete = (lambda _prompt: None) if options["no_llm"] else None
        persist = not options["dry_run"]
        # Verbose, timestamped log to a file AND echoed live to the console.
        runlog = new_run_log(
            settings.DAILY_SUGGESTIONS_LOG_DIR,
            label="cli",
            echo=lambda text: self.stdout.write(text),
        )
        self.stdout.write(self.style.SUCCESS(f"Run log: {runlog.path}"))
        try:
            # One global ingest (search + embed shared topics once), then a
            # per-user recommend pass over the shared store.
            batch = run_daily_batch(
                users,
                complete=complete,
                persist=persist,
                log=runlog.line,
                **common,
            )
        finally:
            runlog.close()

        ingest = batch.ingest
        self.stdout.write(
            self.style.SUCCESS(
                "Ingest: "
                f"{ingest.get('unique_queries', 0)} unique term(s), "
                f"{ingest.get('new', 0)} new / {ingest.get('embedded', 0)} embedded."
            )
        )
        for result in batch.results:
            self._report(result)

    def _report(self, result) -> None:
        line = (
            f"{result.username}: {result.status} — "
            f"{result.scanned_new} new, {result.embedded} embedded, "
            f"{result.retrieved} retrieved, {result.suggestions} suggestions "
            f"({result.llm} llm / {result.fallback} fallback)"
        )
        if result.note:
            line += f" [{result.note}]"
        style = self.style.SUCCESS if result.status == "ok" else self.style.WARNING
        self.stdout.write(style(line))
