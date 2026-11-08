#!/usr/bin/env python3
"""Host-side Illinois Fellowship Finder scrape + import (the one browser source).

Grants and conferences collect entirely inside the backend container now, via
the open-source opportunity collector (``manage.py collect_opportunities`` —
pure HTTP, no login, no session; see
``docs/plans/open-opportunity-collector.md`` D6). Fellowships are the one
opportunity source left that needs a real browser: the Illinois Graduate
College Fellowship Finder is a Blazor Server app, so its detail pages only
render inside an actual page, not a plain HTTP GET.

Split out of the retired ``pivot.py`` (plan Phase 6 — the deletion of
Pivot-RP): this script keeps exactly ``pivot.py``'s ``scrape``/``import`` shape
for the one source that survives it, so ``manual_all.py``'s stage 1 needed no
host-orchestration rewrite beyond the script name. Unlike Pivot-RP's own
grant/conference scrape, this needs no saved SSO session at all — the listing
and detail pages are public.

    uv run tools/retrieval/host/scrape_fellowships.py scrape   # browser scrape -> data/pivot/pivot_fellowships.json
    uv run tools/retrieval/host/scrape_fellowships.py import   # data/pivot/pivot_fellowships.json -> content store

Run from the repo root: the root pyproject.toml provides the environment
(Chromium is auto-installed on first scrape — no ``uv sync --extra`` needed).
The stack must be up (``mycelium start``) so ``DATABASE_URL`` resolves.
Pruning is **not** done here — ``manual_all.py``'s dedicated
``prune_opportunities`` container stage is the one place every opportunity
type's expiry runs, so a moved deadline is always seen by the reminder tick
before its item can be deleted (see that script's ``CONTAINER_STAGES`` note).

The scraped JSON lands in ``data/pivot/`` — the directory name is a leftover
of Pivot-RP's own layout (``manual_all.py``'s ``PIVOT_DIR``/
``_purge_stale_pivot_json`` already depend on this exact path to clean up
stale grant/conference JSON from before this migration), not a sign that
Pivot itself survives here.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PIVOT_DIR = ROOT / "data" / "pivot"
OUT_PATH = PIVOT_DIR / "pivot_fellowships.json"


def _bootstrap_django() -> None:
    """Make this script a Django-aware process (settings from web/backend)."""
    backend = str(ROOT / "web" / "backend")
    if backend not in sys.path:
        sys.path.insert(0, backend)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def _ensure_chromium() -> None:
    """Install the Chromium browser Playwright needs (idempotent, fast if present)."""
    import subprocess

    print("Ensuring the Chromium browser is installed (one-time)…", flush=True)
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"], check=False
    )


def _ensure_migrated() -> None:
    """Apply any pending database migrations (idempotent; no-op when up to date)."""
    from django.db import DEFAULT_DB_ALIAS, connections
    from django.db.migrations.executor import MigrationExecutor

    executor = MigrationExecutor(connections[DEFAULT_DB_ALIAS])
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    if not plan:
        return
    print(f"Applying {len(plan)} pending database migration(s)…", flush=True)
    from django.core.management import call_command

    call_command("migrate", verbosity=0)


def _scrape() -> int:
    _bootstrap_django()
    _ensure_chromium()
    from tools.retrieval.fellowships import scrape_fellowships

    records = scrape_fellowships(log=lambda m: print(m, flush=True))
    if not records:
        print("Scrape returned nothing.")
        return 0
    PIVOT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(records, ensure_ascii=False, indent=2))
    print(f"fellowships: {len(records)} record(s) -> {OUT_PATH}")
    return 0


def _import() -> int:
    _bootstrap_django()
    _ensure_migrated()
    if not OUT_PATH.exists():
        sys.exit(
            f"No scraped JSON at {OUT_PATH} — run 'scrape_fellowships.py scrape' first."
        )
    records = json.loads(OUT_PATH.read_text())
    from tools.retrieval.fellowships.ingest import ingest_fellowships

    # No prune here on purpose — see the module docstring: pruning is
    # ``manual_all.py``'s dedicated later stage, not this one.
    summary = ingest_fellowships(records, log=lambda m: print(m, flush=True))
    print(json.dumps(summary.as_dict(), indent=2))
    return 0


def main() -> int:
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    step = argv[0]
    if step == "scrape":
        return _scrape()
    if step == "import":
        return _import()
    sys.exit(f"Unknown step {step!r}. Expected: scrape, import. See --help.")


if __name__ == "__main__":
    raise SystemExit(main())
