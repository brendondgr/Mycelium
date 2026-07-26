"""Deliver the outbound Discord queue by hand.

The queue normally drains on Celery Beat every minute. This is for the cases Beat
cannot cover: a host run, a stack where the worker is down, or an operator who wants
to see what the queue is holding before releasing it.

    manage.py drain_discord_outbox            # one pass
    manage.py drain_discord_outbox --stats    # report only, deliver nothing
    manage.py drain_discord_outbox --limit 5  # a small, cautious pass

(prefix with `uv run --project web/backend python web/backend/`.)
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from apps.integrations.services import outbox, resolve


class Command(BaseCommand):
    help = "Attempt delivery of queued Discord messages (or just report on them)."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum messages to attempt in this pass.",
        )
        parser.add_argument(
            "--stats",
            action="store_true",
            help="Report queue counters and exit without sending anything.",
        )

    def handle(self, *args, **options) -> None:
        if options["stats"]:
            self.stdout.write(json.dumps(resolve.outbox_counters(), indent=2))
            return

        result = outbox.drain(limit=options.get("limit"))
        self.stdout.write(json.dumps(result.as_dict(), indent=2))

        if result.dead:
            self.stdout.write(
                self.style.WARNING(
                    f"{result.dead} message(s) exhausted their attempts and were "
                    "dead-lettered. The affected people have been told in-app."
                )
            )
        elif result.claimed:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Delivered {result.delivered} of {result.claimed} claimed."
                )
            )
        else:
            self.stdout.write("Nothing due.")
