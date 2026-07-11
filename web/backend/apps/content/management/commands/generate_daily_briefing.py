"""Generate each user's daily "Mylo Report" briefing.

Runs as the last stage of the daily run (``manual_all.py``), after papers and
opportunities have been matched, so it can synthesize across all categories. Also
runnable by hand for all users, or one at a time with ``--user`` (repeatable):

    uv run --project web/backend python web/backend/manage.py generate_daily_briefing
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.content.briefing import generate_briefing_for_user
from apps.content.tasks import select_users


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
        if not users:
            self.stdout.write(self.style.WARNING("No matching users."))
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

        self.stdout.write(
            self.style.SUCCESS(
                f"Briefings written for {len(users)} user(s): "
                f"{llm} via LLM, {fallback} via fallback, {errors} error(s)."
            )
        )
