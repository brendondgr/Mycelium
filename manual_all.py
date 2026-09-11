#!/usr/bin/env python3
"""Run the full manual recommendation flow, in order, for all users.

Scrape every source, then recommend, then write each user's daily briefing —
one stage after another, synchronously, for *all* active users, against the
running Docker stack. This is what the host ``mylo-daily.timer`` runs once a
day (it replaced the in-container Celery Beat daily schedules, which could not
run the host-only Illinois fellowship scrape).

Stages, in order:
    1. Collect opportunity sources          — two independent, non-fatal
       halves. Grants and conferences run **in the backend container**
       through the open collector (``collect_opportunities``: collect -> map
       -> ingest -> extract -> embed, pure HTTP against public registries —
       no login, no session, no SSO). The Illinois Graduate College Fellowship
       Finder still scrapes **on the host** (``uv run scrape_fellowships.py
       scrape``), because it is the one opportunity source that still
       needs a real browser. Neither half can block the other or the rest of
       the night: a failed collector run warns, reports to Discord, and
       leaves the existing grant/conference corpus in place; a failed
       fellowship scrape does the same for fellowships. The dblp venue
       registry (plan D5a) also refreshes here, but on its own weekly
       cadence — see ``refresh_conference_registry`` — since venue longevity
       does not move night to night.
    2. Search research papers (backend)    — ``run_daily_suggestions``: scan the
       literature sources (OpenAlex / PubMed / SemanticScholar), embed, and rank
       papers for every target. The paper sources are scraped here, as part of the
       search — that is why stage 1 only has to add the opportunity sources.
    3. Rank opportunities (backend)        — ``run_daily_opportunities``: rank the
       **whole** grant / conference / fellowship corpus for every target against the
       profile it has *tonight*, and re-establish each feed from that ranking.

Stages 2 and 3 are the "filter and rank by preference" half of the run, and they
are deliberately whole-corpus. Ranking only each day's arrivals — which is what
this used to do — meant a feed was a historical accumulation: it recorded what
each past run happened to see, in whatever order the profile had at the time, so
editing a research focus could not change what a reader was shown, and an item's
position said when it arrived rather than how well it fits. Cost is contained by
carry-forward rather than by narrowing the scan: a verdict Mylo has already
written is reused, never re-billed, so what re-ranking nightly costs is retrieval.

Both stages run untargeted, so each covers all three target kinds: every entitled
user, every lab on an active subscription, and their in-cap active projects
(``apps.content.tasks.select_targets``). That has to match the briefing and digest
stages below — a lab that is briefed nightly but not *ranked* nightly has a frozen
feed, and its report reads "N papers, 0 new" every day.

Between 3 and 4 sit the reminder tick and two sweeps — ``prune_opportunities``
(expired listings) and ``prune_briefings`` (reports past
``BRIEFING_RETENTION_DAYS``). Both are pure deletions of expired rows, so neither
touches the rankings the stages above just wrote.
    3b. Fire project alerts (backend)      — ``evaluate_project_alerts``: which of
       today's findings actually change what a project should do. Five triggers,
       at most three per target per day, once ever per (target, project, item,
       trigger); overflow is held for the Monday weekly rather than dropped. The
       two arithmetic triggers (a venue that now fits, a deadline that moved)
       run always; the three similarity-based ones wait on
       ``PROJECT_ALERTS_ENABLED``.
    4. Write daily briefings (backend)     — ``generate_daily_briefing``: the
       "Mylo Report" for every user **and every entitled lab**, organised by
       research theme (LLM with a deterministic fallback), written over each
       theme's own slate. This is a per-*day* replace — a rerun re-describes today
       and leaves the earlier days' reports standing. When nothing entered any of
       a reader's themes, yesterday's report carries forward unchanged rather than
       being rewritten to say the same thing in new words.
    5. Send daily Discord reports (backend) — ``send_daily_discord_reports``: DM
       each linked, entitled, opted-in user their day — an overview of what kind of
       day it was, then statistics, with the full report attached as a PDF.
       Best-effort: an unreachable DM or Discord outage is counted, never fatal, so
       it can safely be the last stage.

**Who gets a message, and when.** Stages 4 and 5 do not cover the same people, and
that is the design (``apps.content.delivery``). Stage 4 writes a briefing for every
scheduled-eligible target, every day, whatever their cadence — the web app updates
daily for everyone. Stage 5 and the lab stage push only where cadence says a push is
due today: daily cadence gets a daily Tuesday to Friday and the Monday weekly,
weekly cadence gets the Monday weekly alone, and nobody is posted to at the weekend.
Each queued row carries a ``not_before`` set to the recipient's own local send hour,
so the run can finish at 3am and still land in someone's morning. A day with no
entrants and no alerts pushes nothing at all.

**What "new" means.** An item is new when it *enters a theme's slate*, not when it
was ingested — and entry is keyed on the **(theme, item)** pair, so the same paper
entering a second theme later is news again for that theme. Depth is per category
(``apps.content.slates``): papers 25 per theme because they are a flow, grants and
conferences 10 and fellowships 5 because they are a stock of currently-open calls
that barely moves. There is no global ranking anywhere in this path.

That is the whole point of ranking the corpus nightly: each theme's slate re-ranks
with the reader, so a changed focus, cluster, or search term promotes whatever now
fits and that promotion is what gets reported. Slate keys for a theme the profile
no longer declares are pruned on every run, over every stored row — a deleted
theme produces no candidates, so a candidate-driven prune would never reach it.

Only entrants Mylo has not already written up are sent to the model, and a
write-up is keyed on (item, theme, target): re-entering a slate is badged new
again but costs nothing, because "new to the reader's attention" is not "new to
Mylo". The rest of the slate keeps the write-up it already has. Reporting on arrival instead is what
produced mornings of "a new opportunity you haven't seen yet" for grants that had
nothing to do with the reader's work.

Items that fall out of a ranking are **retired, not deleted** — they leave the feed
but keep their verdict, so an item that dips out for a day and returns costs no
second model call. Refitting (``run_refitting`` /
``utils/manual/manual_refitting.py``) remains a distinct on-demand pass: it also
re-sends every surfaced item to the model, which is what a profile edit wants and
what a nightly run must never do.

A pre-flight ``llm_check --strict`` gates the whole run: the pipeline depends on
the LLM for paper rankings, opportunity scoring, and briefings, so if the
endpoint is unreachable the run is skipped entirely (nothing scraped, matched, or
briefed) rather than filling the feeds with deterministic fallbacks. It retries
on the next scheduled run.

Observability: every notable condition is posted to Mylo's Discord error channel
via :mod:`mylo.reporting` (a stdlib-only REST poster that never raises) — a
failed grant/conference collection or fellowship scrape, an unreachable LLM
(the run is skipped), a stage that exited non-zero, and the "run complete"
summary. The run also writes its outcome to ``data/logs/mylo-last-run.json``
for the bot's ``/mylo lastrun``.

That summary used to be one line ("all stages finished"), which proved the
pipeline had not crashed and said nothing about whether the night was worth
having. After the stages, a final **analytics** step runs
``run_analytics_report`` in the container: it measures the run against the rows
it just wrote — coverage, discovery, recommendations, LLM calls / failures /
tokens, report delivery — leaving the metrics in
``data/logs/mylo-run-analytics.json`` and a full report in ``data/analytics/``.
The host reads that JSON back through :mod:`mylo.analytics`, posts the numbers as
tables and bar charts, and attaches the PDF beneath the message. The step sits
outside ``CONTAINER_STAGES`` on purpose: measurement failing must not fail a run
that succeeded, so its exit code degrades the summary rather than the run.

Grants and conferences move into the backend container because the open
collector is pure HTTP — the host/container split Pivot-RP needed existed only
for its Playwright browser and saved SSO session (plan D6). The Illinois
fellowship scrape stays on the host for exactly the reason Pivot did:
Playwright. Host and container share the same Postgres, so a host-side
fellowship import is visible to the backend stages that follow. Every part of
stage 1 — the container collection, the host fellowship scrape, and the weekly
registry refresh — is non-fatal: a failed run warns, reports to Discord, and
lets the rest of the night proceed over whatever corpus already exists. Neither
half needs a login: the collector's sources are public HTTP, and the Illinois
Fellowship Finder's listing page needs no session either — only the retired
Pivot-RP scrape ever did.

Each stage runs for all users with default settings; this script takes no
pass-through flags on purpose, so "collect and recommend everything for
everyone" stays one predictable command. For a targeted run, call the
per-stage scripts in utils/manual/, run
``uv run --project web/backend python web/backend/manage.py
collect_opportunities`` directly, or ``uv run scrape_fellowships.py`` for
fellowships.

Usage:
    python manual_all.py        # collect → rank → slate → diff → report
    python manual_all.py --help # this message

The stack must be up first (``python run.py up``). Requires Docker Compose, plus
``uv`` on PATH for the host-side fellowship scrape.
"""

from __future__ import annotations

import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "utils" / "manual"))
from _runner import ensure_ready, have_uv, run_host, run_manage  # noqa: E402

# The Discord error reporter and the shared run-state writer are optional
# plumbing: if they can't be imported for any reason, the daily run must still
# complete. Every reporter call goes through ``_notify`` which no-ops when the
# reporter is unavailable; ``write_run_state`` is guarded the same way.
try:  # pragma: no cover - trivial import guard
    from mylo import analytics, reporting
    from mylo.runstate import write_run_state
except Exception:  # noqa: BLE001
    analytics = None  # type: ignore[assignment]
    reporting = None  # type: ignore[assignment]
    write_run_state = None  # type: ignore[assignment]

HOST = socket.gethostname()
ROOT = Path(__file__).resolve().parent

#: Where ``scrape_fellowships.py scrape`` writes its JSON (still named after
#: Pivot-RP's own layout — see that script's module docstring). Grants and
#: conferences never write here anymore (they collect straight into the
#: container's Postgres via ``collect_opportunities``), but a JSON file from
#: before this migration can still be sitting on disk on a host nobody has
#: cleaned up — see ``_purge_stale_pivot_json``.
PIVOT_DIR = ROOT / "data" / "pivot"

#: The dblp venue registry cache (plan D5a) — read by the conference
#: collector's resolve stage, written by the ``refresh_dblp_registry``
#: management command. Both sides resolve to the same path: ``data/collect``
#: is this repo's collector root (``apps.scraper.collect.runner.DEFAULT_ROOT``)
#: and ``registry`` is where every registry adapter's cache lands under it.
REGISTRY_CACHE_PATH = ROOT / "data" / "collect" / "registry" / "dblp_venues.json"

#: How often the dblp registry actually needs refreshing. Venue longevity —
#: has this stream published in the last few years — does not move night to
#: night, so refreshing on the same 24h cadence as everything else would spend
#: the same ~8 MB SPARQL request six nights out of seven for an unchanged
#: answer (plan D5a: "weekly is ample").
REGISTRY_REFRESH_INTERVAL_DAYS = 7

# The backend rank/briefing stages, in order, run inside the container. The scrape
# stage (stage 1) is handled separately on the host. The order is the product rule:
# collect everything, rank it all by preference, take each target's slate per theme
# per category, diff each theme against yesterday's, and report only what entered.
#
# Ordering matters for reminders (R2): opportunities ingest with ``--no-prune`` so
# the ContentDeadline projection is rebuilt but nothing is deleted yet, then the
# reminder tick fires against live deadlines, then a separate prune stage deletes
# expired items. A deadline that moved earlier into the past is therefore always
# seen by the tick before its item can be pruned out from under a live reminder.
# Each entry is (command, passthrough_args, intro).
CONTAINER_STAGES = [
    ("run_daily_suggestions", [], "Searching and ranking research papers for all targets…"),
    (
        "run_daily_opportunities",
        ["--no-prune"],
        "Ranking every grant/conference/fellowship for all targets…",
    ),
    ("run_reminder_tick", [], "Firing due deadline reminders…"),
    ("prune_opportunities", [], "Pruning expired opportunities…"),
    # Alongside the opportunity prune: both are pure deletions of expired rows, so
    # neither rewrites or rescores anything the earlier stages just wrote. Keeping
    # the briefing sweep in the daily chain is what stops the Reports page history
    # from drifting past its retention window.
    ("prune_briefings", [], "Pruning daily briefings past the retention window…"),
    # Before the briefings and after scoring, because it needs both: it reads the
    # day's slates, and the briefing reads the day's alerts.
    (
        "evaluate_project_alerts",
        [],
        "Deciding what today changes for each project…",
    ),
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


def compile_analytics(base: list[str]) -> dict | None:
    """Measure the run inside the container, then read the metrics back (non-fatal).

    Runs deliberately *outside* ``CONTAINER_STAGES``. Every stage in that list is
    load-bearing — a failure there means users did not get their day — while this
    one only describes what already happened. A chart that will not render, or an
    unwritable ``data/`` directory, must cost the summary's detail and nothing
    else, so a non-zero exit here is a note, not a run failure.

    Returns the metrics dict, or ``None`` when the stage or the read failed.
    """
    if analytics is None:
        return None
    print("\n=== Analytics · Compiling the internal usage report… ===", flush=True)
    code = run_manage("run_analytics_report", [], intro=None, base=base)
    if code != 0:
        message = (
            f"The analytics stage exited with code {code}; the run itself "
            "completed. Tonight's summary is posted without its detail."
        )
        print(f"note: {message}", flush=True)
        _notify("warn", "Daily analytics not compiled", message, stage="analytics")
        return None
    return analytics.read_analytics()


def report_run_complete(payload: dict | None, *, scrape_ran: bool) -> None:
    """Post the run summary — enriched with analytics and the PDF when available.

    Falls back to the plain completion notice when the analytics stage produced
    nothing. A finished run must always announce itself; the detail is a bonus,
    never a precondition.
    """
    if payload is None:
        _notify(
            "info",
            "Daily run complete",
            "scrape → rank → remind → prune → briefing → report finished "
            "for all users."
            + (
                ""
                if scrape_ran
                else " (opportunity scrape was skipped — see earlier alert)."
            ),
            stage="done",
            fields={"Scrape ran": "yes" if scrape_ran else "no"},
        )
        return

    fields: dict = {"Scrape ran": ("yes" if scrape_ran else "no", True)}
    fields.update(analytics.summary_fields(payload))
    attention = analytics.attention_line(payload)
    if attention:
        fields["Worth a look"] = attention

    _notify(
        "info",
        f"Daily run complete · {payload.get('generated_on', '')}".strip(" ·"),
        analytics.summary_body(payload, scrape_ran=scrape_ran),
        stage="done",
        fields=fields,
        # Resolved against this host's checkout: the path in the payload was
        # written by the container, where the tree is mounted at a different root.
        attachment=analytics.resolve_pdf(payload),
    )


def _write_run_state(**kwargs) -> None:
    """Persist the run outcome for the bot's ``/mylo lastrun`` (guarded no-op)."""
    if write_run_state is None:
        return
    write_run_state(**kwargs)


def _purge_stale_pivot_json() -> None:
    """Delete any leftover grants/conferences JSON from before this migration.

    ``scrape_fellowships.py`` (which replaced Pivot-RP's own ``pivot.py`` —
    plan Phase 6) only ever reads/writes ``pivot_fellowships.json`` by exact
    path, never a glob, so it can no longer accidentally re-ingest a stale
    ``pivot_grants.json`` / ``pivot_conferences.json`` left over from a run
    before this migration the way Pivot-RP's own ``pivot.py import`` could
    (it globbed every ``pivot_*.json`` file under ``PIVOT_DIR`` with no way to
    scope to one area). Those two files are nonetheless pure clutter now that
    grants/conferences collect straight into the container's Postgres — this
    is housekeeping, not a correctness guard the way it once was, and cheap
    enough to keep doing right before the one area that still writes here.
    """
    for stale_name in ("pivot_grants.json", "pivot_conferences.json"):
        stale_path = PIVOT_DIR / stale_name
        if stale_path.exists():
            print(
                f"note: removing stale {stale_path} (grants/conferences no "
                "longer scrape via Pivot)",
                flush=True,
            )
            stale_path.unlink()


def _scrape_fellowships() -> bool:
    """Host-side Illinois Fellowship Finder scrape + import (Playwright), non-fatal.

    The one opportunity source that still needs a real browser — see the
    module docstring. Unlike the retired Pivot-RP grant/conference scrape,
    this needs no saved session at all: ``scrape_fellowships.py scrape``
    reads a public listing page, so there is nothing here that needs to know
    about SSO or a login window. Every step is logged, reported to Discord
    when it needs a human, and swallowed on failure, matching stage 1's
    overall non-fatal contract: a failed fellowship refresh must never stop
    the run from recommending over the existing corpus.
    """
    if not have_uv():
        message = (
            "`uv` is not on PATH — skipping the Illinois fellowship scrape; "
            "the later stages will match the fellowships already in the store."
        )
        print(f"note: {message}", flush=True)
        _notify("warn", "Fellowship scrape skipped", message, stage="scrape")
        return False

    if run_host(["uv", "run", "scrape_fellowships.py", "scrape"]) != 0:
        message = (
            "The Illinois fellowship scrape did not complete. The later "
            "stages will match the fellowships already in the store."
        )
        print(f"\nnote: {message}", flush=True)
        _notify(
            "warn",
            "Fellowship scrape failed",
            message,
            stage="scrape",
            action=f"Check the Playwright/Chromium install on {HOST}.",
        )
        return False

    _purge_stale_pivot_json()

    if run_host(["uv", "run", "scrape_fellowships.py", "import"]) != 0:
        message = (
            "Importing the scraped fellowship listing failed; the later "
            "stages will match whatever is already in the store."
        )
        print(f"\nnote: {message}", flush=True)
        _notify("warn", "Fellowship import failed", message, stage="scrape")
        return False

    return True


def _collect_grants_and_conferences(base: list[str]) -> bool:
    """In-container grants + conferences collection (pure HTTP), non-fatal.

    Runs ``collect_opportunities`` — the open collector's four stages, mapped
    into ``ContentItem``, ingested, extracted (new records only; see
    ``--new-only`` on the command itself) and embedded, entirely inside the
    backend container. No login, no saved session: every source it touches is
    public HTTP. A failure here (a source outage, a database hiccup) is
    exactly the kind of thing stage 1 exists to survive: it warns, reports to
    Discord, and the rest of the run matches whatever grant/conference corpus
    already exists.
    """
    code = run_manage(
        "collect_opportunities",
        ["--new-only", "--no-prune"],
        intro=None,
        base=base,
    )
    if code != 0:
        message = (
            f"The grant/conference collector exited with code {code}; the "
            "later stages will match whatever is already in the store."
        )
        print(f"\nnote: {message}", flush=True)
        _notify(
            "error",
            "Grant/conference collection failed",
            message,
            stage="scrape",
            action=f"Check the backend logs on {HOST} (`python run.py logs`).",
        )
        return False
    return True


def refresh_conference_registry(base: list[str]) -> None:
    """Refresh the dblp venue registry cache on a weekly cadence (plan D5a).

    Must run before the collector's conference resolve stage — the registry
    join reads venue identity and rankings straight off this cache. The resolve
    stage is deliberately offline-only (see ``RegistryCache``'s own docstring),
    so a stale-or-missing cache is not an error there, only a ceiling on how
    many venues can carry a rank badge — which is
    exactly why this can self-throttle with a plain file-mtime check rather
    than needing its own systemd timer: venue longevity does not move night to
    night, so paying for a fresh 8 MB SPARQL POST on six nights out of seven
    would buy nothing a week-old answer didn't already have. Never fatal to
    the run either way.
    """
    try:
        age_days = (time.time() - REGISTRY_CACHE_PATH.stat().st_mtime) / 86400
    except OSError:
        age_days = None  # never fetched, or unreadable — refresh below

    if age_days is not None and age_days < REGISTRY_REFRESH_INTERVAL_DAYS:
        print(
            f"note: dblp registry cache is {age_days:.1f}d old "
            f"(< {REGISTRY_REFRESH_INTERVAL_DAYS}d) — skipping this week's refresh.",
            flush=True,
        )
        return

    print("\n=== Registry · Refreshing the dblp venue registry (weekly)… ===", flush=True)
    code = run_manage("refresh_dblp_registry", [], intro=None, base=base)
    if code != 0:
        message = (
            "The dblp registry refresh failed; conference trust tiers keep "
            "using whatever cache already exists (possibly none). This never "
            "blocks the run — it only caps how many venues can reach tier A "
            "until the next successful refresh."
        )
        print(f"note: {message}", flush=True)
        _notify("warn", "dblp registry refresh failed", message, stage="registry")


def scrape_opportunities(base: list[str]) -> bool:
    """Collect grants/conferences (container) and fellowships (host), non-fatal.

    The single entry point stage 1 has always exposed: same ``-> bool``
    contract, same "every failure is non-fatal, the run always recommends
    over whatever corpus exists" guarantee (see the module docstring). What
    changed is the *mechanism*, not the promise this function makes to
    ``main()``. ``True`` means at least one of the two halves actually
    refreshed something; ``False`` means neither did — and each already
    reported its own reason to Discord before returning.
    """
    collector_ok = _collect_grants_and_conferences(base)
    fellowships_ok = _scrape_fellowships()
    return collector_ok or fellowships_ok


def preflight_llm(base: list[str]) -> bool:
    """Return True if the LLM endpoint is reachable; False (after reporting) if not.

    Runs ``llm_check --strict`` in the backend container before the recommend
    stages. The daily pipeline's paper rankings, opportunity scoring, and
    briefings are only worth writing when the model is up: with the model down every
    slate entrant would be written up by the template instead, and an entitled
    reader would get a full report of items nobody had actually judged. A day-old but real report
    is better than a fresh one padded with template output. A non-zero exit therefore aborts the run instead of proceeding on
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
            "manual_all.py takes no arguments; it always collects every source and "
            "runs every stage for all users.\nFor a targeted run, call the per-stage "
            "scripts in utils/manual/, `manage.py collect_opportunities` directly, "
            "or `uv run scrape_fellowships.py` for fellowships."
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

    # Weekly housekeeping, ahead of stage 1: the conference resolve stage
    # inside collect_opportunities reads whatever registry cache already
    # exists, so refreshing it first (when due) is what lets tonight's run
    # actually benefit from it rather than resolving against a stale cache.
    refresh_conference_registry(base)

    # Stage 1 — collect opportunity sources: grants/conferences in the
    # container, fellowships on the host (non-fatal; see scrape_opportunities).
    print(
        f"\n=== 1/{total} · Collecting opportunity sources (grants, conferences, fellowships)… ===",
        flush=True,
    )
    scrape_ran = scrape_opportunities(base)

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
        "\nAll stages completed: scrape → rank → remind → prune → briefing "
        "→ report, for all users.",
        flush=True,
    )
    _write_run_state(ok=True, scrape_ran=scrape_ran, stages_run=stages_run)
    report_run_complete(compile_analytics(base), scrape_ran=scrape_ran)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
