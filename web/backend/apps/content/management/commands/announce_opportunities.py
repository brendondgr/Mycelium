"""Announce each lab's newly fitting grants, fellowships and conferences.

Runs nightly from ``manual_all.py`` after scoring and before the briefings (plan
"The nightly path"). One forum thread per item, in each server the lab is bound
in. ``--dry-run`` decides everything and prints it, writes nothing and calls no
model unless ``--llm`` is given — it works whether or not announcements are
switched on, so a run can be read by hand before going live:

    uv run --project web/backend python web/backend/manage.py \
        announce_opportunities --dry-run

Never fails the nightly run: an error for one target is reported and the rest
carry on, and the command exits 0.
"""

from __future__ import annotations

import traceback

from django.core.management.base import BaseCommand
from django.utils import timezone
from tools.retrieval.models import AnnouncementSettings

from apps.content import announce
from apps.content import announce_editor as editor


class Command(BaseCommand):
    help = "Announce newly fitting opportunities to labs and departments."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--llm",
            action="store_true",
            help="With --dry-run, call the editor model too (costs a call per item).",
        )
        parser.add_argument("--today", default=None, metavar="YYYY-MM-DD")
        parser.add_argument(
            "--lab",
            default="",
            help="Only this lab (slug). With --dry-run it need not be switched on.",
        )

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
        targets = self._targets(options.get("lab") or "", dry_run)
        complete = editor._model_complete if (not dry_run or options["llm"]) else None
        poster = None
        if not dry_run:
            from apps.content import discord_announcements

            poster = discord_announcements.post
        for target in targets:
            try:
                outcome = announce.run_target(
                    target, today, dry_run=dry_run, complete=complete, poster=poster
                )
            except Exception:  # noqa: BLE001 — one target must not stop the rest
                self.stderr.write(
                    f"{target.kind} {target.key}: failed\n{traceback.format_exc()}"
                )
                continue
            self._print(outcome, dry_run)

    def _targets(self, lab_slug: str, dry_run: bool) -> list:
        if not lab_slug:
            return announce.enabled_targets()
        from apps.accounts.models import Lab

        lab = Lab.objects.filter(slug=lab_slug).first()
        if lab is None:
            self.stderr.write(f"No lab {lab_slug!r}.")
            return []
        settings_row = AnnouncementSettings.objects.filter(target_lab=lab).first()
        if settings_row is None:
            if not dry_run:
                self.stderr.write(f"{lab_slug} has no announcement settings.")
                return []
            settings_row = AnnouncementSettings(target_lab=lab, enabled=True)
        return [announce.Target("lab", lab, settings_row)]

    def _print(self, outcome, dry_run: bool) -> None:
        t = outcome.target
        mode = "DRY RUN · " if dry_run else ""
        what = "activation seed" if outcome.seeding else "new entrants"
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\n{mode}{t.kind} {t.name} ({t.key}) · {what}: "
                f"{len(outcome.posted)} to post, {len(outcome.held)} held back, "
                f"{len(outcome.skipped)} skipped by the editor, "
                f"{outcome.passed_over} passed over, {outcome.waiting} over the cap"
            )
        )
        for p in outcome.posted:
            w = p.write_up
            self.stdout.write(f"\n  ▸ [{p.item.type} · {p.packet.label}] {w.headline}")
            self.stdout.write(f"    Why it matters: {w.why_it_matters}")
            for c in p.checks:
                self.stdout.write(f"    {c.status:7} {c.label}")
            if w.who_should_look:
                people = "; ".join(
                    f"{x['name']} · {x['why']}" for x in w.who_should_look
                )
                self.stdout.write(f"    Who should look: {people}")
            self.stdout.write(f"    Next step: {w.next_step}")
            self.stdout.write(
                f"    ({w.source}{'; ' + p.editor_note if p.editor_note else ''})"
            )
        for p in outcome.held:
            self.stdout.write(f"  ✋ held back: {p.packet.title} — {p.held.label}")
        for p in outcome.skipped:
            self.stdout.write(
                f"  ⤼ editor skipped: {p.packet.title} — {p.write_up.skip_reason}"
            )
