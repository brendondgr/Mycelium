#!/usr/bin/env python3
"""Run the full Mycelium stack from the repository root.

Everything (Nginx gateway, Astro landing, Next.js app, Django backend, Celery
worker, Postgres, Redis, Neo4j, MinIO) is defined in ``compose.yaml``. This
script wraps Docker Compose so the whole stack can be (re)started in the
background with one command.

Default behaviour (no arguments): if anything is already running, stop it, then
start the full stack detached (in the background).

Usage:
    python run.py            # restart everything, detached (default)
    python run.py up         # start everything, detached
    python run.py down       # stop everything
    python run.py restart    # stop then start, detached
    python run.py logs       # follow logs of the running stack (Ctrl-C to exit)
    python run.py status     # show service status
    python run.py migrate    # apply pending database migrations now
    python run.py pending    # list migrations not yet applied (changes nothing)

Options:
    --build                  # rebuild images before starting
    -h, --help               # show this help
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COMPOSE_FILE = ROOT / "compose.yaml"

# App/gateway URLs worth surfacing after the stack comes up.
URLS = [
    ("Gateway (nginx)", "http://localhost:11050"),
    ("Next.js app", "http://localhost:11250"),
    ("Astro landing", "http://localhost:11150"),
    ("Django API", "http://localhost:11350/api/health/"),
    ("MinIO console", "http://localhost:11950"),
    ("Neo4j browser", "http://localhost:11650"),
]


def compose_cmd() -> list[str]:
    """Return the available Docker Compose invocation, or exit with guidance."""
    if shutil.which("docker"):
        # Prefer the v2 plugin form: `docker compose`.
        probe = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            text=True,
        )
        if probe.returncode == 0:
            return ["docker", "compose"]
    if shutil.which("docker-compose"):
        return ["docker-compose"]
    sys.exit(
        "Docker Compose was not found. Install Docker Desktop or the Docker "
        "Compose plugin, then re-run this script."
    )


def run(cmd: list[str]) -> int:
    """Run a command rooted at the repo, streaming its output."""
    print(f"\n$ {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, cwd=ROOT).returncode


def down(base: list[str]) -> int:
    return run([*base, "down", "--remove-orphans"])


def up(base: list[str], build: bool) -> int:
    cmd = [*base, "up", "-d"]
    if build:
        cmd.append("--build")
    return run(cmd)


#: The backend's own ``manage.py`` invocation, as it runs inside the container.
MANAGE = [
    "exec",
    "-T",
    "backend",
    "uv",
    "run",
    "--project",
    "web/backend",
    "python",
    "web/backend/manage.py",
]


def migrate(base: list[str]) -> int:
    """Apply pending migrations against the running stack.

    The backend applies migrations in its *start command*, so a container that is
    already up keeps serving the schema it started with. Code arrives by bind
    mount rather than by image, so `git pull` on the host swaps the code under a
    running backend without restarting it — new code, old schema, and the mismatch
    only surfaces when something touches the new table.

    This is the explicit form of the fix; ``python run.py restart`` is the other,
    since restarting re-runs the start command.
    """
    return run([*base, *MANAGE, "migrate", "--noinput"])


def pending(base: list[str]) -> int:
    """Show the migrations this database has not applied yet. Read-only."""
    return run([*base, *MANAGE, "showmigrations", "--plan"])


def print_urls(base: list[str]) -> None:
    print("\nStack is starting in the background. Endpoints:")
    for name, url in URLS:
        print(f"  - {name:<18} {url}")
    print(f"\nFollow logs:  python {Path(__file__).name} logs")
    print(f"Stop stack:   python {Path(__file__).name} down")


def main() -> int:
    if not COMPOSE_FILE.exists():
        sys.exit(f"compose.yaml not found at {COMPOSE_FILE}. Run this from the repo root.")

    parser = argparse.ArgumentParser(
        description="Run the full Mycelium stack from the repo root.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "action",
        nargs="?",
        default="restart",
        choices=["restart", "up", "down", "logs", "status", "migrate", "pending"],
        help="What to do (default: restart — stop if running, then start detached).",
    )
    parser.add_argument(
        "--build",
        action="store_true",
        help="Rebuild images before starting.",
    )
    args = parser.parse_args()

    base = compose_cmd()

    if args.action == "down":
        return down(base)

    if args.action == "logs":
        return run([*base, "logs", "-f", "--tail", "100"])

    if args.action == "status":
        return run([*base, "ps"])

    if args.action == "migrate":
        return migrate(base)

    if args.action == "pending":
        return pending(base)

    if args.action == "up":
        code = up(base, args.build)
        if code == 0:
            print_urls(base)
        return code

    # Default: restart — stop anything running, then start detached.
    down(base)  # best-effort; safe even if nothing is up
    code = up(base, args.build)
    if code == 0:
        print_urls(base)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
