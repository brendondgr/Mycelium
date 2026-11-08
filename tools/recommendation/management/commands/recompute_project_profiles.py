"""Recompute project team-relevance profiles (Feature D).

Blends each project's declared focus, its members' interest vectors, and their
recent weighted engagement into a team vector (written to ``Project.embedding``)
plus aggregated interest terms. Run manually, or nightly via the Celery beat job.
"""

from apps.research.models import Project
from django.core.management.base import BaseCommand

from tools.recommendation.models import ProjectProfile
from tools.recommendation.team_profile import recompute_project_profile


class Command(BaseCommand):
    help = "Recompute the team-relevance signal for projects (Feature D)."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--project",
            action="append",
            dest="project_ids",
            help="Project id to recompute (repeatable). Omit for all projects.",
        )
        parser.add_argument(
            "--async",
            action="store_true",
            dest="is_async",
            help="Dispatch a Celery task instead of running inline.",
        )

    def handle(self, *args, **options) -> None:
        project_ids = options.get("project_ids")
        if options["is_async"]:
            from tools.recommendation.tasks import recompute_project_profiles

            task = recompute_project_profiles.delay(project_ids)
            self.stdout.write(self.style.SUCCESS(f"Dispatched task {task.id}."))
            return

        queryset = Project.objects.all()
        if project_ids:
            queryset = queryset.filter(id__in=project_ids)
        done = 0
        for project in queryset.iterator():
            recompute_project_profile(
                project, reason=ProjectProfile.Reason.MANUAL, embed_missing=True
            )
            done += 1
        self.stdout.write(
            self.style.SUCCESS(f"Recomputed {done} project team profile(s).")
        )
