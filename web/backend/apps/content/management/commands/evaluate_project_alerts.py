"""Decide which of today's findings actually change what a project should do.

A stage of the daily run (``manual_all.py``), after scoring and before the
briefings — the briefing reads the day's alerts, so it has to run first, and it
reads the day's *slates*, so scoring has to run before it.

Never raises: one bad project must not cost everyone else their report, which is
the same rule every other stage of the chain follows.

    manage.py evaluate_project_alerts [--user <username>] [--lab <slug>]

(prefix with `uv run --project web/backend python web/backend/manage.py`.)
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Fire project alerts for every scheduled-eligible user and lab."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--user",
            "-u",
            action="append",
            dest="usernames",
            help="Limit to this user. Repeat for several.",
        )
        parser.add_argument(
            "--lab",
            action="append",
            dest="slugs",
            help="Limit to this lab slug. Repeat for several.",
        )

    def handle(self, *args, **options) -> None:
        from tools.recommendation.tasks import select_targets, select_users

        from apps.accounts.models import Lab
        from apps.content.alerts import evaluate_for_lab, evaluate_for_user

        usernames = [u for u in (options.get("usernames") or []) if u and u.strip()]
        slugs = [s for s in (options.get("slugs") or []) if s and s.strip()]
        today = timezone.localdate()

        users = select_users(usernames or None)
        if slugs:
            labs = list(Lab.objects.filter(slug__in=slugs))
        else:
            labs, _projects = select_targets(usernames or None)

        summary = {
            "users": len(users),
            "labs": len(labs),
            "considered": 0,
            "fired": 0,
            "held": 0,
            "duplicates": 0,
            "skipped_disabled": 0,
            "errors": 0,
        }

        for target, evaluate, label in [
            *[(user, evaluate_for_user, user.get_username()) for user in users],
            *[(lab, evaluate_for_lab, lab.slug) for lab in labs],
        ]:
            try:
                run = evaluate(target, today=today)
            except Exception as exc:  # noqa: BLE001 — one target never sinks the run
                summary["errors"] += 1
                self.stderr.write(self.style.WARNING(f"{label}: {exc}"))
                continue
            for key in (
                "considered",
                "fired",
                "held",
                "duplicates",
                "skipped_disabled",
            ):
                summary[key] += getattr(run, key)

        self.stdout.write(json.dumps(summary, indent=2))
        if summary["skipped_disabled"]:
            # Not a warning: it is the designed state until a calibration run has
            # set the thresholds (plan 3.8). Said out loud so nobody reads the
            # absence of overlap alerts as a broken matcher.
            self.stdout.write(
                self.style.NOTICE(
                    f"{summary['skipped_disabled']} similarity-based candidate(s) "
                    "not fired: PROJECT_ALERTS_ENABLED is off until the "
                    "thresholds are calibrated."
                )
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"{summary['fired']} alert(s) fired, {summary['held']} held for "
                f"the weekly, {summary['errors']} error(s)."
            )
        )
