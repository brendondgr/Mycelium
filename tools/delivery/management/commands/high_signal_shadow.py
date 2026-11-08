"""Shadow-mode calibration (and gated delivery) for high-signal alerts (R7).

By default this **only measures** how many alerts each user would get per week at a
given floor — run it over the real corpus and tune ``HIGH_SIGNAL_FLOOR`` before any
delivery is wired (D-14). A floor of 90 that fires 40 times a week for one user is
worse than the current zero.

    manage.py high_signal_shadow              # measure at the configured floor
    manage.py high_signal_shadow --floor 85   # try a candidate floor
    manage.py high_signal_shadow --deliver    # deliver in-app (only if enabled)

(prefix with `uv run --project web/backend python web/backend/`.)
"""

from __future__ import annotations

import json

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from tools.delivery.high_signal import deliver_high_signal, shadow_report
from tools.recommendation.tasks import select_users


class Command(BaseCommand):
    help = "Measure (or, if enabled, deliver) high-signal alerts — calibration first."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--floor", type=int, default=None, help="Override the floor."
        )
        parser.add_argument(
            "--user",
            "-u",
            action="append",
            dest="usernames",
            help="Limit to this user. Repeat for several. Default: all active users.",
        )
        parser.add_argument(
            "--deliver",
            action="store_true",
            help="Deliver in-app (requires HIGH_SIGNAL_DELIVERY_ENABLED).",
        )
        parser.add_argument(
            "--today",
            default=None,
            metavar="YYYY-MM-DD",
            help="Reference date to measure against. Default: today.",
        )

    def handle(self, *args, **options) -> None:
        raw = options.get("today")
        today = (
            timezone.datetime.fromisoformat(raw).date()
            if raw
            else timezone.localdate()
        )
        users = select_users(options.get("usernames"))
        floor = options.get("floor")

        if not options["deliver"]:
            report = shadow_report(users, today=today, floor=floor)
            self.stdout.write(json.dumps(report, indent=2))
            self.stdout.write(
                self.style.WARNING(
                    "Shadow mode — nothing delivered. Calibrate HIGH_SIGNAL_FLOOR "
                    "against these numbers before enabling delivery (D-14)."
                )
            )
            return

        if not getattr(settings, "HIGH_SIGNAL_DELIVERY_ENABLED", False):
            self.stderr.write(
                self.style.ERROR(
                    "Delivery is disabled. Calibrate the floor in shadow mode, then "
                    "set HIGH_SIGNAL_DELIVERY_ENABLED=true to deliver."
                )
            )
            return

        delivered = sum(
            deliver_high_signal(user, today=today, floor=floor) for user in users
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Delivered {delivered} high-signal alert(s) "
                f"across {len(users)} user(s)."
            )
        )
