"""Backfill "who is this for?" over labs' and projects' existing feeds.

The layer is normally written by the scoring passes (the daily opportunity batch's
phase 3, and every on-demand refit). This command is the catch-up: it annotates
feeds that were scored before the layer existed, or re-annotates after a lab's
membership or a member's profile changed without a re-score.

Never touches what a feed contains — only ``RelevanceScore.signals["member_fit"]``.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.accounts.models import Lab
from apps.research.models import Project

from ...member_fit import annotate_for_target
from ...targets import target_for_lab, target_for_project


class Command(BaseCommand):
    help = "Recompute per-item member recommendations for labs and projects."

    def add_arguments(self, parser):
        parser.add_argument(
            "--lab", help="Annotate only this lab (slug).", default=None
        )
        parser.add_argument(
            "--project", help="Annotate only this project (id).", default=None
        )
        parser.add_argument(
            "--no-llm",
            action="store_true",
            help="Skip Mylo's rationale; write the deterministic overlap reasons only.",
        )

    def handle(self, *args, **options):
        def log(message: str) -> None:
            self.stdout.write(message)

        # A ``complete`` that returns nothing makes the module fall back to its
        # deterministic reasons without ever reaching for the model.
        complete = (lambda _prompt: None) if options["no_llm"] else None

        labs = Lab.objects.all()
        if options["lab"]:
            labs = labs.filter(slug=options["lab"])
        projects = Project.objects.active()
        if options["project"]:
            projects = projects.filter(id=options["project"])
        elif options["lab"]:
            projects = projects.filter(scope_lab__slug=options["lab"])

        targets = [
            *(("lab", lab.slug, target_for_lab(lab)) for lab in labs),
            *(
                ("project", str(project.id), target_for_project(project))
                for project in projects
            ),
        ]
        if not targets:
            self.stdout.write("No matching labs or projects.")
            return

        total = 0
        for kind, key, target in targets:
            written = annotate_for_target(target, complete=complete, log=log)
            named = sum(written.values())
            total += named
            self.stdout.write(f"{kind} {key}: named members on {named} items")
        self.stdout.write(self.style.SUCCESS(f"Annotated {total} items."))
