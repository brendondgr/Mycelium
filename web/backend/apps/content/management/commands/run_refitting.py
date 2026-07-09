"""Refit users' personalized layer over the existing top results (LLM re-score).

    # everyone
    uv run --project web/backend python web/backend/manage.py run_refitting

    # just Brendon, at most one refit (safe smoke test — one round of LLM calls)
    uv run --project web/backend python web/backend/manage.py run_refitting \
        --user brendondgr --max 1

    # first N active users, deterministic fallback (no model), persist nothing
    uv run --project web/backend python web/backend/manage.py run_refitting \
        --max 5 --no-llm --dry-run

"Refitting" re-runs only the personalization half of the daily pipelines: it takes
the top results already stored for each area (research papers, grants, conferences,
fellowships) and re-scores them through the language model — with **no** literature
scan and **no** Pivot re-scrape. ``--max`` caps how many users are refit (a number
or ``all``) so a manual run can be bounded to avoid overwhelming the model host.
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from apps.content.refitting import DEFAULT_AREAS, refit_batch
from apps.content.tasks import select_users


class Command(BaseCommand):
    help = "Refit users' personalized layer over existing top results (LLM re-score)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--user",
            "-u",
            action="append",
            dest="usernames",
            metavar="USERNAME",
            help="Limit to this user. Repeat for several. Default: all active users.",
        )
        parser.add_argument(
            "--max",
            dest="max_users",
            default="all",
            metavar="N|all",
            help="Cap how many users to refit — a number or 'all' (default: all).",
        )
        parser.add_argument(
            "--areas",
            nargs="+",
            choices=DEFAULT_AREAS,
            default=list(DEFAULT_AREAS),
            metavar="AREA",
            help=(
                "Areas to refit (default: all): "
                f"{', '.join(DEFAULT_AREAS)}."
            ),
        )
        parser.add_argument(
            "--no-llm",
            action="store_true",
            help="Use deterministic fallback scoring instead of the language model.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run the refit but persist no RelevanceScore rows.",
        )

    def _parse_max(self, raw: str) -> int | None:
        """``all`` (or blank) → no cap; otherwise a positive integer."""
        value = (raw or "all").strip().lower()
        if value == "all":
            return None
        try:
            limit = int(value)
        except ValueError as exc:
            raise CommandError(
                f"--max must be a number or 'all', not {raw!r}."
            ) from exc
        if limit < 1:
            raise CommandError("--max must be at least 1 (or 'all').")
        return limit

    def handle(self, *args, **options):
        max_users = self._parse_max(options["max_users"])

        users = select_users(options.get("usernames"))
        if max_users is not None:
            users = users[:max_users]

        if not users:
            self.stdout.write(self.style.WARNING("No matching users."))
            return

        cap = "all" if max_users is None else str(max_users)
        self.stdout.write(
            f"Refitting {len(users)} user(s) (max={cap}) "
            f"over areas: {', '.join(options['areas'])}…"
        )

        # ``--no-llm`` forces the deterministic fallback by injecting a complete
        # seam that always returns nothing usable (mirrors run_daily_opportunities).
        complete = (lambda _prompt: None) if options["no_llm"] else None

        results = refit_batch(
            users,
            areas=options["areas"],
            complete=complete,
            persist=not options["dry_run"],
            log=self.stdout.write,
        )

        self.stdout.write(json.dumps([r.as_dict() for r in results], indent=2))
        ok = sum(1 for r in results if r.status == "ok")
        self.stdout.write(
            self.style.SUCCESS(f"{ok}/{len(results)} user refit(s) ok")
        )
