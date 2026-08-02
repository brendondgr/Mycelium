"""Queue each entitled lab's daily digest to its bound Discord updates channel.

Two messages per lab, in order: the counts-by-theme summary, then the lab's written
report — the same one it reads in the portal — split across follow-up messages in
the same channel.

Runs as a stage of the daily chain, after the briefings are written (which is what
makes the report available to post at all). Never raises: one lab's bad day must not
sink the run, exactly as the personal report stage behaves.

    manage.py send_lab_digests [--lab <slug>] [--dry-run]

(prefix with `uv run --project web/backend python web/backend/`.)
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Post each entitled lab's daily digest to its Discord updates channel."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--lab",
            action="append",
            dest="slugs",
            help="Limit to this lab slug. Repeat for several.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Compile and report, but queue nothing.",
        )

    def handle(self, *args, **options) -> None:
        from apps.accounts.models import Lab
        from apps.content.lab_digest import (
            compile_lab_digest,
            eligible_labs,
            queue_lab_digest,
            queue_lab_report,
            report_chunks,
            written_briefing_body,
        )
        from apps.content.tasks import select_targets

        slugs = options.get("slugs")
        if slugs:
            labs = list(Lab.objects.filter(slug__in=slugs))
        else:
            # The same subscription-active set the rest of the daily run uses, then
            # narrowed by the add-on / link / bound-channel checks.
            labs, _projects = select_targets(None)

        eligible = eligible_labs(labs)
        summary = {
            "considered": len(labs),
            "eligible": len(eligible),
            "queued": 0,
            "report_messages": 0,
            "empty": 0,
            "errors": 0,
        }
        today = timezone.localdate()

        for lab in eligible:
            try:
                digest = compile_lab_digest(lab, on=today)
                if digest.is_empty:
                    summary["empty"] += 1
                    continue
                if options["dry_run"]:
                    chunks = report_chunks(written_briefing_body(lab))
                    self.stdout.write(
                        f"{lab.slug}: {digest.total} item(s) across "
                        f"{len(digest.themes)} theme(s); "
                        f"{len(chunks)} report message(s)"
                    )
                    continue
                _row, created = queue_lab_digest(lab, on=today, digest=digest)
                summary["queued"] += int(bool(created))
                # Enqueued after the summary so the outbox — which claims by
                # (next_attempt_at, id) and delivers one at a time — posts it after.
                summary["report_messages"] += queue_lab_report(lab, on=today)
            except Exception as exc:  # noqa: BLE001 — one lab never sinks the run
                summary["errors"] += 1
                self.stderr.write(self.style.WARNING(f"{lab.slug}: {exc}"))

        self.stdout.write(json.dumps(summary, indent=2))
        if summary["queued"]:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Queued {summary['queued']} lab digest(s) and "
                    f"{summary['report_messages']} report message(s); "
                    "the outbox delivers."
                )
            )
