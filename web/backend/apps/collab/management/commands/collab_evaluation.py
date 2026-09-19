"""Where the collaboration network stands (plan CN-08): the day's counts, the
harm checks, concentration, and whether search may widen to the next scope.

Counts only — nothing here names a person.
"""

from __future__ import annotations

import json
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.collab import evaluation


class Command(BaseCommand):
    help = "Report collaboration counts, harm checks and scope readiness."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days", type=int, default=1, help="Harm checks over this many days."
        )

    def handle(self, *args, **options):
        now = timezone.now()
        report = {
            "today": evaluation.daily_counts(timezone.localdate()),
            "harm": evaluation.harm_checks(now - timedelta(days=options["days"]), now),
            "readiness": evaluation.readiness(now),
        }
        self.stdout.write(json.dumps(report, indent=1, default=str))
