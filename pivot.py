#!/usr/bin/env python3
"""One entry point for the Pivot-RP (ProQuest) grants/conferences flow.

The full interactive process, in order:

    python pivot.py login                       # 1. interactive SSO -> save session
    python pivot.py scrape --topic "agentic ai" # 2. browser scrape -> data/pivot/*.json
    python pivot.py import                       # 3. JSON -> content store (+prune +embed)
    python pivot.py distribute                   # 4. match + rank per user (distribute)

    python pivot.py all --topic "agentic ai"     # steps 2-4 in one go (login separately)

Where each step runs — this matters:

  * **login** and **scrape** open a real Chromium window, so they run **on the
    host** (a machine with a display). One-time host setup:
        uv sync --project web/backend --extra pivot
        uv run --project web/backend playwright install chromium
    The session (``storage_state.json``) lives in the repo, which the container
    bind-mounts, so the scrape/import steps share it. Set ``PIVOT_STORAGE_STATE``
    to relocate it. Sessions expire after ~1h idle — re-run ``login`` then.

  * **import** and **distribute** need Postgres/Redis/the embedder, so they run
    **inside the backend container** (start it first: ``python run.py up``).

Any extra flags are passed straight through to the underlying management command
(e.g. ``python pivot.py import --no-prune``, ``python pivot.py distribute
--user brendondgr --no-llm``). Run ``python pivot.py <step> --help`` via the
management command for the full option list.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COMPOSE_FILE = ROOT / "compose.yaml"
BACKEND_SERVICE = "backend"
PIVOT_DIR = ROOT / "data" / "pivot"

MANAGE = ["uv", "run", "--project", "web/backend", "python", "web/backend/manage.py"]


def _compose() -> list[str]:
    if shutil.which("docker"):
        probe = subprocess.run(
            ["docker", "compose", "version"], capture_output=True, text=True
        )
        if probe.returncode == 0:
            return ["docker", "compose"]
    if shutil.which("docker-compose"):
        return ["docker-compose"]
    sys.exit("Docker Compose not found. Install Docker, then re-run.")


def _backend_running(base: list[str]) -> bool:
    probe = subprocess.run(
        [*base, "ps", "-q", BACKEND_SERVICE], cwd=ROOT, capture_output=True, text=True
    )
    return probe.returncode == 0 and bool(probe.stdout.strip())


def _run_host(manage_args: list[str]) -> int:
    """Run a management command on the host (browser steps: login / scrape)."""
    cmd = [*MANAGE, *manage_args]
    print(f"\n[host] $ {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, cwd=ROOT).returncode


def _run_container(manage_args: list[str]) -> int:
    """Run a management command inside the backend container (DB steps)."""
    base = _compose()
    if not _backend_running(base):
        sys.exit(
            "The backend service is not running. Start the stack first:\n"
            "    python run.py up"
        )
    exec_flags = [] if sys.stdin.isatty() else ["-T"]
    cmd = [*base, "exec", *exec_flags, BACKEND_SERVICE, *MANAGE, *manage_args]
    print(f"\n[container] $ {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, cwd=ROOT).returncode


def _import_files(passthrough: list[str]) -> int:
    """Ingest each scraped JSON file in data/pivot/ into the content store."""
    files = sorted(PIVOT_DIR.glob("pivot_*.json"))
    if not files:
        sys.exit(
            f"No scraped JSON in {PIVOT_DIR} — run 'python pivot.py scrape' first "
            "(or pass --source db/json to ingest_pivot directly)."
        )
    rc = 0
    for path in files:
        # pivot_grants.json -> grants, pivot_conferences.json -> conferences
        area = path.stem.replace("pivot_", "")
        rel = path.relative_to(ROOT)
        rc = _run_container(
            ["ingest_pivot", "--source", "json", "--area", area, "--path", str(rel), *passthrough]
        )
        if rc != 0:
            return rc
    return rc


def main() -> int:
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0

    step, rest = argv[0], argv[1:]

    if step == "login":
        return _run_host(["pivot_login", *rest])
    if step == "scrape":
        return _run_host(["scrape_pivot", *rest])
    if step == "import":
        return _import_files(rest)
    if step == "distribute":
        return _run_container(["run_daily_opportunities", *rest])
    if step == "all":
        # Steps 2-4: scrape (host) -> import (container) -> distribute (container).
        # 'login' is intentionally separate — it needs a human at the browser.
        rc = _run_host(["scrape_pivot", *rest])
        if rc != 0:
            return rc
        rc = _import_files([])
        if rc != 0:
            return rc
        return _run_container(["run_daily_opportunities"])

    sys.exit(
        f"Unknown step {step!r}. Expected one of: login, scrape, import, "
        "distribute, all. See --help."
    )


if __name__ == "__main__":
    raise SystemExit(main())
