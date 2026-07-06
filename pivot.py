#!/usr/bin/env python3
"""One entry point for the Pivot-RP (ProQuest) grants/conferences flow.

The headline command does the whole thing in a single process:

    uv run pivot.py all
        # 1. scrape every user's watched grants + all conferences (best-effort)
        # 2. de-duplicate + prune expired into the content store, embed new ones
        # 3. recommend/rank the fresh matches to every user

Granular steps (same in-process runner):

    uv run pivot.py login        # interactive SSO -> save session
    uv run pivot.py scrape        # browser scrape -> data/pivot/*.json
    uv run pivot.py import         # data/pivot/*.json -> content store
    uv run pivot.py distribute     # recommend on the existing corpus

(Run from the repo root: the root pyproject.toml provides the environment. The
stack must be up — ``python run.py up`` — so ``DATABASE_URL`` resolves.)

Flags pass through: ``all`` / ``distribute`` accept ``--user <name>`` (repeatable),
``--no-llm`` (deterministic scoring), ``--dry-run`` (persist nothing); ``all`` also
takes ``--no-scrape`` (skip the browser step, just dedup + recommend the existing
corpus) and ``--no-prune``.

What the environment needs:

  * **Scraping** (``login`` / ``scrape``, and the scrape inside ``all``) opens a
    real Chromium window, so run it where there's a display, with the browser
    extra installed once:
        uv sync --project web/backend --extra pivot
        uv run --project web/backend playwright install chromium
    The session (``storage_state.json``, path overridable via
    ``PIVOT_STORAGE_STATE``) is reused so you never re-enter a password.
  * **De-dup + recommend** need Postgres/pgvector + the embeddings extra, so
    ``DATABASE_URL`` must point at the running database (``python run.py up``).

``all`` is best-effort about scraping: with no session or browser it logs, skips
the scrape, and still dedups + recommends whatever is already stored — so it never
hard-fails a nightly run. (``login`` is deliberately its own step: a human has to
complete SSO/MFA at the browser.)
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
    from apps.content.opportunities import run_daily_opportunities_batch
    from apps.content.tasks import select_users

    users = select_users(args.usernames)
    print(f"Running for {len(users)} user(s)…", flush=True)
    complete = (lambda _prompt: None) if args.no_llm else None
    batch = run_daily_opportunities_batch(
        users,
        ingest=ingest and not getattr(args, "no_scrape", False),
        prune=not getattr(args, "no_prune", False),
        persist=not args.dry_run,
        complete=complete,
        log=lambda m: print(m, flush=True),
    )
    print(json.dumps(batch.as_dict(), indent=2))
    ok = sum(1 for r in batch.results if r.status == "ok")
    new = sum(r.new for r in batch.results)
    print(f"\n[done] {ok}/{len(batch.results)} runs ok, {new} new item(s) surfaced.")
    return 0


def _login() -> int:
    _bootstrap_django()
    from apps.scraper.pivot.common import STATE_PATH, state_exists

    print(f"Session will be saved to: {STATE_PATH}")
    try:
        from apps.scraper.pivot.login import login
    except Exception as exc:  # pragma: no cover - import guard
        sys.exit(
            "Could not start the browser. Install the extra first:\n"
            "  uv sync --project web/backend --extra pivot\n"
            "  uv run --project web/backend playwright install chromium\n"
            f"(error: {exc})"
        )
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
