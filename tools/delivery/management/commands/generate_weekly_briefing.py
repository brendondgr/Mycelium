"""Write each target's Monday weekly.

A stage of the daily run, and **only on a Monday** unless forced: the weekly is a
Monday-morning artefact in the reader's week, keyed on that Monday so a re-run
after an outage re-finds the row rather than writing a second copy of the week.

Runs after ``generate_daily_briefing``, which is deliberate. Monday still gets a
daily written for the web — cadence governs push, not computation — and the
weekly is a second row beside it, not a replacement for it.

Never raises: one bad target must not cost everyone else their week.

    manage.py generate_weekly_briefing [--user U] [--lab L] [--force]
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = (
        "Write the Monday weekly for every scheduled-eligible user, lab and "
        "department."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("--user", "-u", action="append", dest="usernames")
        parser.add_argument("--lab", action="append", dest="slugs")
        parser.add_argument(
            "--force",
            action="store_true",
            help="Write it whatever day it is. For review and for a re-run.",
        )

    def handle(self, *args, **options) -> None:
        from apps.accounts.models import Lab

        from tools.delivery.weekly import (
            generate_weekly_for_lab,
            generate_weekly_for_user,
        )
        from tools.recommendation.tasks import (
            select_departments,
            select_targets,
            select_users,
        )

        today = timezone.localdate()
        if today.weekday() != 0 and not options.get("force"):
            self.stdout.write(
                self.style.NOTICE(
                    f"Not a Monday ({today:%A}); nothing written. Use --force to "
                    "write one anyway."
                )
            )
            return

        usernames = [u for u in (options.get("usernames") or []) if u and u.strip()]
        slugs = [s for s in (options.get("slugs") or []) if s and s.strip()]
        users = select_users(usernames or None)
        if slugs:
            labs = list(Lab.objects.filter(slug__in=slugs))
            departments = []
        else:
            labs, _projects = select_targets(usernames or None)
            # A department's weekly is the lab's, through the same function.
            departments = select_departments(usernames or None)

        summary = {
            "users": 0,
            "labs": 0,
            "departments": 0,
            "llm": 0,
            "fallback": 0,
            "errors": 0,
        }
        for target, generate, label, key in [
            *[(u, generate_weekly_for_user, u.get_username(), "users") for u in users],
            *[(lab, generate_weekly_for_lab, lab.slug, "labs") for lab in labs],
            *[
                (d, generate_weekly_for_lab, str(d.pk), "departments")
                for d in departments
            ],
        ]:
            try:
                briefing = generate(target, today=today)
            except Exception as exc:  # noqa: BLE001 — one target never sinks the run
                summary["errors"] += 1
                self.stderr.write(self.style.WARNING(f"{label}: {exc}"))
                continue
            summary[key] += 1
            summary["llm" if briefing.origin == "llm" else "fallback"] += 1

        self.stdout.write(json.dumps(summary, indent=2))
        self.stdout.write(
            self.style.SUCCESS(
                f"Weeklies written for {summary['users']} user(s), "
                f"{summary['labs']} lab(s) and {summary['departments']} "
                f"department(s); {summary['errors']} error(s)."
            )
        )
