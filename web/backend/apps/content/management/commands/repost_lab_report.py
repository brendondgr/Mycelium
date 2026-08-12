"""Re-render one lab's daily report and post it to its updates channel again.

The lab-shaped half of the manual re-delivery pair; ``resend_user_report`` is the
person-shaped one. The names are deliberately different verbs because the deliveries
are: a person is *re-sent* a DM, a lab is *re-posted* to its channel.

Only the report PDF goes back up. The counts-by-theme summary the nightly digest
posts above it describes the same day and would read as a second morning.

Unlike ``send_lab_digests --lab``, this actually posts: that command shares the
daily chain's per-day dedupe key, so a same-day repeat re-found the row it had
already delivered and queued nothing.

    uv run --project web/backend python web/backend/manage.py \\
        repost_lab_report --lab reyes-lab
    ... --lab a --lab b          # several labs
    ... --no-regenerate          # re-post the briefing exactly as written
    ... --dry-run                # regenerate + render, queue nothing
    ... --save-dir /tmp/reports  # write the PDF here instead of the outbox dir
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Lab
from apps.content.report_resend import repost_lab_report


class Command(BaseCommand):
    help = "Re-render one or more labs' daily reports and re-post them to Discord."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--lab",
            "-l",
            action="append",
            dest="slugs",
            metavar="SLUG",
            required=True,
            help="The lab slug to re-post for. Repeat for several.",
        )
        parser.add_argument(
            "--no-regenerate",
            action="store_true",
            help="Keep the stored briefing instead of rewriting it first.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Regenerate and render, but queue nothing.",
        )
        parser.add_argument(
            "--save-dir",
            dest="save_dir",
            metavar="PATH",
            help="Write the PDF here instead of the outbox attachment directory.",
        )

    def handle(self, *args, **options) -> None:
        slugs = [s.strip() for s in options["slugs"] if s and s.strip()]
        labs = list(Lab.objects.filter(slug__in=slugs))
        found = {lab.slug for lab in labs}
        missing = [slug for slug in slugs if slug not in found]
        if missing:
            # Loudly, not as a zero-recipient no-op: a mistyped slug is the single
            # likeliest reason an operator sees nothing happen.
            raise CommandError(f"no such lab(s): {', '.join(missing)}")

        outcomes = []
        for lab in labs:
            outcome = repost_lab_report(
                lab,
                regenerate=not options["no_regenerate"],
                dry_run=options["dry_run"],
                report_dir=options.get("save_dir"),
            )
            outcomes.append(outcome)
            style = self.style.SUCCESS if outcome.ok else self.style.WARNING
            self.stdout.write(style(outcome.summary()))

        self.stdout.write(json.dumps([o.as_dict() for o in outcomes], indent=2))
        queued = sum(1 for o in outcomes if o.ok)
        self.stdout.write(
            self.style.SUCCESS(
                f"{queued}/{len(outcomes)} queued; the outbox drain delivers."
            )
            if queued
            else self.style.WARNING("Nothing was queued — see the reasons above.")
        )
