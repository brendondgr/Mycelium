#!/usr/bin/env python3
"""Create (or promote) a Mycelium superuser admin. `make admin NAME=<user>` runs this.

A thin wrapper over the ``create_admin`` management command so an operator can mint
the first admin without knowing the ``uv``/``manage.py`` incantation. It runs the
command inside the running ``backend`` container (via Docker Compose) so it uses
the real Postgres and the container's environment — where ``ADMIN_USER_PASS`` is
supplied from ``.env`` (see ``compose.yaml``'s ``env_file``). The password is read
only from that variable; it is never a command-line argument and never printed.

Usage:
    python ops/setup/create_admin.py <username>
    python ops/setup/create_admin.py alice --email alice@example.org --first-name Alice
    python ops/setup/create_admin.py --help

Set the password first in your repo-root ``.env``:
    ADMIN_USER_PASS=your-strong-password

The stack must be up (``mycelium start``); this uses the same Docker Compose
path as the other manual runners. Re-running is safe — an existing user is
promoted to staff+superuser and their password reset to the current value.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nightly"))
from _runner import ensure_ready, run_manage  # noqa: E402


def main() -> int:
    argv = sys.argv[1:]
    if any(arg in ("-h", "--help") for arg in argv):
        print(__doc__)
        return 0
    if not argv or argv[0].startswith("-"):
        print(
            "A username is required. Example:\n"
            "    python ops/setup/create_admin.py alice\n"
            "Set ADMIN_USER_PASS in your .env first. See --help for details.",
            file=sys.stderr,
        )
        return 2

    base = ensure_ready()
    return run_manage(
        "create_admin",
        argv,
        intro="Creating/promoting the superuser admin (password from $ADMIN_USER_PASS)…",
        base=base,
    )


if __name__ == "__main__":
    raise SystemExit(main())
