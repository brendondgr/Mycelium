"""Re-render one person's daily report and DM it to them again.

The person-shaped half of the manual re-delivery pair; ``repost_lab_report`` is the
lab-shaped one. Both regenerate the written briefing over the target's current
Top-25 before rendering, so what arrives reflects the data as it stands now, not as
it stood at 3am.

Unlike ``send_daily_discord_reports --user``, this actually sends: that command
shares the daily chain's per-day dedupe key, so a same-day re-send re-found the
already-delivered row and quietly queued nothing.

    uv run --project web/backend python web/backend/manage.py \\
        resend_user_report --user brendondgr
    ... --user a --user b        # several people
    ... --no-regenerate          # re-send the briefing exactly as written
    ... --dry-run                # regenerate + render, queue nothing
    ... --save-dir /tmp/reports  # write the PDF here instead of the outbox dir
"""

from __future__ import annotations

import json

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from apps.content.report_resend import resend_user_report


class Command(BaseCommand):
    help = "Re-render one or more users' daily reports and DM them again."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--user",
            "-u",
            action="append",
            dest="usernames",
            metavar="USERNAME",
            required=True,
            help="The user to re-send to. Repeat for several.",
        )
        parser.add_argument(
            "--no-regenerate",
            action="store_true",
            help="Keep the stored briefing instead of rewriting it first.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Regenerate and render, but queue nothing.",
        )
        parser.add_argument(
            "--save-dir",
            dest="save_dir",
            metavar="PATH",
            help="Write the PDF here instead of the outbox attachment directory.",
        )

    def handle(self, *args, **options) -> None:
        usernames = [u.strip() for u in options["usernames"] if u and u.strip()]
        users = list(User.objects.filter(username__in=usernames))
        found = {u.get_username() for u in users}
        missing = [name for name in usernames if name not in found]
        if missing:
            # Loudly, not as a zero-recipient no-op: a typo in a username is the
            # single likeliest reason an operator sees nothing happen.
            raise CommandError(f"no such user(s): {', '.join(missing)}")

        outcomes = []
        for user in users:
            outcome = resend_user_report(
                user,
                regenerate=not options["no_regenerate"],
                dry_run=options["dry_run"],
                report_dir=options.get("save_dir"),
            )
            outcomes.append(outcome)
            style = self.style.SUCCESS if outcome.ok else self.style.WARNING
            self.stdout.write(style(outcome.summary()))

        self.stdout.write(json.dumps([o.as_dict() for o in outcomes], indent=2))
        queued = sum(1 for o in outcomes if o.ok)
        self.stdout.write(
            self.style.SUCCESS(
                f"{queued}/{len(outcomes)} queued; the outbox drain delivers."
            )
            if queued
            else self.style.WARNING("Nothing was queued — see the reasons above.")
        )
