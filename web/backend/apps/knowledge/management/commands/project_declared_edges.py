"""Mirror declared profiles, labs and projects into the knowledge graph.

With no arguments this is the nightly sweep and the one-time backfill: every
subject is reconciled and orphaned private concepts are pruned. Name one
subject to project just that one.
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from apps.knowledge import projection


class Command(BaseCommand):
    help = "Project declared profiles, labs and projects into the knowledge graph."

    def add_arguments(self, parser):
        target = parser.add_mutually_exclusive_group()
        target.add_argument("--user", help="A user id.")
        target.add_argument("--lab", help="A lab id.")
        target.add_argument("--project", help="A project id.")

    def handle(self, *args, **options):
        for kind in projection.KINDS:
            if options.get(kind):
                result = projection.project_by_key(kind, options[kind])
                if not result.subjects:
                    raise CommandError(f"no {kind} with id {options[kind]}")
                break
        else:
            result = projection.sweep()
        self.stdout.write(json.dumps(result.as_dict()))
        if result.failures:
            self.stderr.write("failed: " + ", ".join(result.failures))
