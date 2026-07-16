#!/usr/bin/env python3
"""Run Mylo's language-model recommendation pass over every user's matches.

Where ``manual_all.py`` is the daily *ingest* run (scrape → search → match →
briefing, scoring only that day's brand-new items), this is the on-demand
*re-personalization* run: it takes the top results already stored for every user
in every area (research papers, grants, conferences, fellowships) and re-scores
them through the language model, refreshing each user's Mylo recommendations —
the percent match and the tailored "why it fits you" write-up — with **no**
literature scan and **no** Pivot re-scrape. Then it rewrites each user's Mylo
Report so the daily briefing reflects the freshly-scored recommendations.

Use it when you want Mylo to re-think its recommendations for everyone over the
corpus already in the store — e.g. after tuning the prompts/matcher, after an LLM
outage left feeds on deterministic fallbacks, or just to regenerate the
personalized layer on demand. This is the whole-corpus **replace** pass, so it can
re-score, rewrite, or drop recommendations Mylo already wrote — which is exactly
why the scheduled daily run (``manual_all.py``) never does it and this is a
separate, human-invoked command.

Stages, in order:
    1. Refit all users (backend)   — ``run_refitting``: re-score each user's
       existing top papers/grants/conferences/fellowships through the LLM and
       persist the refreshed Mylo recommendations.
    2. Refresh Mylo Reports (backend) — ``generate_daily_briefing``: rewrite each
       user's cross-category "Mylo Report" over the just-refreshed items (skipped
       on ``--dry-run``, since nothing was persisted to synthesize).

A pre-flight ``llm_check --strict`` gates the run: the whole point is to run the
model, so if the endpoint is unreachable the run aborts before touching anything
rather than re-scoring on deterministic fallbacks. Re-run once the model is back.

Every flag is passed straight through to ``run_refitting`` — the same code path as
``utils/manual/manual_refitting.py`` and any future scheduler. Because each refit
issues a round of LLM calls for every user, cap the run with ``--max`` when
smoke-testing so you don't overwhelm the model host. Any ``--user`` filter also
scopes the report refresh, so the two stages stay in step.

Usage:
    python manual_mylo.py                          # all users, top-10 LLM, refresh reports
    python manual_mylo.py --max 5                  # first 5 active users only
    python manual_mylo.py --user brendondgr        # one user (refit + report)
    python manual_mylo.py --llm-limit all          # send every surfaced item to the model
    python manual_mylo.py --areas papers grants    # a subset of areas
    python manual_mylo.py --dry-run                # refit but persist nothing (no report refresh)
    python manual_mylo.py --help                   # this message

The stack must be up first (``python run.py up``). Requires Docker Compose. This
matches the *existing* corpus, so seed it first (``manual_all.py`` / the daily
jobs) if the store is empty.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "utils" / "manual"))
from _runner import ensure_ready, run_manage  # noqa: E402


def _user_flags(argv: list[str]) -> list[str]:
    """Just the ``--user``/``-u`` selectors from ``argv``, to scope stage 2.

    ``run_refitting`` and ``generate_daily_briefing`` both take repeatable
    ``--user`` (nothing else in common), so forwarding only those keeps the report
    refresh on the same set of users the refit ran for, ignoring refit-only flags
    (``--max``, ``--areas``, ``--llm-limit``, ``--no-llm``, ``--dry-run``).
    """
    out: list[str] = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--user", "-u") and i + 1 < len(argv):
            out += [arg, argv[i + 1]]
            i += 2
        elif arg.startswith("--user="):
            out.append(arg)
            i += 1
        else:
            i += 1
    return out


def preflight_llm(base: list[str]) -> bool:
    """True if the LLM endpoint is reachable; False (after a note) otherwise.

    Runs ``llm_check --strict`` in the backend container. Refitting is a pure LLM
    re-score, so an unreachable model means there is nothing worth doing — abort
    before persisting anything rather than overwriting real recommendations with
    deterministic fallbacks.
    """
    print("\n=== Pre-flight · Checking the LLM endpoint… ===", flush=True)
    return run_manage("llm_check", ["--strict"], intro=None, base=base) == 0


def main() -> int:
    argv = sys.argv[1:]
    if any(arg in ("-h", "--help") for arg in argv):
        print(__doc__)
        return 0

    # Resolve Compose and confirm the stack is up once, up front, so both stages
    # reuse it and we fail fast if the backend is down.
    base = ensure_ready()

    if not preflight_llm(base):
        sys.exit(
            "\nThe LLM endpoint is unreachable, so Mylo's recommendation pass was "
            "not run — nothing was changed. Check the LLM server / `LLM_BASE_URL` "
            "and re-run `manual_mylo.py` once it is back."
        )

    dry_run = "--dry-run" in argv
    total = 1 if dry_run else 2

    # Stage 1 — refit: run the model across every user's existing matches.
    print(
        f"\n=== 1/{total} · Running Mylo across every user's matches (refit)… ===",
        flush=True,
    )
    code = run_manage(
        "run_refitting",
        argv,
        intro="Re-scoring every user's recommendations through the language model…",
        base=base,
    )
    if code != 0:
        print(
            f"\nRefit stage exited with code {code}; stopping.",
            file=sys.stderr,
            flush=True,
        )
        return code

    # Stage 2 — refresh the Mylo Report over the just-refreshed items. Skipped on a
    # dry run, where stage 1 persisted nothing to synthesize a fresh report from.
    if dry_run:
        print(
            "\n(--dry-run: nothing was persisted, so the Mylo Report refresh is "
            "skipped.)",
            flush=True,
        )
        print("\nDone: refit dry run complete for the selected users.", flush=True)
        return 0

    print(f"\n=== 2/{total} · Refreshing each user's Mylo Report… ===", flush=True)
    code = run_manage(
        "generate_daily_briefing",
        _user_flags(argv),
        intro="Rewriting each user's Mylo Report over the refreshed items…",
        base=base,
    )
    if code != 0:
        print(
            f"\nReport refresh exited with code {code}. The refit itself succeeded; "
            "re-run to retry just the report with `generate_daily_briefing`.",
            file=sys.stderr,
            flush=True,
        )
        return code

    print(
        "\nDone: Mylo re-scored every selected user's matches and refreshed their "
        "reports.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
