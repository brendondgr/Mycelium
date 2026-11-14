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
       Finder still scrapes **on the host** (``uv run tools/retrieval/host/scrape_fellowships.py
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

Both stages run untargeted, so each covers every target kind: every entitled
user, every lab on an active subscription, every department on an active plan
(``select_departments`` — papers and opportunities alike, whether or not its
announcements are on), and their in-cap active projects
(``tools.recommendation.tasks.select_targets``). That has to match the briefing,
digest and weekly stages below, which take the same departments — a lab or
department that is briefed nightly but not *ranked* nightly has a frozen feed,
and its report reads "N papers, 0 new" every day.

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
       "Mylo Report" for every user **and every entitled lab and department**
       (a department through the lab's own function), organised by
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
that is the design (``tools.delivery.delivery``). Stage 4 writes a briefing for every
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
(``tools.recommendation.slates``): papers 25 per theme because they are a flow, grants and
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
``ops/nightly/manual_refitting.py``) remains a distinct on-demand pass: it also
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

After collection, a **collaboration** step (``extract_requirement_slots``)
reads what new funding calls ask a team to bring, so the scoring stages can mark
which of it the reader and their lab already cover; it is non-fatal.

Then an **ambient** step (``deliberate_ambient``) decides what the day's
conversation observations mean — pure over the ledger, plus model-written
explanations. Non-fatal, and a no-op while ``AMBIENT_DELIBERATE_ENABLED`` is off.

Just before analytics, a **knowledge** step (``facet_author_works``) reads
people's own imported papers into the knowledge graph — facets, demonstrated
edges — within a nightly cap. It is outside ``CONTAINER_STAGES`` for the same
reason: nothing a user receives today depends on it, so a failure is a warning.

Grants and conferences are collected inside the backend container because the
open collector is pure HTTP. The Illinois fellowship scrape stays on the host
because it drives a Playwright browser. Host and container share the same
Postgres, so a host-side fellowship import is visible to the backend stages
that follow. Every part of stage 1 — the container collection, the host
fellowship scrape, and the weekly registry refresh — is non-fatal: a failed run
warns, reports to Discord, and lets the rest of the night proceed over whatever
corpus already exists. Neither half needs a login: the collector's sources are
public HTTP, and the Illinois Fellowship Finder's listing page needs no session
either.

Each stage runs for all users with default settings; this script takes no
pass-through flags on purpose, so "collect and recommend everything for
everyone" stays one predictable command. For a targeted run, call the
per-stage scripts in ops/nightly/, run
``uv run --project web/backend python web/backend/manage.py
collect_opportunities`` directly, or ``uv run tools/retrieval/host/scrape_fellowships.py`` for
fellowships.

Usage:
    python ops/nightly/manual_all.py        # collect → rank → slate → diff → report
    python ops/nightly/manual_all.py --help # this message

The stack must be up first (``mycelium start``). Requires Docker Compose, plus
``uv`` on PATH for the host-side fellowship scrape.
"""

from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _runner  # noqa: E402
from _runner import (  # noqa: E402
    capture_manage,
    ensure_ready,
    have_uv,
    run_host,
    run_manage,
)

# The Discord error reporter and the shared run-state writer are optional
# plumbing: if they can't be imported for any reason, the daily run must still
# complete. Every reporter call goes through ``_notify`` which no-ops when the
# reporter is unavailable; ``write_run_state`` is guarded the same way.
# The repository root must be importable first: since this script moved to
# ops/nightly/ (2026-11-06) the import below failed silently, so the nightly
# posted no error or summary to Discord and stopped writing its run state.
if str(Path(__file__).resolve().parents[2]) not in sys.path:
    sys.path.append(str(Path(__file__).resolve().parents[2]))
try:  # pragma: no cover - trivial import guard
    from mylo import analytics, reporting
    from mylo.runstate import write_run_state
except Exception:  # noqa: BLE001
    analytics = None  # type: ignore[assignment]
    reporting = None  # type: ignore[assignment]
    write_run_state = None  # type: ignore[assignment]

HOST = socket.gethostname()
ROOT = Path(__file__).resolve().parents[2]

#: Where ``scrape_fellowships.py scrape`` writes its JSON. Grants and
#: conferences never write here (they collect straight into the container's
#: Postgres via ``collect_opportunities``), but a JSON file from an older layout
#: can still be sitting on disk on a host nobody has cleaned up — see
#: ``_tidy_scrape_dir``.
FELLOWSHIPS_DIR = ROOT / "data" / "fellowships"
#: The directory's previous name. Moved once, on the first run that finds it.
LEGACY_SCRAPE_DIR = ROOT / "data" / "pivot"
#: Files the older layout wrote (the fellowship JSON is now fellowships.json).
STALE_SCRAPE_FILES = ("pivot_grants.json", "pivot_conferences.json", "pivot_fellowships.json")

#: The dblp venue registry cache (plan D5a) — read by the conference
#: collector's resolve stage, written by the ``refresh_dblp_registry``
#: management command. Both sides resolve to the same path: ``data/collect``
#: is this repo's collector root (``tools.retrieval.collect.runner.DEFAULT_ROOT``)
#: and ``registry`` is where every registry adapter's cache lands under it.
REGISTRY_CACHE_PATH = ROOT / "data" / "collect" / "registry" / "dblp_venues.json"

#: How often the dblp registry actually needs refreshing. Venue longevity —
#: has this stream published in the last few years — does not move night to
#: night, so refreshing on the same 24h cadence as everything else would spend
#: the same ~8 MB SPARQL request six nights out of seven for an unchanged
#: answer (plan D5a: "weekly is ample").
REGISTRY_REFRESH_INTERVAL_DAYS = 7

# The backend rank/briefing stages, in order, run inside the container. The
# scrape stage (stage 1) is handled separately on the host. The order is the
# product rule: collect everything, rank it all by preference, take each
# target's slate per theme per category, diff each theme against yesterday's,
# and report only what entered.
#
# Each stage is declared by the tool that owns its command (``Tool.stages`` in
# tools/<name>/tool.py, or ``PLATFORM_STAGES`` in tools/_framework/nightly.py
# for one the platform still owns) with a phase; tools/_framework/nightly.py
# orders them, and a golden test holds the order to the one this file used to
# list by hand.
#
# Ordering matters for reminders (R2): opportunities ingest with ``--no-prune``
# so the ContentDeadline projection is rebuilt but nothing is deleted yet, then
# the reminder tick fires against live deadlines (phase ``remind``), then a
# separate prune stage deletes expired items (phase ``prune``). A deadline that
# moved earlier into the past is therefore always seen by the tick before its
# item can be pruned out from under a live reminder.
#
# A tool the container's import script did not LOAD contributes no stage: its
# stages are skipped tonight and reported (see ``tool_load_state``).
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))
from tools._framework import nightly as _tool_nightly  # noqa: E402


def planned_container_stages(loaded: list[str] | None = None):
    """``(command, passthrough_args, intro)`` per stage, in run order.

    ``loaded=None`` plans every installed tool (the static view); pass the
    container's loaded tool names to plan tonight's run.
    """
    run, _skipped = _tool_nightly.plan_for(loaded)
    return _tool_nightly.as_tuples(run)


CONTAINER_STAGES = planned_container_stages()


def tool_load_state(base: list[str]) -> tuple[list[str], list[tuple[str, str, str]]] | None:
    """Ask the container which tools loaded: ``(loaded, [(tool, state, reason)])``.

    ``None`` if the import script could not run at all, which means Django
    itself cannot start in the container.
    """
    raw = capture_manage("tools", ["check", "--json", "--lenient"], base=base)
    if not raw:
        return None
    try:
        report = json.loads(raw)
    except ValueError:
        return None
    tools = report.get("tools", {})
    loaded = [n for n in report.get("order", []) if tools[n]["state"] == "LOADED"]
    others = [
        (n, tools[n]["state"], (tools[n].get("reason") or "").splitlines()[0]
         if tools[n].get("reason") else "")
        for n in report.get("order", []) if tools[n]["state"] != "LOADED"
    ]
    return loaded, others


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


def extract_requirement_slots(base: list[str]) -> None:
    """Read what new funding calls ask a team to bring (non-fatal).

    Between collection and scoring, so tonight's team-fit lines read tonight's
    calls. Outside ``CONTAINER_STAGES``: a call without slots shows no team-fit
    line, which is honest, and must not stop anyone's report.
    """
    print("\n=== Collaboration · Reading what new calls require… ===", flush=True)
    code = run_manage("extract_requirement_slots", [], intro=None, base=base)
    if code != 0:
        message = (
            f"Reading call requirements exited with code {code}; the run "
            "continues. Calls without slots show no team-fit line until tomorrow."
        )
        print(f"note: {message}", flush=True)
        _notify("warn", "Call requirements not read", message, stage="collab")


def deliberate_ambient(base: list[str]) -> None:
    """Decide what the day's conversation observations mean (non-fatal).

    Before ranking, so today's findings can reach today's slates once Plan 05
    reads them. Outside ``CONTAINER_STAGES``: nobody's report depends on it, and
    it does nothing at all while ``AMBIENT_DELIBERATE_ENABLED`` is off.
    """
    print("\n=== Ambient · Deciding what conversation showed… ===", flush=True)
    code = run_manage("deliberate_ambient", [], intro=None, base=base)
    if code != 0:
        message = (
            f"Ambient deliberation exited with code {code}; the run continues. "
            "Nothing is decided about anybody until tomorrow."
        )
        print(f"note: {message}", flush=True)
        _notify("warn", "Ambient deliberation failed", message, stage="ambient")


def send_slack_reports(base: list[str]) -> None:
    """Queue today's Slack reports (ambient Plan 11; non-fatal, a no-op while
    SLACK_ENABLED is off). The reports themselves were written by the stages."""
    print("\n=== Slack · Queueing today's reports… ===", flush=True)
    code = run_manage("send_slack_reports", [], intro=None, base=base)
    if code != 0:
        message = f"Queueing Slack reports exited with code {code}."
        print(f"note: {message}", flush=True)
        _notify("warn", "Slack reports not queued", message, stage="slack")


def deliver_ambient_questions(base: list[str]) -> None:
    """Send tonight's ambient questions and ring the bell (non-fatal).

    After the stages, so a question arrives with — never before — the report
    it belongs beside; each goes out at the person's own send hour.
    """
    print("\n=== Ambient · Sending tonight's questions… ===", flush=True)
    code = run_manage("deliver_ambient_questions", [], intro=None, base=base)
    if code != 0:
        message = (
            f"Sending ambient questions exited with code {code}; they stay "
            "queued and go out tomorrow."
        )
        print(f"note: {message}", flush=True)
        _notify("warn", "Ambient questions not sent", message, stage="ambient")


def facet_author_works(base: list[str]) -> None:
    """Read people's own papers into the knowledge graph (non-fatal).

    Outside ``CONTAINER_STAGES`` for the same reason as analytics: nothing a
    user receives today depends on it (a person's papers never shape their own
    ranking), so a failure here is a warning, not a failed run. Capped per night
    inside the command; a backlog is worked through over several nights.
    """
    print("\n=== Knowledge · Reading people's own papers… ===", flush=True)
    code = run_manage("facet_author_works", [], intro=None, base=base)
    if code != 0:
        message = (
            f"Reading people's papers exited with code {code}; the run itself "
            "completed. Unread papers are tried again tomorrow."
        )
        print(f"note: {message}", flush=True)
        _notify("warn", "Author papers not read", message, stage="knowledge")


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


def _tidy_scrape_dir() -> None:
    """Move the old ``data/pivot`` directory to ``data/fellowships`` once, and
    delete the JSON files the older layout left there.

    The fellowship scraper only ever reads and writes its own file by exact
    path, never a glob, so the leftovers cannot be re-ingested; removing them
    is housekeeping, cheap enough to do right before the one area that still
    writes here.
    """
    if LEGACY_SCRAPE_DIR.is_dir() and not FELLOWSHIPS_DIR.exists():
        try:
            LEGACY_SCRAPE_DIR.rename(FELLOWSHIPS_DIR)
            print(f"note: moved {LEGACY_SCRAPE_DIR} to {FELLOWSHIPS_DIR}", flush=True)
        except OSError as exc:
            print(f"note: could not move {LEGACY_SCRAPE_DIR} ({exc})", flush=True)
    for directory in (FELLOWSHIPS_DIR, LEGACY_SCRAPE_DIR):
        for stale_name in STALE_SCRAPE_FILES:
            stale_path = directory / stale_name
            if stale_path.exists():
                print(
                    f"note: removing stale {stale_path} (left by an older layout)",
                    flush=True,
                )
                stale_path.unlink()


def _scrape_fellowships() -> bool:
    """Host-side Illinois Fellowship Finder scrape + import (Playwright), non-fatal.

    The one opportunity source that still needs a real browser — see the
    module docstring. It needs no saved session: ``scrape_fellowships.py
    scrape`` reads a public listing page, so there is nothing here that needs
    to know about a login. Every step is logged, reported to Discord
    when it needs a human, and swallowed on failure, matching stage 1's
    overall non-fatal contract: a failed fellowship refresh must never stop
    the run from recommending over the existing corpus.
    """
    # Before the scrape, so a scraper still writing the old directory name
    # finds its own output where it left it for the import step.
    _tidy_scrape_dir()

    if not have_uv():
        message = (
            "`uv` is not on PATH — skipping the Illinois fellowship scrape (it "
            "needs a browser on this host; the stack itself does not need uv); "
            "the later stages will match the fellowships already in the store."
        )
        print(f"note: {message}", flush=True)
        _notify("warn", "Fellowship scrape skipped", message, stage="scrape")
        return False

    if run_host(["uv", "run", "tools/retrieval/host/scrape_fellowships.py", "scrape"]) != 0:
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

    if run_host(["uv", "run", "tools/retrieval/host/scrape_fellowships.py", "import"]) != 0:
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
            action=f"Check the backend logs on {HOST} (`mycelium logs`).",
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


def model_off_on_purpose() -> bool:
    """``llm.enabled = false`` in mycelium.toml: this instance runs without a
    language model by choice, so a missing model is not an outage.

    Read on the host with the standard-library config reader, which resolves
    the file and the environment exactly as the backend does.
    """
    try:
        sys.path.insert(0, str(ROOT / "ops" / "setup"))
        import config_cli

        return not bool(config_cli.resolve()["llm.enabled"])
    except Exception:  # noqa: BLE001 - unreadable config: let llm_check decide
        return False


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
    if model_off_on_purpose():
        # No model by choice (setup's "none for now"): the run is what this
        # instance offers, so it collects and ranks with deterministic drafts
        # instead of skipping every night.
        print(
            "Language model off on purpose (llm.enabled = false): collecting and "
            "ranking with deterministic write-ups.",
            flush=True,
        )
        return True
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


def start_model_budget(base: list[str]) -> None:
    """Record where tonight's ``nightly.model_calls`` budget starts counting.

    Every later stage gets the starting point as environment, so they all draw on
    one budget (``apps.core.llm_budget``). With no budget configured the values
    are harmless; if the command fails the run simply goes unbudgeted.
    """
    import json

    raw = capture_manage("nightly_budget", ["--start"], base=base)
    try:
        _runner.EXTRA_ENV.update({str(k): str(v) for k, v in json.loads(raw).items()})
    except (TypeError, ValueError):
        print("  · nightly model-call budget not started; running unbudgeted", flush=True)


def main() -> int:
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        print(__doc__)
        return 0

    if sys.argv[1:]:
        sys.exit(
            "manual_all.py takes no arguments; it always collects every source and "
            "runs every stage for all users.\nFor a targeted run, call the per-stage "
            "scripts in ops/nightly/, `manage.py collect_opportunities` directly, "
            "or `uv run tools/retrieval/host/scrape_fellowships.py` for fellowships."
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
            action=f"Run `mycelium start` on {HOST}.",
        )
        _write_run_state(ok=False, scrape_ran=False, stages_run=[], failed_stage="startup", exit_code=1)
        raise

    # The import script: which tools may run tonight. A tool that is not LOADED
    # (disabled, broken, or missing a dependency) contributes no stage; each
    # one set aside is reported, never skipped silently.
    state = tool_load_state(base)
    if state is None:
        _notify(
            "error",
            "Daily run could not start — the tools import script failed",
            "`manage.py tools check` did not run in the backend container, so "
            "Django itself cannot start there.",
            stage="tools",
            action=f"Run `make tools-check` on {HOST} and read the error.",
        )
        _write_run_state(ok=False, scrape_ran=False, stages_run=[], failed_stage="tools", exit_code=1)
        return 1
    loaded_tools, set_aside = state
    stages = planned_container_stages(loaded_tools)
    skipped = [cmd for cmd, *_ in CONTAINER_STAGES if cmd not in {c for c, *_ in stages}]
    for name, tool_state, reason in set_aside:
        print(f"Tool {name} is {tool_state}: {reason}", file=sys.stderr, flush=True)
    if set_aside:
        _notify(
            "warn",
            "Daily run: tools set aside",
            "\n".join(f"{n}: {st} — {why}" for n, st, why in set_aside),
            stage="tools",
            fields={"Skipped stages": ", ".join(skipped) or "none"},
            action=f"Run `make tools-check` on {HOST}.",
        )

    total = 1 + len(stages)

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

    start_model_budget(base)

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
    extract_requirement_slots(base)
    deliberate_ambient(base)

    # Stages 2..N — recommend, remind, prune, and brief inside the backend container.
    stages_run: list[str] = []
    for offset, (command, passthrough, intro) in enumerate(stages):
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
                action=f"Check the backend logs on {HOST} (`mycelium logs`).",
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
    deliver_ambient_questions(base)
    send_slack_reports(base)
    facet_author_works(base)
    report_run_complete(compile_analytics(base), scrape_ran=scrape_ran)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
