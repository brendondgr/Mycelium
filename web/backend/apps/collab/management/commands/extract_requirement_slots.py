"""Read what funding calls ask a team to bring (plan CN-03).

Nightly (``manual_all.py``, before the scoring stages, non-fatal): every grant
whose slots are missing or were read under an older prompt, newest first,
within ``COLLAB_SLOTS_NIGHTLY_CAP``. Exits 0 when the model is unreachable —
the calls are simply read tomorrow.
"""

from __future__ import annotations

import json

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.collab import slots


class Command(BaseCommand):
    help = "Read requirement slots out of funding calls."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, help="Calls to read this run.")
        parser.add_argument("--content", help="One content id: read it now.")

    def handle(self, *args, **options):
        items = slots.grants()
        if options.get("content"):
            items = items.filter(pk=options["content"])
        limit = options.get("limit")
        if limit is None:
            limit = settings.COLLAB_SLOTS_NIGHTLY_CAP
        result = slots.read_calls(items, limit=limit)
        self.stdout.write(json.dumps(result.as_dict()))
