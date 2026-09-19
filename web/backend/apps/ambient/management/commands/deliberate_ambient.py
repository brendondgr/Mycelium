"""Decide, nightly, what the day's observations mean (ambient Plan 04).

Called by ``manual_all.py`` before ranking, outside its load-bearing stages:
nothing a person receives today depends on it yet, so a failure here is a
warning and never a failed run. Does nothing while
``AMBIENT_DELIBERATE_ENABLED`` is off.

Three steps: read any conversation still waiting (the hourly task's work, in
case Beat missed it), decide every finding (pure, no model), and write the
explanations the decided findings need (model-written; a missing model leaves
them pending for tomorrow).
"""

import json

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.ambient import deliberate, explain, reading


class Command(BaseCommand):
    help = "Decide what ambient observations mean, and explain what will be asked."

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-explain",
            action="store_true",
            help="Decide only; leave explanations pending.",
        )

    def handle(self, *args, **options):
        if not settings.AMBIENT_DELIBERATE_ENABLED:
            self.stdout.write(
                "ambient deliberation is off (AMBIENT_DELIBERATE_ENABLED)"
            )
            return
        out = {"read": reading.read_ready().as_dict()}
        out["deliberate"] = deliberate.deliberate().as_dict()
        if not options["no_explain"]:
            out["explain"] = explain.explain_pending().as_dict()
        self.stdout.write(json.dumps(out, default=str))
