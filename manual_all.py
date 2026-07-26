#!/usr/bin/env python3
"""Run the full manual recommendation flow, in order, for all users.

Scrape every source, then recommend, then write each user's daily briefing —
one stage after another, synchronously, for *all* active users, against the
running Docker stack. This is what the host ``mylo-daily.timer`` runs once a
day (it replaced the in-container Celery Beat daily schedules, which could not
run the host-only Pivot scrape).

Stages, in order:
    1. Scrape opportunity sources (host)   — ``uv run pivot.py`` login + scrape +
       import: pull fresh grants, conferences, and fellowships from Pivot-RP / the
       Illinois fellowship site into the shared content store and embed them. When
       there is no saved Pivot session, this stage first opens the interactive
       login window (SSO/MFA) to establish one, then scrapes. In a non-interactive
       shell it cannot prompt, so it skips the scrape and *reports to Discord that a
       manual login is needed*, then the later stages match the existing corpus.
    2. Search research papers (backend)    — ``run_daily_suggestions``: scan the
       literature sources (OpenAlex / PubMed / SemanticScholar), embed, and
       recommend papers. The paper sources are scraped here, as part of the
       search — that is why stage 1 only has to add the opportunity sources.
    3. Match opportunities (backend)       — ``run_daily_opportunities``: score
       only the grants / conferences / fellowships that arrived today for every
       user and append the passers to each accumulating feed.
    4. Write daily briefings (backend)     — ``generate_daily_briefing``: the
       cross-category "Mylo Report" synthesis for every user **and every entitled
       lab** (LLM with a deterministic fallback). Like the summary itself, this is
       a per-run *replace* — it re-describes the day's matches, never rewrites the
       stored recommendations — so it stays consistent with the append-only rule.
    5. Send daily Discord reports (backend) — ``send_daily_discord_reports``: DM
       each linked, entitled, opted-in user their day as a PDF (the written report
       plus the top-25 papers and top-25 grants/fellowships/conferences and a full
       appendix). Best-effort: an unreachable DM or Discord outage is counted, never
       fatal, so it can safely be the last stage.

Deliberately **no refit stage**: the daily run only scores that day's *new*
items and appends them. Mylo's already-written recommendations are never
re-scored, rewritten, or dropped by the daily run — an item stays in the feed
until its deadline/event date passes and the ingest prune deletes it.
Refitting (``run_refitting`` / ``utils/manual/manual_refitting.py``) is the
explicit whole-corpus *replace* pass, reserved for sign-up and profile edits.

A pre-flight ``llm_check --strict`` gates the whole run: the pipeline depends on
the LLM for paper rankings, opportunity scoring, and briefings, so if the
endpoint is unreachable the run is skipped entirely (nothing scraped, matched, or
briefed) rather than filling the feeds with deterministic fallbacks. It retries
on the next scheduled run.

Observability: every notable condition is posted to Mylo's Discord error channel
via :mod:`mylo.reporting` (a stdlib-only REST poster that never raises) — a
needed Pivot re-login, an unreachable LLM (the run is skipped), a stage that
exited non-zero, and a short "run complete" summary. The run also writes its
outcome to ``data/logs/mylo-last-run.json`` for the bot's ``/mylo lastrun``.

The scrape stage runs on the host because Playwright/Chromium and the saved Pivot
session live there, not in the backend container (the container has no Playwright,
which is why its own opportunity ingest silently skips the scrape). Host and
container share the same Postgres, so a host-side import is visible to the
backend stages that follow. Every part of the scrape stage — login, scrape,
import — is non-fatal: a declined login, an expired session, or no ``uv`` just
warns (and reports) and lets the run continue, recommending over whatever corpus
already exists.

Each stage runs for all users with default settings; this script takes no
pass-through flags on purpose, so "scrape and recommend everything for everyone"
stays one predictable command. For a targeted run, call the per-stage scripts in
utils/manual/ or ``uv run pivot.py`` directly.

Usage:
    python manual_all.py        # scrape → search → match → briefing
    python manual_all.py --help # this message

The stack must be up first (``python run.py up``). Requires Docker Compose, plus
``uv`` on PATH; the scrape stage will log in for you when no Pivot session exists,
as long as it is run from an interactive terminal with a display for SSO/MFA.
"""

from __future__ import annotations

import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "utils" / "manual"))
from _runner import ensure_ready, have_uv, run_host, run_manage  # noqa: E402

# The Discord error reporter and the shared run-state writer are optional
# plumbing: if they can't be imported for any reason, the daily run must still
# complete. Every reporter call goes through ``_notify`` which no-ops when the
# reporter is unavailable; ``write_run_state`` is guarded the same way.
try:  # pragma: no cover - trivial import guard
    from mylo import reporting
    from mylo.runstate import write_run_state
except Exception:  # noqa: BLE001
    reporting = None  # type: ignore[assignment]
    write_run_state = None  # type: ignore[assignment]

HOST = socket.gethostname()
ROOT = Path(__file__).resolve().parent

# The backend recommend/briefing stages, in order, run inside the container.
# The scrape stage (stage 1) is handled separately on the host. There is no
# refit stage here on purpose — the daily run must never rewrite or drop the
# recommendations Mylo already wrote (refit is the on-demand replace pass for
# sign-up / profile edits).
#
# Ordering matters for reminders (R2): opportunities ingest with ``--no-prune`` so
# the ContentDeadline projection is rebuilt but nothing is deleted yet, then the
# reminder tick fires against live deadlines, then a separate prune stage deletes
# expired items. A deadline that moved earlier into the past is therefore always
# seen by the tick before its item can be pruned out from under a live reminder.
# Each entry is (command, passthrough_args, intro).
CONTAINER_STAGES = [
    ("run_daily_suggestions", [], "Searching research papers for all users…"),
    (
        "run_daily_opportunities",
        ["--no-prune"],
        "Matching grants/conferences/fellowships for all users…",
    ),
    ("run_reminder_tick", [], "Firing due deadline reminders…"),
    ("prune_opportunities", [], "Pruning expired opportunities…"),
    ("generate_daily_briefing", [], "Writing each user's and lab's daily briefing…"),
    (
        "send_daily_discord_reports",
        [],
        "DMing each linked user their daily PDF report…",
    ),
    # After the briefings, and last alongside the personal report: both only queue
    # messages, so a failure here costs a day's post rather than the day's data.
    (
        "send_lab_digests",
        [],
        "Posting each lab's digest to its Discord updates channel…",
    ),
]


def _notify(kind: str, title: str, body: str = "", **kwargs) -> None:
    """Post to the Discord error channel, tolerating a missing/broken reporter."""
    if reporting is None:
        return
    fn = {
        "error": reporting.report_error,
        "warn": reporting.report_warning,
        "info": reporting.report_info,
    }.get(kind)
    if fn is None:
        return
    try:
        fn(title, body, **kwargs)
    except Exception:  # noqa: BLE001 - reporting must never break the run
        pass


def _write_run_state(**kwargs) -> None:
    """Persist the run outcome for the bot's ``/mylo lastrun`` (guarded no-op)."""
    if write_run_state is None:
        return
    write_run_state(**kwargs)


def pivot_session_exists() -> bool:
    """True if a saved Pivot SSO session is present on the host.

    Reuses the scraper's own ``state_exists()`` (which honors ``PIVOT_STORAGE_STATE``)
    so this check can never drift from where the scraper actually looks. That module
    is pure-stdlib, so importing it needs no Django setup. If it can't be imported for
    any reason we report "no session" — the caller then tries to log in, which is the
    safe direction.
    """
    backend = str(ROOT / "web" / "backend")
    if backend not in sys.path:
        sys.path.insert(0, backend)
    try:
        from apps.scraper.pivot.common import state_exists
    except Exception:
        return False
    return state_exists()


def scrape_opportunities() -> bool:
    """Log in if needed, then scrape grants/conferences/fellowships (host, non-fatal).

    Runs the host Pivot pipeline: ``uv run pivot.py login`` first when no session is
    saved, then ``uv run pivot.py scrape`` (browser scrape to ``data/pivot/*.json``)
    and ``uv run pivot.py import`` (dedup + prune + embed into the shared store).
    Every step is logged, reported to Discord when it needs a human, and swallowed
    on failure: the daily run should still recommend over the existing corpus, not
    abort, when the scrape can't run. Returns ``True`` when the import stage ran.
    """
    if not have_uv():
        message = (
            "`uv` is not on PATH — skipping the opportunity scrape; the later "
            "stages will match the corpus already in the store."
        )
        print(f"note: {message}", flush=True)
        _notify("warn", "Opportunity scrape skipped", message, stage="scrape")
        return False

    # No saved session → log in first so the scrape can actually reach the grant /
    # conference sources. Login is interactive (SSO/MFA in a browser); in a
    # non-interactive shell we cannot prompt, so we skip and match the existing corpus.
    if not pivot_session_exists():
        if not sys.stdin.isatty():
            message = (
                "No saved Pivot session and this is an unattended run, so Mylo "
                "cannot log in. Fresh grants/conferences/fellowships were NOT "
                "scraped today; the later stages matched the existing corpus."
            )
            print(f"note: {message}", flush=True)
            _notify(
                "error",
                "Pivot login needed — no fresh opportunities today",
                message,
                stage="scrape",
                action=f"Run `uv run pivot.py login` on {HOST} to refresh the session.",
            )
            return False
        print(
            "No saved Pivot session — opening the login window; complete SSO/MFA to "
            "continue…",
            flush=True,
        )
        if run_host(["uv", "run", "pivot.py", "login"]) != 0 or not pivot_session_exists():
            message = (
                "Pivot login did not complete; skipping the scrape. The later "
                "stages will match the existing corpus."
            )
            print(f"\nnote: {message}", flush=True)
            _notify(
                "error",
                "Pivot login did not complete",
                message,
                stage="scrape",
                action=f"Run `uv run pivot.py login` on {HOST}.",
            )
            return False

    if run_host(["uv", "run", "pivot.py", "scrape"]) != 0:
        message = (
            "The Pivot scrape did not complete — the session may have expired. "
            "Skipping import; the later stages will match the existing corpus."
        )
        print(f"\nnote: {message}", flush=True)
        _notify(
            "error",
            "Pivot scrape failed (session likely expired)",
            message,
            stage="scrape",
            action=f"Re-run `uv run pivot.py login` on {HOST}.",
        )
        return False

    if run_host(["uv", "run", "pivot.py", "import"]) != 0:
        message = (
            "Importing the scraped opportunities failed; the later stages will "
            "match whatever is already in the store."
        )
        print(f"\nnote: {message}", flush=True)
        _notify("warn", "Opportunity import failed", message, stage="scrape")
        return False

    return True


def preflight_llm(base: list[str]) -> bool:
    """Return True if the LLM endpoint is reachable; False (after reporting) if not.

    Runs ``llm_check --strict`` in the backend container before the recommend
    stages. The daily pipeline's paper rankings, opportunity scoring, and
    briefings are only worth writing when the model is up: the deterministic
    fallbacks would append lower-quality results to feeds that Mylo never
    rewrites, so a stale-but-real feed is better than one padded with template
    output. A non-zero exit therefore aborts the run instead of proceeding on
    fallbacks — nothing is scraped, matched, or briefed until the endpoint is
    back and the next run (or a manual re-run) can do it with the model up.
    """
    print("\n=== Pre-flight · Checking the LLM endpoint… ===", flush=True)
    if run_manage("llm_check", ["--strict"], intro=None, base=base) != 0:
        _notify(
            "error",
            "LLM endpoint unreachable — daily run skipped",
            "The daily run needs the language model for paper rankings, "
            "opportunity scoring, and briefings, so it did not run today. Nothing "
            "was scraped, matched, or briefed; the existing feeds are untouched. "
            "It will try again on the next scheduled run.",
            stage="preflight",
            action=(
                "Check the LLM server / `LLM_BASE_URL`; run `llm_check` in the "
                f"backend on {HOST}, then re-run `manual_all.py` once it is back."
            ),
        )
        return False
    return True


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
    # partway through the run before discovering the backend is down. ``ensure_ready``
    # exits (SystemExit) with guidance if the stack is down — report that too.
    try:
        base = ensure_ready()
    except SystemExit as exc:
        _notify(
            "error",
            "Daily run could not start — stack not ready",
            str(exc.code) if exc.code else "The backend stack is not up.",
            stage="startup",
            action=f"Run `python run.py up` on {HOST}.",
        )
        _write_run_state(ok=False, scrape_ran=False, stages_run=[], failed_stage="startup", exit_code=1)
        raise

    total = 1 + len(CONTAINER_STAGES)

    # Pre-flight — the entire pipeline (paper rankings, opportunity scoring,
    # briefings) depends on the LLM. If it is unreachable, do NOT run the search
    # or any later stage on deterministic fallbacks: abort before scraping so the
    # scrape does not ingest a batch of items that today's LLM-less run would
    # leave unmatched. The run will do everything on the next attempt with the
    # model up.
    if not preflight_llm(base):
        _write_run_state(
            ok=False,
            scrape_ran=False,
            stages_run=[],
            failed_stage="preflight",
            exit_code=1,
        )
        return 1

    # Stage 1 — scrape the opportunity sources on the host (non-fatal).
    print(
        f"\n=== 1/{total} · Scraping opportunity sources (grants, conferences, fellowships)… ===",
        flush=True,
    )
    scrape_ran = scrape_opportunities()

    # Stages 2..N — recommend, remind, prune, and brief inside the backend container.
    stages_run: list[str] = []
    for offset, (command, passthrough, intro) in enumerate(CONTAINER_STAGES):
        step = 2 + offset
        print(f"\n=== {step}/{total} · {intro} ===", flush=True)
        code = run_manage(command, passthrough, intro=None, base=base)
        if code != 0:
            print(
                f"\nStage '{command}' exited with code {code}; stopping before the "
                "remaining stages.",
                file=sys.stderr,
                flush=True,
            )
            _notify(
                "error",
                f"Daily run stage failed: {command}",
                f"Stage '{command}' exited with code {code}; the remaining stages "
                "were skipped.",
                stage=command,
                fields={"Exit code": str(code)},
                action=f"Check the backend logs on {HOST} (`python run.py logs`).",
            )
            _write_run_state(
                ok=False,
                scrape_ran=scrape_ran,
                stages_run=stages_run,
                failed_stage=command,
                exit_code=code,
            )
            return code
        stages_run.append(command)

    print(
        "\nAll stages completed: scrape → search → match → remind → prune → briefing "
        "→ report, for all users.",
        flush=True,
    )
    _write_run_state(ok=True, scrape_ran=scrape_ran, stages_run=stages_run)
    _notify(
        "info",
        "Daily run complete",
        "scrape → search → match → remind → prune → briefing → report finished for "
        "all users."
        + ("" if scrape_ran else " (opportunity scrape was skipped — see earlier alert)."),
        stage="done",
        fields={"Scrape ran": "yes" if scrape_ran else "no"},
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
