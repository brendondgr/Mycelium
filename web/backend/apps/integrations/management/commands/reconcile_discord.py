"""Run the Discord reconciliation sweep once (host-invocable).

Mirrors the ``apps.integrations.reconcile_discord`` Celery task for environments
that drive scheduled work from the host (like the daily run) rather than Beat ::

    uv run --project web/backend python manage.py reconcile_discord
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.integrations.services import reconcile


class Command(BaseCommand):
    help = "Reconcile Discord guild presence and OAuth token health."

    def handle(self, *args, **options):
        summary = reconcile.reconcile()
        self.stdout.write(
            self.style.SUCCESS(
                "Discord reconcile: "
                f"kicked={summary['kicked']} refreshed={summary['refreshed']} "
                f"revoked={summary['revoked']} guild_sweep={summary['guild_sweep']}"
            )
        )
