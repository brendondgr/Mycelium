#!/usr/bin/env python3
"""Run the full manual recommendation flow, in order, for all users.

Scrape every source, then recommend, then refit — one stage after another,
synchronously, for *all* active users, against the running Docker stack.

Stages, in order:
    1. Scrape opportunity sources (host)   — ``uv run pivot.py`` login + scrape +
       import: pull fresh grants, conferences, and fellowships from Pivot-RP / the
       Illinois fellowship site into the shared content store and embed them. When
       there is no saved Pivot session, this stage first opens the interactive
       login window (SSO/MFA) to establish one, then scrapes. In a non-interactive
       shell it cannot prompt, so it skips the scrape and the later stages match
       the existing corpus.
    2. Search research papers (backend)    — ``run_daily_suggestions``: scan the
       literature sources (OpenAlex / PubMed / SemanticScholar), embed, and
       recommend papers. The paper sources are scraped here, as part of the
       search — that is why stage 1 only has to add the opportunity sources.
    3. Match opportunities (backend)       — ``run_daily_opportunities``: score
       the grants / conferences / fellowships now in the store for every user.
    4. Refit personalization (backend)     — ``run_refitting``: re-score every
       area's stored top results through the LLM for every user.

The scrape stage runs on the host because Playwright/Chromium and the saved Pivot
session live there, not in the backend container (the container has no Playwright,
which is why its own opportunity ingest silently skips the scrape). Host and
container share the same Postgres, so a host-side import is visible to the
backend stages that follow. Every part of the scrape stage — login, scrape,
import — is non-fatal: a declined login, an expired session, or no ``uv`` just
warns and lets the run continue, recommending over whatever corpus already
exists.

Each stage runs for all users with default settings; this script takes no
pass-through flags on purpose, so "scrape and recommend everything for everyone"
stays one predictable command. For a targeted run, call the per-stage scripts in
utils/manual/ or ``uv run pivot.py`` directly.

Usage:
    python manual_all.py        # scrape → search → match → refit, all users
    python manual_all.py --help # this message

The stack must be up first (``python run.py up``). Requires Docker Compose, plus
``uv`` on PATH; the scrape stage will log in for you when no Pivot session exists,
as long as it is run from an interactive terminal with a display for SSO/MFA.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "utils" / "manual"))
from _runner import ensure_ready, have_uv, run_host, run_manage  # noqa: E402

# The backend recommend/refit stages, in order, run inside the container. The
# scrape stage (stage 1) is handled separately because it runs on the host.
CONTAINER_STAGES = [
    ("run_daily_suggestions", "Searching research papers for all users…"),
    ("run_daily_opportunities", "Matching grants/conferences/fellowships for all users…"),
    ("run_refitting", "Refitting the personalized layer for all users…"),
]


def pivot_session_exists() -> bool:
    """True if a saved Pivot SSO session is present on the host.

    Reuses the scraper's own ``state_exists()`` (which honors ``PIVOT_STORAGE_STATE``)
    so this check can never drift from where the scraper actually looks. That module
    is pure-stdlib, so importing it needs no Django setup. If it can't be imported for
    any reason we report "no session" — the caller then tries to log in, which is the
    safe direction.
    """
    backend = str(Path(__file__).resolve().parent / "web" / "backend")
    if backend not in sys.path:
        sys.path.insert(0, backend)
    try:
        from apps.scraper.pivot.common import state_exists
    except Exception:
        return False
    return state_exists()


def scrape_opportunities() -> None:
    """Log in if needed, then scrape grants/conferences/fellowships (host, non-fatal).

    Runs the host Pivot pipeline: ``uv run pivot.py login`` first when no session is
    saved, then ``uv run pivot.py scrape`` (browser scrape to ``data/pivot/*.json``)
    and ``uv run pivot.py import`` (dedup + prune + embed into the shared store).
    Every step is logged and swallowed on failure: the daily run should still
    recommend over the existing corpus, not abort, when the scrape can't run.
    """
    if not have_uv():
        print(
            "note: `uv` is not on PATH — skipping the opportunity scrape; the later "
            "stages will match the corpus already in the store.",
            flush=True,
        )
        return

    # No saved session → log in first so the scrape can actually reach the grant /
    # conference sources. Login is interactive (SSO/MFA in a browser); in a
    # non-interactive shell we cannot prompt, so we skip and match the existing corpus.
    if not pivot_session_exists():
        if not sys.stdin.isatty():
            print(
                "note: no saved Pivot session and not an interactive terminal — cannot "
                "log in unattended. Skipping the scrape; run `uv run pivot.py login` "
                "once from a terminal with a display. The later stages will match the "
                "existing corpus.",
                flush=True,
            )
            return
        print(
            "No saved Pivot session — opening the login window; complete SSO/MFA to "
            "continue…",
            flush=True,
        )
        if run_host(["uv", "run", "pivot.py", "login"]) != 0 or not pivot_session_exists():
            print(
                "\nnote: Pivot login did not complete; skipping the scrape. The later "
                "stages will match the existing corpus.",
                flush=True,
            )
            return

    if run_host(["uv", "run", "pivot.py", "scrape"]) != 0:
        print(
            "\nnote: the Pivot scrape did not complete — the session may have expired. "
            "Re-run `uv run pivot.py login`. Skipping import; the later stages will "
            "match the existing corpus.",
            flush=True,
        )
        return

    if run_host(["uv", "run", "pivot.py", "import"]) != 0:
        print(
            "\nnote: importing the scraped opportunities failed; the later stages will "
            "match whatever is already in the store.",
            flush=True,
        )


def main() -> int:
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        print(__doc__)
        return 0

    if sys.argv[1:]:
        sys.exit(
            "manual_all.py takes no arguments; it always scrapes every source and runs "
            "every stage for all users.\nFor a targeted run, call the per-stage scripts "
            "in utils/manual/ or `uv run pivot.py` directly."
        )

    # Resolve Compose and confirm the stack is up once, up front, so we don't get
    # partway through the run before discovering the backend is down.
    base = ensure_ready()
    total = 1 + len(CONTAINER_STAGES)

    # Stage 1 — scrape the opportunity sources on the host (non-fatal).
    print(
        f"\n=== 1/{total} · Scraping opportunity sources (grants, conferences, fellowships)… ===",
        flush=True,
    )
    scrape_opportunities()

    # Stages 2..N — recommend and refit inside the backend container.
    for offset, (command, intro) in enumerate(CONTAINER_STAGES):
        step = 2 + offset
        print(f"\n=== {step}/{total} · {intro} ===", flush=True)
        code = run_manage(command, intro=None, base=base)
        if code != 0:
            print(
                f"\nStage '{command}' exited with code {code}; stopping before the "
                "remaining stages.",
                file=sys.stderr,
                flush=True,
            )
            return code

    print("\nAll stages completed: scrape → search → match → refit, for all users.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
