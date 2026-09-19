"""Rebuild who on Mycelium published with whom (plan CN-07).

The nightly knowledge sweep does this too; run it by hand after a bulk import
of people's works, or to backfill.
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from apps.knowledge import coauthorship


class Command(BaseCommand):
    help = "Rebuild the co-authorship table from people's own works."

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(coauthorship.rebuild().as_dict()))
