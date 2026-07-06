#!/usr/bin/env python3
"""One entry point for the Pivot-RP (ProQuest) grants/conferences flow.

The ONE command — login (only if needed) + the full run, in a single process:

    uv run pivot.py all
        # 0. install Chromium if missing, and open the login window the FIRST
        #    time (or whenever no session is saved) — complete SSO/MFA once
        # 1. scrape every user's watched grants + all conferences
        # 2. de-duplicate + prune expired into the content store, embed new ones
        # 3. recommend/rank the fresh matches to every user

So the very first run logs you in and then does everything; later runs reuse the
saved session and skip straight to the scrape. In a non-interactive shell (cron)
it skips the login prompt and just dedups + recommends the existing corpus, so it
never blocks.

Granular steps (same in-process runner), if you want them separately:

    uv run pivot.py login        # force a fresh interactive SSO -> save session
    uv run pivot.py scrape        # browser scrape -> data/pivot/*.json
    uv run pivot.py import         # data/pivot/*.json -> content store
    uv run pivot.py distribute     # recommend on the existing corpus (no scrape)

Run from the repo root: the root pyproject.toml provides the environment (Chromium
is auto-installed on first scrape — no ``uv sync --extra`` needed). The stack must
be up (``python run.py up``) so ``DATABASE_URL`` resolves. The saved session lives
at ``storage_state.json`` (``PIVOT_STORAGE_STATE`` overrides the path) and expires
after ~1h idle — re-run ``pivot.py login`` when a scrape says it's expired.

Flags pass through: ``all`` / ``distribute`` accept ``--user <name>`` (repeatable),
``--no-llm`` (deterministic scoring), ``--dry-run`` (persist nothing); ``all`` also
takes ``--no-scrape`` (skip login + scrape, just dedup + recommend) and ``--no-prune``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PIVOT_DIR = ROOT / "data" / "pivot"


def _bootstrap_django() -> None:
    """Make this script a Django-aware process (settings from web/backend)."""
    backend = str(ROOT / "web" / "backend")
    if backend not in sys.path:
        sys.path.insert(0, backend)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def _parse(rest: list[str], *, scrape_flags: bool) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="pivot.py", add_help=True)
    ap.add_argument("--user", "-u", action="append", dest="usernames",
                    help="Limit to this user (repeatable). Default: all active users.")
    ap.add_argument("--no-llm", action="store_true",
                    help="Deterministic scoring instead of the language model.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Run the pipeline but persist nothing.")
    ap.add_argument("--concurrency", type=int, default=None,
                    help="Max concurrent LLM scoring calls (default: 12).")
    if scrape_flags:
        ap.add_argument("--no-scrape", action="store_true",
                        help="Skip the browser scrape; dedup + recommend the corpus.")
        ap.add_argument("--no-prune", action="store_true",
                        help="Keep expired grants/conferences instead of deleting them.")
    return ap.parse_args(rest)


def _recommend(rest: list[str], *, ingest: bool) -> int:
    """Run the batch pipeline in-process: (optional scrape+dedup+prune) + recommend."""
    args = _parse(rest, scrape_flags=ingest)
    _bootstrap_django()
    _ensure_migrated()
    if not args.no_llm:
        _fix_llm_host()
    from apps.content.opportunities import run_daily_opportunities_batch
    from apps.content.tasks import select_users

    # The one-command path: before scraping, make sure a browser is installed and
    # a login session exists — logging in interactively only when one is missing.
    if ingest and not getattr(args, "no_scrape", False):
        _prepare_scrape()

    users = select_users(args.usernames)
    print(f"Running for {len(users)} user(s)…", flush=True)
    complete = (lambda _prompt: None) if args.no_llm else None
    batch = run_daily_opportunities_batch(
        users,
        ingest=ingest and not getattr(args, "no_scrape", False),
        prune=not getattr(args, "no_prune", False),
        persist=not args.dry_run,
        concurrency=args.concurrency,
        complete=complete,
        log=lambda m: print(m, flush=True),
    )
    print(json.dumps(batch.as_dict(), indent=2))
    ok = sum(1 for r in batch.results if r.status == "ok")
    new = sum(r.new for r in batch.results)
    print(f"\n[done] {ok}/{len(batch.results)} runs ok, {new} new item(s) surfaced.")
    return 0


def _fix_llm_host() -> None:
    """Make the LLM endpoint reachable from a host run.

    ``LLM_BASE_URL`` is configured for the containers as
    ``http://host.docker.internal:<port>/v1`` — a hostname that only resolves
    inside Docker. ``pivot.py`` runs on the host, where the same vLLM tunnel is at
    ``localhost``. Rewrite it for this process so host runs actually score with the
    model instead of always falling back. The containers' own config is untouched.
    """
    from django.conf import settings

    url = getattr(settings, "LLM_BASE_URL", "") or ""
    if "host.docker.internal" in url:
        settings.LLM_BASE_URL = url.replace("host.docker.internal", "localhost")
        print(
            f"note: LLM endpoint rewritten for host run -> {settings.LLM_BASE_URL}",
            flush=True,
        )


def _ensure_migrated() -> None:
    """Apply any pending database migrations (idempotent; no-op when up to date).

    Guards the exact failure where the running database predates a new migration
    (e.g. a table this feature added does not exist yet), turning a deep ORM
    traceback into a one-line, self-healing step. Safe: it only applies the
    migrations already committed in the repo — the same as running ``migrate``.
    """
    from django.db import DEFAULT_DB_ALIAS, connections
    from django.db.migrations.executor import MigrationExecutor

    executor = MigrationExecutor(connections[DEFAULT_DB_ALIAS])
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    if not plan:
        return
    print(f"Applying {len(plan)} pending database migration(s)…", flush=True)
    from django.core.management import call_command

    call_command("migrate", verbosity=0)


def _ensure_chromium() -> None:
    """Install the Chromium browser Playwright needs (idempotent, fast if present)."""
    import subprocess

    print("Ensuring the Chromium browser is installed (one-time)…", flush=True)
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"], check=False
    )


def _prepare_scrape() -> None:
    """Make the environment scrape-ready: a browser, and a login session.

    Installs Chromium if missing, then — when no saved session exists — opens the
    interactive login so ``pivot.py all`` is a single command (login + run). In a
    non-interactive shell it skips login and lets the run dedup + recommend the
    existing corpus rather than blocking on a prompt.
    """
    from apps.scraper.pivot.common import state_exists

    _ensure_chromium()
    if state_exists():
        return
    if not sys.stdin.isatty():
        print(
            "No saved Pivot session and not an interactive terminal — skipping the "
            "scrape; will de-duplicate + recommend the existing corpus."
        )
        return
    print("No saved Pivot session — opening the login window; complete SSO/MFA…")
    from apps.scraper.pivot.login import login

    login()


def _login() -> int:
    _bootstrap_django()
    from apps.scraper.pivot.common import STATE_PATH, state_exists

    print(f"Session will be saved to: {STATE_PATH}")
    _ensure_chromium()
    from apps.scraper.pivot.login import login

    login()
    return 0 if state_exists() else 1


def _scrape(rest: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="pivot.py scrape")
    ap.add_argument("--topic", action="append", dest="topics", metavar="TEXT",
                    help="Grant search topic (repeatable). Conferences ignore this.")
    ap.add_argument("--area", action="append", choices=["grants", "conferences"],
                    dest="areas", help="Limit to an area (repeatable). Default: both.")
    ap.add_argument("--out", default=str(PIVOT_DIR),
                    help=f"Output directory (default: {PIVOT_DIR}).")
    args = ap.parse_args(rest)

    _bootstrap_django()
    from apps.scraper.pivot.common import state_exists

    if not state_exists():
        sys.exit("No saved session — run 'pivot.py login' first (on a machine "
                 "with a display).")
    from apps.scraper.pivot.scrape import refresh

    areas = tuple(args.areas or ("grants", "conferences"))
    topics = [t for t in (args.topics or []) if t and t.strip()]
    pairs = list(refresh(areas=areas, topics=topics, log=lambda m: print(m, flush=True)))
    if not pairs:
        print("Scrape returned nothing.")
        return 0
    by_area: dict[str, list[dict]] = {}
    for area, rec in pairs:
        by_area.setdefault(area, []).append(rec)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    for area, records in by_area.items():
        path = out_dir / f"pivot_{area}.json"
        path.write_text(json.dumps(records, ensure_ascii=False, indent=2))
        print(f"{area}: {len(records)} record(s) -> {path}")
    return 0


def _import(rest: list[str]) -> int:
    _bootstrap_django()
    _ensure_migrated()
    from apps.scraper.pivot.importer import load_json
    from apps.scraper.pivot.ingest import ingest_pivot

    files = sorted(PIVOT_DIR.glob("pivot_*.json"))
    if not files:
        sys.exit(f"No scraped JSON in {PIVOT_DIR} — run 'pivot.py scrape' first.")
    pairs: list[tuple[str, dict]] = []
    for path in files:
        area = path.stem.replace("pivot_", "")
        pairs.extend(load_json(path, area))
    summary = ingest_pivot(pairs, prune="--no-prune" not in rest,
                           log=lambda m: print(m, flush=True))
    print(json.dumps(summary.as_dict(), indent=2))
    return 0


def main() -> int:
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    step, rest = argv[0], argv[1:]
    if step == "all":
        return _recommend(rest, ingest=True)
    if step == "distribute":
        return _recommend(rest, ingest=False)
    if step == "login":
        return _login()
    if step == "scrape":
        return _scrape(rest)
    if step == "import":
        return _import(rest)
    sys.exit(f"Unknown step {step!r}. Expected: all, login, scrape, import, "
             "distribute. See --help.")


if __name__ == "__main__":
    raise SystemExit(main())
