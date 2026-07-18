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

from apps.content.opportunities import DEFAULT_SURFACE
from apps.content.refitting import DEFAULT_AREAS, refit_batch, refit_targets_batch
from apps.content.tasks import select_targets, select_users


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
            "--llm-limit",
            dest="llm_limit",
            default=None,
            metavar="N|all",
            help=(
                "How many of each area's surfaced items to send to the model — a "
                "number or 'all'. Default: each pipeline's own top-10. Use 'all' "
                "to give every surfaced item genuine LLM feedback (higher GPU load)."
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
        parser.add_argument(
            "--no-labs",
            action="store_true",
            help=(
                "Skip labs and lab projects. By default a full run (no --user) also "
                "refits active-subscription labs + their projects, mirroring the "
                "nightly run — the replace pass that re-expands a stale lab feed."
            ),
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

    def _parse_llm_limit(self, raw: str | None) -> int | None:
        """``None`` → pipeline default; ``all`` → every surfaced item; else an int."""
        if raw is None:
            return None
        value = raw.strip().lower()
        if value == "all":
            # Cover the whole surfaced set. Both pipelines slice
            # ``surfaced[:llm_limit]``, so the surfaced count is the effective max.
            return DEFAULT_SURFACE
        try:
            limit = int(value)
        except ValueError as exc:
            raise CommandError(
                f"--llm-limit must be a number or 'all', not {raw!r}."
            ) from exc
        if limit < 0:
            raise CommandError("--llm-limit must be 0 or more (or 'all').")
        return limit

    def handle(self, *args, **options):
        max_users = self._parse_max(options["max_users"])
        llm_limit = self._parse_llm_limit(options["llm_limit"])

        users = select_users(options.get("usernames"))
        if max_users is not None:
            users = users[:max_users]

        # ``--no-llm`` forces the deterministic fallback by injecting a complete
        # seam that always returns nothing usable (mirrors run_daily_opportunities).
        complete = (lambda _prompt: None) if options["no_llm"] else None

        results: list = []
        if users:
            cap = "all" if max_users is None else str(max_users)
            self.stdout.write(
                f"Refitting {len(users)} user(s) (max={cap}) "
                f"over areas: {', '.join(options['areas'])}…"
            )
            results = refit_batch(
                users,
                areas=options["areas"],
                llm_limit=llm_limit,
                complete=complete,
                persist=not options["dry_run"],
                log=self.stdout.write,
            )
        else:
            self.stdout.write(self.style.WARNING("No matching users."))

        # A full run (no --user) also re-personalizes active labs + their projects,
        # the same target set the nightly run fans out to. ``select_targets``
        # self-scopes to nothing for a --user-scoped run, so --no-labs is only for
        # a full run that wants users only.
        labs, projects = (
            ([], [])
            if options["no_labs"]
            else select_targets(options["usernames"])
        )
        lab_results = refit_targets_batch(
            labs,
            projects,
            areas=options["areas"],
            llm_limit=llm_limit,
            complete=complete,
            persist=not options["dry_run"],
            log=self.stdout.write,
        )

        all_results = results + lab_results
        self.stdout.write(json.dumps([r.as_dict() for r in all_results], indent=2))
        user_ok = sum(1 for r in results if r.status == "ok")
        summary = f"{user_ok}/{len(results)} user refit(s) ok"
        if lab_results:
            lab_ok = sum(1 for r in lab_results if r.status == "ok")
            summary += (
                f"; {lab_ok}/{len(lab_results)} lab+project refit(s) ok "
                f"({len(labs)} lab(s), {len(projects)} project(s))"
            )
        self.stdout.write(self.style.SUCCESS(summary))
