"""Roll ended billing periods and revoke seats whose deferred-removal cutoff has passed.

A lightweight daily tick for the subscription lifecycle. Schedule it from a host timer
(sibling to ``mylo-daily``) or Celery beat — it is deliberately **not** part of the
recommendation daily run (that run only scores new items). Idempotent; safe to re-run.

    uv run --project web/backend python web/backend/manage.py run_billing_tick
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.billing import period


class Command(BaseCommand):
    help = "Advance ended billing periods and revoke lapsed (deferred-removal) seats."

    def handle(self, *args, **options):
        rolled = period.roll_periods()
        revoked = period.end_lapsed_seats()
        self.stdout.write(
            self.style.SUCCESS(
                f"billing tick: rolled {rolled} period(s), "
                f"revoked {revoked} lapsed seat(s)."
            )
        )
