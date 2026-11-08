"""Collapse cross-source duplicate paper rows already in the store.

Before the against-store dedup fix, the same paper could land twice — e.g.
OpenAlex under ``doi:…`` and SemanticScholar under ``semanticscholar:…`` — so it
showed up twice in a recommendation feed. This command finds those pairs (shared
DOI/PMID/PMCID/arXiv, or a matching normalized title + author + year) and merges
each group into one row, repointing every score / save / share / collection /
suggestion onto the survivor.

    # preview only — no writes
    uv run --project web/backend python web/backend/manage.py dedupe_content_papers

    # actually merge
    uv run --project web/backend python web/backend/manage.py \
        dedupe_content_papers --apply

Default is a dry run; pass ``--apply`` to write. Safe to re-run (idempotent).
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from tools.retrieval.dedupe import dedupe_papers


class Command(BaseCommand):
    help = "Merge cross-source duplicate paper ContentItems into one row each."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Perform the merges (default is a dry-run preview).",
        )

    def handle(self, *args, **options) -> None:
        apply = options["apply"]
        if not apply:
            self.stdout.write(self.style.WARNING("DRY RUN — no changes written"))

        stats = dedupe_papers(apply=apply, log=lambda m: self.stdout.write(m))

        summary = (
            f"{stats.groups} duplicate group(s), {stats.duplicates} redundant row(s)"
        )
        if apply:
            self.stdout.write(self.style.SUCCESS(f"Merged: {summary}"))
        else:
            self.stdout.write(
                self.style.WARNING(f"Would merge: {summary} (re-run with --apply)")
            )
