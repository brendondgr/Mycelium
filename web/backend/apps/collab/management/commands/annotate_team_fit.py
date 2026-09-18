"""Write the team-fit line on every grant each target has already been shown.

The nightly opportunity batch does this itself after scoring; this command is
for a backfill (after slots are first read) or a single target, without
re-scoring anything.
"""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.accounts.models import Lab
from apps.collab.team_fit import annotate_target
from apps.content.targets import target_for_lab, target_for_project, target_for_user
from apps.research.models import Project


class Command(BaseCommand):
    help = "Write the team-fit line on grants already shown to each target."

    def add_arguments(self, parser):
        parser.add_argument("--user", help="One user id.")
        parser.add_argument("--lab", help="One lab id.")

    def handle(self, *args, **options):
        User = get_user_model()
        if options.get("user"):
            targets = [target_for_user(User.objects.get(pk=options["user"]))]
        elif options.get("lab"):
            targets = [target_for_lab(Lab.objects.get(pk=options["lab"]))]
        else:
            targets = [
                *(
                    target_for_user(u)
                    for u in User.objects.filter(
                        relevance_scores__isnull=False
                    ).distinct()
                ),
                *(target_for_lab(lab) for lab in Lab.objects.all()),
                *(target_for_project(p) for p in Project.objects.active()),
            ]
        changed = sum(annotate_target(target) for target in targets)
        self.stdout.write(
            json.dumps({"targets": len(targets), "rows_changed": changed})
        )
