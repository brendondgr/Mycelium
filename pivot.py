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
                                 #   add --transfer to rsync the saved session to
                                 #   a remote host (default: zeus:/home/bdg20b/
                                 #   Projects/Mycelium) so you can run the manual
                                 #   process there with fresh credentials
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


def _remote_target(remote_host: str, remote_dir: str) -> str:
    """Where the saved session should land on the remote host.

    We mirror the file's path *relative to the repo root* under the remote
    project directory, so the remote ``pivot.py`` finds it at its own default
    ``STATE_PATH`` with no ``PIVOT_STORAGE_STATE`` needed. If the session lives
    outside the repo (a custom ``PIVOT_STORAGE_STATE``), we fall back to dropping
    it by basename directly in the remote project directory.
    """
    from apps.scraper.pivot.common import STATE_PATH

    remote_dir = remote_dir.rstrip("/")
    try:
        rel = STATE_PATH.resolve().relative_to(ROOT)
        remote_path = f"{remote_dir}/{rel.as_posix()}"
    except ValueError:
        remote_path = f"{remote_dir}/{STATE_PATH.name}"
    return f"{remote_host}:{remote_path}"


def _transfer_state(remote_host: str, remote_dir: str) -> int:
    """rsync the saved session to the remote host, creating parent dirs first."""
    import shlex
    import subprocess

    from apps.scraper.pivot.common import STATE_PATH, state_exists

    if not state_exists():
        print("No saved session to transfer — did the login complete?")
        return 1

    target = _remote_target(remote_host, remote_dir)
    # Split "host:/path/to/storage_state.json" back into host + remote dir so we
    # can pre-create the destination directory (rsync won't make deep parents).
    host, _, remote_path = target.partition(":")
    remote_parent = os.path.dirname(remote_path)

    print(f"Ensuring remote directory exists: {host}:{remote_parent}")
    mk = subprocess.run(
        ["ssh", host, f"mkdir -p {shlex.quote(remote_parent)}"], check=False
    )
    if mk.returncode != 0:
        print(f"[!] Could not create remote directory (ssh exit {mk.returncode}).")
        return mk.returncode

    print(f"Transferring session -> {target}")
    rc = subprocess.run(
        ["rsync", "-avz", str(STATE_PATH), target], check=False
    ).returncode
    if rc == 0:
        print(f"[ok] Session is now on {host} — run the manual process there.")
    else:
        print(f"[!] rsync failed (exit {rc}).")
    return rc


def _login(rest: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="pivot.py login")
    ap.add_argument("--transfer", action="store_true",
                    help="After saving, rsync the session to the remote host.")
    ap.add_argument("--remote-host", default="zeus",
                    help="Remote host to transfer to (default: zeus).")
    ap.add_argument("--remote-dir", default="/home/bdg20b/Projects/Mycelium",
                    help="Remote project directory (default: /home/bdg20b/Projects/Mycelium).")
    args = ap.parse_args(rest)

    _bootstrap_django()
    from apps.scraper.pivot.common import STATE_PATH, state_exists

    print(f"Session will be saved to: {STATE_PATH}")
    _ensure_chromium()
    from apps.scraper.pivot.login import login

    login()
    if not state_exists():
        return 1
    if args.transfer:
        return _transfer_state(args.remote_host, args.remote_dir)
    return 0


def _scrape(rest: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="pivot.py scrape")
    ap.add_argument("--topic", action="append", dest="topics", metavar="TEXT",
                    help="Grant search topic (repeatable). Conferences/fellowships ignore this.")
    ap.add_argument("--area", action="append",
                    choices=["grants", "conferences", "fellowships"],
                    dest="areas",
                    help="Limit to an area (repeatable). Default: all three.")
    ap.add_argument("--out", default=str(PIVOT_DIR),
                    help=f"Output directory (default: {PIVOT_DIR}).")
    args = ap.parse_args(rest)

    _bootstrap_django()

    areas = tuple(args.areas or ("grants", "conferences", "fellowships"))
    pivot_areas = [a for a in areas if a in ("grants", "conferences")]

    if pivot_areas:
        from apps.scraper.pivot.common import state_exists

        if not state_exists():
            if set(areas) == {"fellowships"}:
                pass  # public site only — no session needed
            else:
                sys.exit("No saved session — run 'pivot.py login' first (on a machine "
                         "with a display). Pass --area fellowships to scrape only the "
                         "public fellowship site without a session.")

    from apps.scraper.pivot.scrape import refresh

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

    # Known area -> expected file stem mapping.
    # Also check for a pivot_fellowships.json from a scrape run, plus the tool's
    # fellowships.json (same record shape, area inferred from the stem/argument).
    _AREA_FILES = {
        "grants": PIVOT_DIR / "pivot_grants.json",
        "conferences": PIVOT_DIR / "pivot_conferences.json",
        "fellowships": PIVOT_DIR / "pivot_fellowships.json",
    }

    files = sorted(PIVOT_DIR.glob("pivot_*.json"))
    if not files:
        sys.exit(f"No scraped JSON in {PIVOT_DIR} — run 'pivot.py scrape' first.")
    pairs: list[tuple[str, dict]] = []
    for path in files:
        stem = path.stem  # e.g. "pivot_grants"
        area = stem.replace("pivot_", "")
        try:
            pairs.extend(load_json(path, area))
        except ValueError:
            # area not recognised (e.g. a stale file with an unexpected name) — skip
            print(f"warning: skipping {path.name} (unrecognised area {area!r})")
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
        return _login(rest)
    if step == "scrape":
        return _scrape(rest)
    if step == "import":
        return _import(rest)
    sys.exit(f"Unknown step {step!r}. Expected: all, login, scrape, import, "
             "distribute. See --help.")


if __name__ == "__main__":
    raise SystemExit(main())
