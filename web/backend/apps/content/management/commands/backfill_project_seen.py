"""Seed the project seen ledger from existing per-project relevance scores.

Before the collaboration feed existed, papers already surfaced to a project via the
daily matcher (``RelevanceScore`` rows under ``target_project``). This one-off command
records those as ``ProjectItemSeen`` rows (``first_seen_via='digest'``) so the "already
surfaced in this project" badge is accurate from day one. Idempotent — safe to re-run.
"""

from django.core.management.base import BaseCommand
from tools.recommendation.models import RelevanceScore
from tools.retrieval.models import ProjectItemSeen

from apps.content.collaboration import mark_seen


class Command(BaseCommand):
    help = (
        "Backfill the project seen ledger from existing per-project relevance "
        "scores (first_seen_via='digest')."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be written without touching the ledger.",
        )

    def handle(self, *args, **options) -> None:
        dry_run = bool(options["dry_run"])
        scores = RelevanceScore.objects.filter(
            target_project__isnull=False
        ).select_related("target_project", "content")

        seen_pairs: set = set()
        created = 0
        for score in scores.iterator():
            key = (score.target_project_id, score.content_id)
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            if ProjectItemSeen.objects.filter(
                project_id=score.target_project_id, content_id=score.content_id
            ).exists():
                continue
            if not dry_run:
                mark_seen(
                    score.target_project,
                    score.content,
                    ProjectItemSeen.Via.DIGEST,
                )
            created += 1

        verb = "Would create" if dry_run else "Created"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} {created} project-seen ledger row(s) from "
                f"{len(seen_pairs)} distinct (project, item) pair(s)."
            )
        )
