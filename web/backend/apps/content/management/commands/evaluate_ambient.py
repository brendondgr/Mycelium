"""Ambient Plan 10: the measures and harm checks, as JSON.

    manage.py evaluate_ambient [--days 28] [--out path]

Every harm check must be zero. Counts and ids only — no text leaves.
Lives in the content app only because one check reads the stored lab reports,
and the ambient app may not import this one.
"""

import json
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.ambient.read import evaluation_report


class Command(BaseCommand):
    help = "Report ambient validation precision, maintenance and harm checks."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=28)
        parser.add_argument("--out", default="")

    def handle(self, *args, **options):
        from apps.content.models import DailyBriefing

        until = timezone.now()
        since = until - timedelta(days=options["days"])
        lab_reports = list(
            DailyBriefing.objects.filter(lab__isnull=False).values_list("pk", "body")
        )
        result = evaluation_report(since=since, until=until, lab_reports=lab_reports)
        text = json.dumps(result, indent=1, default=str)
        if options["out"]:
            with open(options["out"], "w") as handle:
                handle.write(text)
        self.stdout.write(text)
        if result["harm_checks"]["_total"]:
            self.stderr.write(
                f"{result['harm_checks']['_total']} harm-check violation(s)"
            )
