"""Run the ambient retention sweep by hand.

The same sweep Beat runs nightly. Useful after changing the retention window,
and useful for showing somebody exactly what the sweep touches — which is
message references and nothing else.
"""

from django.core.management.base import BaseCommand

from apps.ambient import retention


class Command(BaseCommand):
    help = "Delete ambient message references past the retention window."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be deleted without deleting it.",
        )

    def handle(self, *args, **options):
        days = retention.ref_retention_days()
        if options["dry_run"]:
            from datetime import timedelta

            from django.utils import timezone

            from apps.ambient.models import RawMessageRef

            cutoff = timezone.now() - timedelta(days=days)
            count = RawMessageRef.objects.filter(sent_at__lt=cutoff).count()
            self.stdout.write(
                f"{count} message references are older than {days} days; "
                "observations are never touched by this sweep."
            )
            return

        result = retention.sweep()
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {result.refs_deleted} message references past {days} days "
                f"and cleared {result.stamps_cleared} expired buffer stamps."
            )
        )
