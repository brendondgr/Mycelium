"""Delete every grant and conference, so the corpus can be rebuilt from open sources.

This exists for exactly one job: retiring Pivot-RP. It is deliberately **not** a
general "clear the database" tool, and it is deliberately narrow about what it
will touch.

    uv run --project web/backend python web/backend/manage.py reset_opportunities --yes

**Fellowships are never deleted.** They come from the Illinois Fellowship Finder,
a public source that has nothing to do with Pivot-RP and is not being replaced —
the fact that its code once lived in a directory named ``pivot`` was an accident
of filing, not a dependency. Papers, users, labs, projects, billing and Discord
links are equally untouched.

**Why the ORM and not ``TRUNCATE``.** Deleting a ``ContentItem`` fires
``pre_delete``, which marks any reminder pointing at it as stale
(:mod:`apps.content.signals`). Truncating at SQL level is far faster and would
skip that signal entirely, leaving live reminders firing against snapshots of
listings that no longer exist. A slow correct wipe beats a fast one that leaves
someone being reminded about a deadline we can no longer show them.

**What survives on purpose.** ``SavedOpportunity.content`` is ``SET_NULL`` with a
display + deadline snapshot taken at save time, so a save outlives the item it
points at and the Saves page keeps rendering from the snapshot. Those saves will
**not** re-attach when the "same" opportunity arrives from a new source under a
new ``(source, external_id)`` — that pairing is genuinely lost, and it is the one
user-visible cost of the migration. ``--report`` prints how many saves are about
to be orphaned so the number is known rather than discovered.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from apps.content.models import ContentItem, SavedOpportunity

#: The two areas being re-sourced. Fellowships are pointedly absent.
RESET_TYPES = (ContentItem.Type.GRANT, ContentItem.Type.CONFERENCE)


class Command(BaseCommand):
    help = "Delete all grant and conference items so the corpus can be rebuilt."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Actually delete. Without it the command only reports.",
        )
        parser.add_argument(
            "--source",
            default=None,
            help=(
                "Restrict to one source id (e.g. 'pivot'). Default: every source, "
                "which is what a full re-source wants."
            ),
        )
        parser.add_argument(
            "--types",
            default=",".join(RESET_TYPES),
            help=f"Comma-separated item types. Default: {','.join(RESET_TYPES)}.",
        )

    def handle(self, *args, **options) -> None:
        types = [t.strip() for t in options["types"].split(",") if t.strip()]
        unknown = set(types) - set(ContentItem.Type.values)
        if unknown:
            raise CommandError(f"unknown type(s): {sorted(unknown)}")
        if ContentItem.Type.FELLOWSHIP in types:
            # Guarded rather than merely undocumented. Fellowships are not part of
            # this migration and deleting 829 of them would be silent, expensive
            # and unrecoverable without a restore.
            raise CommandError(
                "refusing to delete fellowships: they come from the public Illinois "
                "Fellowship Finder and are not being re-sourced. Pass an explicit "
                "--types list without 'fellowship'."
            )

        qs = ContentItem.objects.filter(type__in=types)
        if options["source"]:
            qs = qs.filter(source=options["source"])

        breakdown = list(
            qs.values("type", "source").annotate(n=Count("id")).order_by("type", "-n")
        )
        total = sum(row["n"] for row in breakdown)
        orphaned = SavedOpportunity.objects.filter(content__in=qs).count()

        if not total:
            self.stdout.write("Nothing to delete.")
            return

        self.stdout.write(f"About to delete {total} item(s):")
        for row in breakdown:
            self.stdout.write(f"    {row['type']:<12} {row['source']:<28} {row['n']:>6}")
        self.stdout.write(
            f"{orphaned} save(s) point at these and will fall back to their "
            "snapshot (SET_NULL). They will not re-attach to the new records."
        )

        if not options["yes"]:
            self.stdout.write(
                self.style.WARNING("Dry run. Re-run with --yes to delete.")
            )
            return

        # One ORM delete so pre_delete fires per row and reminders are marked
        # stale. Django batches the SQL; the signal cost is the point, not waste.
        deleted, _ = qs.delete()
        self.stdout.write(
            self.style.SUCCESS(f"Deleted {total} item(s) ({deleted} rows incl. cascades).")
        )
