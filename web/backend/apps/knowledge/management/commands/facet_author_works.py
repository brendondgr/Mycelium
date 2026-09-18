"""Read people's own papers into facets and demonstrated edges.

The nightly pass (``manual_all.py`` runs it after the daily stages): look up
the OpenAlex field of works from other sources, read every unread work within
``KNOWLEDGE_WORK_FACETS_NIGHTLY_CAP``, fill vectors the embedder missed, and
rebuild the demonstrated edges of everyone whose papers changed. Exits 0 when
the model is unreachable — the works stay unread and are tried tomorrow.
"""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.knowledge import papers


class Command(BaseCommand):
    help = "Read people's own papers into facets and demonstrated edges."

    def add_arguments(self, parser):
        parser.add_argument("--user", help="One user id: read all their works now.")
        parser.add_argument("--limit", type=int, help="Works to read this run.")
        parser.add_argument(
            "--lookups", type=int, help="DOI lookups to make this run (0 for none)."
        )

    def handle(self, *args, **options):
        if options.get("user"):
            user = get_user_model().objects.filter(pk=options["user"]).first()
            if user is None:
                raise CommandError(f"no user with id {options['user']}")
            result = papers.refresh_person(user)
        else:
            result = papers.refresh_pending(
                limit=options.get("limit"), lookups=options.get("lookups")
            )
        self.stdout.write(json.dumps(result.as_dict()))
        if result.failures:
            self.stderr.write("failed: " + ", ".join(result.failures))
