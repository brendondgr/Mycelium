"""Queue the Monday weekly to Discord — DMs and lab channels.

The last stage of a Monday run, after ``generate_weekly_briefing`` has written
the reports. Both cadences receive a weekly on Monday, which is what makes this
the one message every reader gets: a weekly-cadence reader's only Discord message
of the week, and a daily-cadence reader's Monday in place of that day's daily.

Never raises. A failure here costs a week's post, not the week's data.

    manage.py send_weekly_reports [--user U] [--lab L] [--dry-run]
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Queue each eligible target's weekly report to Discord."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--user", "-u", action="append", dest="usernames")
        parser.add_argument("--lab", action="append", dest="slugs")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report who would receive one, and queue nothing.",
        )

    def handle(self, *args, **options) -> None:
        from tools.recommendation.tasks import select_targets

        from apps.accounts.models import Lab
        from apps.content.weekly_send import (
            eligible_weekly_recipients,
            send_lab_weeklies,
            send_weekly_discord_reports,
        )

        usernames = [u for u in (options.get("usernames") or []) if u and u.strip()]
        slugs = [s for s in (options.get("slugs") or []) if s and s.strip()]
        if slugs:
            labs = list(Lab.objects.filter(slug__in=slugs))
        else:
            labs, _projects = select_targets(usernames or None)

        if options["dry_run"]:
            recipients = eligible_weekly_recipients(usernames or None)
            self.stdout.write(
                json.dumps(
                    {
                        "would_dm": [u.get_username() for u in recipients],
                        "labs_considered": [lab.slug for lab in labs],
                        "today": timezone.localdate().isoformat(),
                    },
                    indent=2,
                )
            )
            return

        people = send_weekly_discord_reports(usernames or None)
        lab_posts = send_lab_weeklies(labs)

        for detail in (*people.error_detail, *lab_posts.error_detail):
            self.stderr.write(self.style.WARNING(f"  {detail}"))
        self.stdout.write(
            json.dumps({"dms": people.as_dict(), "labs": lab_posts.as_dict()}, indent=2)
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Weekly: {people.sent} DM(s) and {lab_posts.sent} lab post(s) "
                "queued; the outbox delivers."
            )
        )
