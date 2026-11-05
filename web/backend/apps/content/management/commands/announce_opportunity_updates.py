"""Keep announced opportunities current (plan D9, D11).

Runs nightly right after ``announce_opportunities``: updates the thread of every
call that changed (edited in place, renamed ``[🚨 Update <Mon D>]``, tagged, and a
reply tagging the people following it), sends due nudges, replaces each forum's
closing-soon list, and closes threads whose last deadline passed. ``--dry-run``
prints the plan and touches nothing:

    uv run --project web/backend python web/backend/manage.py \
        announce_opportunity_updates --dry-run

Never fails the nightly run: errors are reported per target and it exits 0.
"""

from __future__ import annotations

import traceback

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.content import announce, announce_updates


class Command(BaseCommand):
    help = "Update, nudge, list closing-soon and close announced opportunities."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--today", default=None, metavar="YYYY-MM-DD")

    def handle(self, *args, **options) -> None:
        dry_run = options["dry_run"]
        if not dry_run and not announce.enabled():
            self.stdout.write(
                "Opportunity announcements are switched off; nothing to do."
            )
            return
        raw = options.get("today")
        today = (
            timezone.datetime.fromisoformat(raw).date() if raw else timezone.localdate()
        )
        for target in announce.enabled_targets():
            try:
                plan = announce_updates.plan(target, today)
                self._print(plan, dry_run)
                if not dry_run:
                    from apps.content import discord_announcements

                    discord_announcements.apply_updates(plan, today)
            except Exception:  # noqa: BLE001 — one target must not stop the rest
                self.stderr.write(
                    f"{target.kind} {target.key}: failed\n{traceback.format_exc()}"
                )
        if not dry_run:
            from apps.content import discord_announcements

            sent = discord_announcements.send_due_nudges(today)
            self.stdout.write(f"Nudges sent: {sent}")

    def _print(self, plan, dry_run: bool) -> None:
        t = plan.target
        mode = "DRY RUN · " if dry_run else ""
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\n{mode}{t.kind} {t.name} ({t.key}): {len(plan.changed)} changed, "
                f"{len(plan.to_close)} to close, "
                + ", ".join(
                    f"{len(v)} {k}s closing soon" for k, v in plan.closing_soon.items()
                )
            )
        )
        for c in plan.changed:
            self.stdout.write(f"  🚨 {c.announcement.snapshot.get('title', '')}")
            for change in c.changes:
                self.stdout.write(f"     {change.line()}")
        for a in plan.to_close:
            self.stdout.write(f"  🔒 {a.snapshot.get('title', '')}")
        for kind, rows in plan.closing_soon.items():
            for r in rows:
                self.stdout.write(
                    f"  ⏳ {kind}: {r.due:%a, %b %d} ({r.days} days) {r.title}"
                )
