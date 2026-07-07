"""Scrape Pivot-RP grants/conferences to JSON (browser step, run on the host).

    uv run --project web/backend python web/backend/manage.py scrape_pivot \
        --topic "agentic ai" --topic "knowledge graphs" --out data/pivot

Uses the saved login session (run ``pivot_login`` first) to scrape and write one
JSON file per area (``pivot_grants.json`` / ``pivot_conferences.json``) — the raw
tool schema. This is the browser half of the flow and needs no database, so it
runs on the host; feed the files to ``ingest_pivot --source json`` inside the
container to upsert + prune + embed them. Grants search is topic-driven (pass
``--topic``); conferences walk every subject on their own.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Scrape Pivot grants/conferences to JSON (host browser step)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--topic",
            action="append",
            dest="topics",
            metavar="TEXT",
            help="Grant search topic (repeatable). Conferences ignore this.",
        )
        parser.add_argument(
            "--area",
            action="append",
            choices=["grants", "conferences", "fellowships"],
            dest="areas",
            help="Limit to an area (repeatable). Default: all three.",
        )
        parser.add_argument(
            "--out",
            default="data/pivot",
            help="Output directory for the JSON files (default: data/pivot).",
        )

    def handle(self, *args, **options):
        areas = tuple(options.get("areas") or ("grants", "conferences", "fellowships"))

        # Pivot SSO session is only required for grants + conferences.
        pivot_areas = [a for a in areas if a in ("grants", "conferences")]
        if pivot_areas:
            from apps.scraper.pivot.common import state_exists

            if not state_exists():
                if set(areas) == {"fellowships"}:
                    pass  # fellowships-only scrape needs no session
                else:
                    raise CommandError(
                        "No saved session — run 'pivot_login' first (and on a machine "
                        "with a display). Pass --area fellowships to scrape only the "
                        "public fellowship site without a session."
                    )

        from apps.scraper.pivot.scrape import refresh
        topics = [t for t in (options.get("topics") or []) if t and t.strip()]
        if "grants" in areas and not topics:
            self.stdout.write(
                self.style.WARNING(
                    "No --topic given; grants search needs topics and will be empty."
                )
            )

        pairs = list(refresh(areas=areas, topics=topics, log=self.stdout.write))
        if not pairs:
            self.stdout.write(self.style.WARNING("Scrape returned nothing."))
            return

        by_area: dict[str, list[dict]] = {}
        for area, rec in pairs:
            by_area.setdefault(area, []).append(rec)

        out_dir = Path(options["out"])
        out_dir.mkdir(parents=True, exist_ok=True)
        for area, records in by_area.items():
            path = out_dir / f"pivot_{area}.json"
            path.write_text(json.dumps(records, ensure_ascii=False, indent=2))
            self.stdout.write(
                self.style.SUCCESS(f"{area}: {len(records)} record(s) -> {path}")
            )
        self.stdout.write(
            "Next: ingest_pivot --source json --area <area> --path <file> "
            "(inside the backend container)."
        )
