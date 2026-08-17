"""Refresh the dblp venue registry cache (plan D5a).

One SPARQL POST to ``sparql.dblp.org``, ~8 MB, ~5 s, CC0-licensed — the whole
9,325-venue registry with indexed-proceedings-year counts already aggregated.
The conference collector's resolve stage joins against this cache to assign
``dblp_found`` / ``indexed_years`` and to attach the CORE / CCF rank badges a
conference card displays.

    uv run --project web/backend python web/backend/manage.py refresh_dblp_registry

**Run this on a slow, deliberate schedule — weekly is ample.** Venue longevity
(has this stream published in the last few years) does not move night to
night, so refreshing on the collector's own nightly cadence would spend the
same ~8 MB request six nights out of seven for an unchanged answer. This
command has no schedule of its own; ``manual_all.py``'s
``refresh_conference_registry`` self-throttles by checking the cache file's
mtime and only calls this command once the cache is stale, so the collector's
resolve stage never has to know or care how recently this ran. See
``apps.scraper.collect.conferences.registry.dblp`` for why SPARQL is the
compliant route rather than a preference (``dblp.org/robots.txt`` disallows
the venue search API outright, and its host bans on repeated 429s).

The resolve stage is deliberately offline-only (``RegistryCache`` never opens a
socket), so a missing or stale cache is never fatal to a collection run — it
only means fewer series can be promoted to tier A on evidence until the next
successful refresh here.
"""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.scraper.collect.conferences.registry.dblp import fetch_registry
from apps.scraper.collect.core.http import PoliteClient
from apps.scraper.collect.runner import DEFAULT_ROOT


class Command(BaseCommand):
    help = "Refresh the dblp venue registry cache (one SPARQL POST; weekly cadence)."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--root",
            default=str(DEFAULT_ROOT),
            help=(
                f"Collector data root (default: {DEFAULT_ROOT}); the cache "
                "lands under <root>/registry."
            ),
        )

    def handle(self, *args, **options) -> None:
        root = Path(options["root"])
        registry_dir = root / "registry"
        client = PoliteClient()
        try:
            payload = fetch_registry(client, registry_dir)
        except Exception as exc:  # noqa: BLE001 -- a clean, actionable failure beats a traceback
            raise CommandError(
                f"dblp registry refresh failed: {type(exc).__name__}: {exc}"
            ) from exc

        venues = payload.get("venues", [])
        with_years = sum(1 for v in venues if v.get("n_years"))
        self.stdout.write(
            self.style.SUCCESS(
                f"dblp registry refreshed: {len(venues):,} venue(s) "
                f"({with_years:,} with indexed proceedings) -> {registry_dir}"
            )
        )
