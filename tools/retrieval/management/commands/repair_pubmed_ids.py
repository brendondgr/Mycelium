"""Correct the DOI / PMCID stored on PubMed papers before the Q-057 fix.

The PubMed scraper used to keep a cited paper's DOI and PMCID (and build the
row's ``external_id`` from that DOI). This re-fetches each PMID-bearing paper's
PubMed record and puts the article's own ids back. See
``tools/retrieval/pubmed_repair.py`` for exactly what is and is not changed.

    # preview only — no writes (fetches from PubMed, ~1 request per 200 papers)
    uv run --directory web/backend python manage.py repair_pubmed_ids

    # write the corrections, then merge the duplicates they expose
    uv run --directory web/backend python manage.py repair_pubmed_ids --apply
    uv run --directory web/backend python manage.py dedupe_content_papers

Default is a dry run. Safe to re-run.
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from tools.retrieval.pubmed_repair import repair_pubmed_ids


class Command(BaseCommand):
    help = "Re-fetch PubMed records and correct papers' stored DOI/PMCID (Q-057)."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--apply", action="store_true",
                            help="Write the corrections (default is a dry run).")
        parser.add_argument("--limit", type=int, default=None,
                            help="Only check the first N PMID-bearing papers.")
        parser.add_argument("--json", action="store_true",
                            help="Print the final counts as JSON.")

    def handle(self, *args, **options) -> None:
        apply = options["apply"]
        if not apply:
            self.stdout.write(self.style.WARNING("DRY RUN — no changes written"))
        stats = repair_pubmed_ids(apply=apply, limit=options["limit"],
                                  log=lambda m: self.stdout.write(m))
        if options["json"]:
            self.stdout.write(json.dumps(stats.as_dict(), indent=1))
        verb = "Corrected" if apply else "Would correct"
        style = self.style.SUCCESS if apply else self.style.WARNING
        self.stdout.write(style(
            f"{verb} {stats.rows_changed - stats.other_source_pmcid_fixed} of "
            f"{stats.pubmed_rows} PubMed row(s); "
            f"{stats.duplicates_exposed} duplicate(s) exposed "
            "(merge with dedupe_content_papers), "
            f"{stats.external_id_collisions} external_id collision(s) kept, "
            f"{stats.other_source_pmcid_fixed} other-source row(s) given back "
            "their own PMCID, "
            f"{stats.foreign_pmid_rows} other-source row(s) with a citing "
            "paper's PMID (not changed)."
        ))
