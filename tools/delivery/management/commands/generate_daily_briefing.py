"""Generate each user's daily "Mylo Report" briefing.

Runs as the last stage of the daily run (``manual_all.py``), after papers and
opportunities have been matched, so it can synthesize across all categories. Also
runnable by hand for all users, or one at a time with ``--user`` (repeatable):

    uv run --project web/backend python web/backend/manage.py generate_daily_briefing
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from tools.delivery.briefing import (
    generate_briefing_for_lab,
    generate_briefing_for_user,
)
from tools.recommendation.tasks import (
    select_departments,
    select_targets,
    select_users,
)


class Command(BaseCommand):
    help = "Write the cross-category daily briefing for all users (or named ones)."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--user",
            "-u",
            action="append",
            dest="usernames",
            metavar="USERNAME",
            help="Limit to this user. Repeat for several. Default: all active users.",
        )

    def handle(self, *args, **options) -> None:
        usernames = [u for u in (options.get("usernames") or []) if u and u.strip()]
        users = select_users(usernames or None)
        # A full run also briefs each entitled lab over its aggregate matches (a
        # targeted --user run stays user-scoped; select_targets returns no labs).
        labs, _ = select_targets(usernames or None)
        # A department is briefed over its own matches through the lab's function.
        departments = select_departments(usernames or None)
        if not users and not labs and not departments:
            self.stdout.write(
                self.style.WARNING("No matching users, labs or departments.")
            )
            return

        llm = 0
        fallback = 0
        errors = 0
        for user in users:
            try:
                briefing = generate_briefing_for_user(user)
            except Exception as exc:  # noqa: BLE001 — one user must not abort the batch
                errors += 1
                self.stderr.write(
                    self.style.ERROR(f"  {user.username}: briefing failed — {exc}")
                )
                continue
            if briefing.origin == briefing.Origin.LLM:
                llm += 1
            else:
                fallback += 1

        lab_llm = 0
        lab_fallback = 0
        for lab in labs:
            try:
                briefing = generate_briefing_for_lab(lab)
            except Exception as exc:  # noqa: BLE001 — one lab must not abort the batch
                errors += 1
                self.stderr.write(
                    self.style.ERROR(f"  {lab.slug}: lab briefing failed — {exc}")
                )
                continue
            if briefing.origin == briefing.Origin.LLM:
                lab_llm += 1
            else:
                lab_fallback += 1

        dept_written = 0
        for department in departments:
            try:
                generate_briefing_for_lab(department)
            except Exception as exc:  # noqa: BLE001 — one department never sinks it
                errors += 1
                self.stderr.write(
                    self.style.ERROR(
                        f"  {department.pk}: department briefing failed — {exc}"
                    )
                )
                continue
            dept_written += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Briefings written for {len(users)} user(s): "
                f"{llm} via LLM, {fallback} via fallback; "
                f"{len(labs)} lab(s): {lab_llm} via LLM, {lab_fallback} via fallback; "
                f"{dept_written} department(s); {errors} error(s)."
            )
        )
