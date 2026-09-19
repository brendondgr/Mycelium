"""Read every ambient conversation that is ready, now (ambient Plan 04).

The hourly Beat task, by hand. Safe at any time: an unchanged conversation is
never read twice, and nothing is read while ``AMBIENT_ENABLED`` is off.
"""

import json

from django.core.management.base import BaseCommand

from apps.ambient import reading


class Command(BaseCommand):
    help = "Read ambient conversations that have gone quiet."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=None)

    def handle(self, *args, **options):
        self.stdout.write(
            json.dumps(reading.read_ready(limit=options["limit"]).as_dict())
        )
