#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27,<1.0"]
# ///
"""Onboarding load test — simulate concurrent user onboarding to stress the server.

This harness replays the real onboarding flow (the same API the browser uses) for
many fake users spread randomly across a time window, to stress-test server-side
compute: **embedding generation** (profile writes), **embedding filtering/search**
and **LLM-based recommendation generation** (the per-area match). Fake users are
built deterministically from a static interest catalog — the LLM is exercised by
the *recommendation* step, not by user generation.

Per simulated user, in sequence (mirrors ``onboarding-flow.tsx``):

  1. GET   /auth/csrf/              — obtain the CSRF cookie
  2. POST  /auth/register/         — create a personal account + log in
  3. PATCH /auth/profile/me/       — role + institution (embedding hook fires)
  4. POST  /auth/intake/synthesize/  — optional (--synthesize): LLM profile fill
  5. POST  /auth/intake/confirm/   — save deterministic interests (embedding gen)
  6. PATCH /auth/watch/me/         — topics + variable categories + cadence
  7. POST  /onboarding/match/      — one call per opted-in area (retrieval + LLM)

During the run a live console table shows progress and throughput; after the run
a summary table prints and detailed CSVs are written. Every fake user created is
then deleted via the ``loadtest_purge`` management command.

Run it (uv installs httpx into an ephemeral env from the header above):

    uv run loadtest.py --users 500 --window 30m
    uv run loadtest.py --users 2 --window 20 --base-url http://localhost:11350/api

IMPORTANT — registration throttle: the server caps anonymous registration at
``DJANGO_REGISTER_THROTTLE_RATE`` (default 20/hour). Start the backend with a high
value for a real run, e.g. ``DJANGO_REGISTER_THROTTLE_RATE=1000000/hour``.
See docs/loadtest.md.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import math
import random
import shutil
import statistics
import subprocess
import sys
import time
import traceback
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import httpx

# Full-detail run log (config, every failed request with its body, per-user
# failure reasons, the final summary). Configured to a file in setup_logging();
# the console is left for the live dashboard so the two never interleave.
logger = logging.getLogger("loadtest")


def _clip(text: str, limit: int) -> str:
    """Trim ``text`` to ``limit`` chars, flagging how much was dropped."""
    text = text or ""
    if len(text) <= limit:
        return text
    return f"{text[:limit]}… (+{len(text) - limit} more chars)"

# The interest catalog + deck selector live in a sibling module (no external deps).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from loadtest_interests import CATALOG, FIELDS, Interest, build_selector  # noqa: E402

# The four areas the onboarding match can run, in report order. Each maps to a
# watch-category key, so a user only matches areas they kept switched on.
MATCH_AREAS = ("papers", "grants", "fellowships", "conferences")

# Stage labels used for per-request metrics and the CSV "stage" column.
STAGE_CSRF = "csrf"
STAGE_REGISTER = "register"
STAGE_PROFILE = "profile"
STAGE_SYNTHESIZE = "synthesize"
STAGE_CONFIRM = "confirm"
STAGE_WATCH = "watch"
STAGE_MATCH = "match"

# Stages that SAVE the user's Profile → fire the pre_save embedding hook (the
# embedding-generation code path). `synthesize` is excluded: it returns a draft
# without saving, so it fires no hook — it is an LLM call, tracked as its own stage.
EMBEDDING_GEN_STAGES = frozenset({STAGE_CONFIRM, STAGE_PROFILE})

MARKER_EMAIL_DOMAIN = "loadtest.mycelium.test"
USERNAME_PREFIX = "lt_"
# Meets AUTH_PASSWORD_VALIDATORS (length, not all-numeric, not too common).
FAKE_PASSWORD = "Mycelium-Load-9271"


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
@dataclass
class OpRecord:
    """One HTTP request's outcome — the row shape of operations.csv."""

    user_idx: int
    username: str
    stage: str
    area: str
    method: str
    status_code: int
    ok: bool
    latency_ms: float
    started_at: float
    error: str = ""


@dataclass
class Metrics:
    """Live counters + the full per-request log, shared across all user tasks."""

    target_users: int
    started_at: float

    users_started: int = 0
    users_completed: int = 0
    users_failed: int = 0

    requests_in_flight: int = 0
    requests_done: int = 0

    # Match (= LLM recommendation) calls specifically.
    match_in_flight: int = 0
    match_done: int = 0
    # Embedding-generation writes (profile/confirm/synthesize) completed.
    embed_gen_done: int = 0
    # Embedding filtering/search passes (one per match call) completed.
    embed_filter_done: int = 0

    # Aggregated from match responses.
    matched_total: int = 0
    llm_scores: int = 0
    fallback_scores: int = 0

    errors: int = 0
    errors_by_key: Counter = field(default_factory=Counter)
    # Which stage a fully-failed user bailed at (csrf / register / exception).
    user_fail_stage: Counter = field(default_factory=Counter)
    latency_by_stage: dict[str, list[float]] = field(
        default_factory=lambda: defaultdict(list)
    )
    records: list[OpRecord] = field(default_factory=list)

    def record(self, rec: OpRecord) -> None:
        self.requests_done += 1
        self.latency_by_stage[rec.stage].append(rec.latency_ms)
        self.records.append(rec)
        if not rec.ok:
            self.errors += 1
            if rec.status_code:
                key = f"{rec.stage} {rec.status_code}"
            else:
                # No HTTP status → a network exception; key by its type so the
                # breakdown and the diagnosis can see (e.g.) ConnectError/ReadTimeout.
                etype = rec.error.split(":", 1)[0] if rec.error else "error"
                key = f"{rec.stage} {etype}"
            self.errors_by_key[key] += 1
        if rec.stage == STAGE_MATCH:
            self.match_done += 1
            if rec.ok:
                self.embed_filter_done += 1
        if rec.ok and rec.stage in EMBEDDING_GEN_STAGES:
            self.embed_gen_done += 1


# --------------------------------------------------------------------------- #
# One simulated user
# --------------------------------------------------------------------------- #
def _csrf_header(client: httpx.AsyncClient) -> dict[str, str]:
    """Current csrftoken from the cookie jar as an X-CSRFToken header.

    Django rotates the token on login, so this is re-read before every unsafe
    request rather than cached.
    """
    token = client.cookies.get("csrftoken")
    return {"X-CSRFToken": token} if token else {}


def build_interests(picks: list[Interest]) -> dict:
    """A contract-shaped ``interests`` dict from the user's selected catalog rows.

    Deterministic: statement = joined descriptions, areas/keywords unioned across
    the picks, plus a safe default eligibility block (as the real flow sends).
    """
    areas: list[str] = []
    keywords: list[str] = []
    for interest in picks:
        if interest.area not in areas:
            areas.append(interest.area)
        for kw in interest.keywords:
            if kw not in keywords:
                keywords.append(kw)
    statement = " ".join(i.description for i in picks)
    return {
        "version": 1,
        "areas": areas,
        "statement": statement,
        "keywords": keywords,
        "skills": [],
        "eligibility": {
            "citizenship": "us",
            "stage": "",
            "fields": [],
            "eligible_restrictions": [],
        },
    }


def build_resume_text(picks: list[Interest]) -> str:
    """A plain-text 'résumé' built from the picks, for the optional synthesize path."""
    lines = ["Research Summary", ""]
    for interest in picks:
        lines.append(f"- {interest.area} ({interest.field}): {interest.description}")
    lines.append("")
    lines.append("Keywords: " + ", ".join(kw for i in picks for kw in i.keywords))
    return "\n".join(lines)


class UserSim:
    """Drives one fake user through the whole onboarding sequence over HTTP."""

    def __init__(
        self,
        idx: int,
        run_id: str,
        picks: list[Interest],
        categories: list[str],
        cfg: "Config",
        metrics: Metrics,
    ) -> None:
        self.idx = idx
        self.run_id = run_id
        self.picks = picks
        self.categories = categories
        self.cfg = cfg
        self.metrics = metrics
        self.username = f"{USERNAME_PREFIX}{run_id}_{idx:05d}"
        self.email = f"{self.username}@{MARKER_EMAIL_DOMAIN}"

    async def _do(
        self,
        client: httpx.AsyncClient,
        stage: str,
        method: str,
        path: str,
        *,
        area: str = "",
        expect: tuple[int, ...] = (200,),
        **kwargs,
    ) -> httpx.Response | None:
        """Issue one request, timing it and recording the outcome. None on failure."""
        m = self.metrics
        m.requests_in_flight += 1
        if stage == STAGE_MATCH:
            m.match_in_flight += 1
        started = time.time()
        status_code = 0
        error = ""
        response: httpx.Response | None = None
        try:
            response = await client.request(method, path, **kwargs)
            status_code = response.status_code
            if status_code not in expect:
                body = response.text
                error = f"HTTP {status_code}: {body[:120]}"
                # Full body to the log so failures are diagnosable, not guessed.
                logger.error(
                    "user=%05d stage=%-9s area=%-11s %s %s -> HTTP %s\n"
                    "    response: %s",
                    self.idx, stage, area or "-", method, path, status_code,
                    _clip(body.strip(), 1500),
                )
        except Exception as exc:  # network / timeout / protocol
            error = f"{type(exc).__name__}: {exc}"[:160]
            logger.error(
                "user=%05d stage=%-9s area=%-11s %s %s -> %s: %s",
                self.idx, stage, area or "-", method, path,
                type(exc).__name__, exc,
            )
        finally:
            latency_ms = (time.time() - started) * 1000.0
            m.requests_in_flight -= 1
            if stage == STAGE_MATCH:
                m.match_in_flight -= 1
            ok = status_code in expect
            if ok and self.cfg.log_requests:
                logger.info(
                    "user=%05d stage=%-9s area=%-11s %s %s -> %s (%.0f ms)",
                    self.idx, stage, area or "-", method, path,
                    status_code, latency_ms,
                )
            m.record(
                OpRecord(
                    user_idx=self.idx,
                    username=self.username,
                    stage=stage,
                    area=area,
                    method=method,
                    status_code=status_code,
                    ok=ok,
                    latency_ms=latency_ms,
                    started_at=started,
                    error=error,
                )
            )
        return response if (response is not None and status_code in expect) else None

    async def run(self, client: httpx.AsyncClient) -> None:
        m = self.metrics
        m.users_started += 1
        try:
            # 1. CSRF cookie.
            if await self._do(client, STAGE_CSRF, "GET", "/auth/csrf/") is None:
                m.users_failed += 1
                m.user_fail_stage[STAGE_CSRF] += 1
                logger.warning("user=%05d FAILED at stage=csrf", self.idx)
                return

            # 2. Register (creates account + logs in). 201 on success.
            reg = await self._do(
                client,
                STAGE_REGISTER,
                "POST",
                "/auth/register/",
                expect=(201,),
                headers=_csrf_header(client),
                json={
                    "username": self.username,
                    "email": self.email,
                    "password": FAKE_PASSWORD,
                    "password_confirm": FAKE_PASSWORD,
                    "account_type": "personal",
                    "first_name": "Load",
                    "last_name": f"Test{self.idx}",
                },
            )
            if reg is None:
                m.users_failed += 1
                m.user_fail_stage[STAGE_REGISTER] += 1
                logger.warning("user=%05d FAILED at stage=register", self.idx)
                return

            # 3. Profile basics.
            await self._do(
                client,
                STAGE_PROFILE,
                "PATCH",
                "/auth/profile/me/",
                headers=_csrf_header(client),
                json={"academic_title": "researcher", "institution": "Load Test University"},
            )

            # 4. Optional LLM profile fill from a résumé built off the picks.
            if self.cfg.synthesize:
                resume = build_resume_text(self.picks).encode("utf-8")
                await self._do(
                    client,
                    STAGE_SYNTHESIZE,
                    "POST",
                    "/auth/intake/synthesize/",
                    headers=_csrf_header(client),
                    files={"resume": ("resume.txt", resume, "text/plain")},
                )

            # 5. Save deterministic interests (embedding generation).
            await self._do(
                client,
                STAGE_CONFIRM,
                "POST",
                "/auth/intake/confirm/",
                headers=_csrf_header(client),
                json={"interests": build_interests(self.picks)},
            )

            # 6. Watch preferences (variable categories).
            topics = [i.area for i in self.picks] + [
                kw for i in self.picks for kw in i.keywords
            ]
            await self._do(
                client,
                STAGE_WATCH,
                "PATCH",
                "/auth/watch/me/",
                headers=_csrf_header(client),
                json={
                    "topics": topics[:12],
                    "categories": self.categories,
                    "cadence": "weekly",
                },
            )

            # 7. Match each opted-in area (retrieval + LLM recommendation).
            match_areas = [a for a in MATCH_AREAS if a in self.categories]
            for area in match_areas:
                resp = await self._do(
                    client,
                    STAGE_MATCH,
                    "POST",
                    "/onboarding/match/",
                    area=area,
                    headers=_csrf_header(client),
                    json={"area": area},
                )
                if resp is not None:
                    try:
                        data = resp.json()
                        m.matched_total += int(data.get("matched", 0) or 0)
                        m.llm_scores += int(data.get("llm", 0) or 0)
                        m.fallback_scores += int(data.get("fallback", 0) or 0)
                    except Exception:
                        pass

            m.users_completed += 1
            logger.debug("user=%05d completed", self.idx)
        except Exception:
            # Defensive: a bug in the harness must not sink the whole run.
            m.users_failed += 1
            m.user_fail_stage["exception"] += 1
            logger.error(
                "user=%05d FAILED with exception:\n%s",
                self.idx, traceback.format_exc(),
            )


# --------------------------------------------------------------------------- #
# Live dashboard
# --------------------------------------------------------------------------- #
def _pct(part: int, whole: int) -> float:
    return (100.0 * part / whole) if whole else 0.0


def _fmt_dur(seconds: float) -> str:
    seconds = max(0, int(seconds))
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"


def _stage_stats(samples: list[float]) -> tuple[int, float, float]:
    """(count, mean_ms, p95_ms) for a list of latency samples."""
    if not samples:
        return 0, 0.0, 0.0
    mean = statistics.fmean(samples)
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1)]
    return len(samples), mean, p95


class Dashboard:
    """Renders the live status table, in place on a TTY, snapshots otherwise."""

    def __init__(self, metrics: Metrics, cfg: "Config") -> None:
        self.m = metrics
        self.cfg = cfg
        self.loops = 0
        self.is_tty = sys.stdout.isatty() and not cfg.no_live
        self._prev_lines = 0

    def _lines(self, window_deadline: float) -> list[str]:
        m = self.m
        now = time.time()
        elapsed = now - m.started_at
        remaining = max(0.0, window_deadline - now)
        avg_all = statistics.fmean(
            [x for s in m.latency_by_stage.values() for x in s]
        ) if m.records else 0.0
        users_per_min = (m.users_completed / elapsed * 60.0) if elapsed > 0 else 0.0
        ops_per_sec = (m.requests_done / elapsed) if elapsed > 0 else 0.0

        lines = [
            f"  Onboarding load test · run {self.cfg.run_id} · loop {self.loops}",
            f"  {'─' * 66}",
            f"  Users     started {m.users_started:>5} · done {m.users_completed:>5}"
            f" · failed {m.users_failed:>4}  / target {m.target_users}"
            f"   ({_pct(m.users_completed, m.target_users):5.1f}%)",
            f"  Requests  in-flight {m.requests_in_flight:>4} · done {m.requests_done:>6}"
            f" · errors {m.errors:>4}",
            f"  Match/LLM in-flight {m.match_in_flight:>4} · done {m.match_done:>6}"
            f"   (llm {m.llm_scores} · fallback {m.fallback_scores} · matched {m.matched_total})",
            f"  Embeddings  generation {m.embed_gen_done:>6} · filter/search {m.embed_filter_done:>6}",
            f"  Timing    elapsed {_fmt_dur(elapsed)} · window left {_fmt_dur(remaining)}"
            f" · avg {avg_all:6.0f} ms",
            f"  Rate      {users_per_min:5.1f} users/min · {ops_per_sec:5.1f} req/s",
            f"  {'─' * 66}",
            f"  {'stage':<11}{'count':>7}{'mean ms':>10}{'p95 ms':>10}",
        ]
        for stage in (
            STAGE_CSRF, STAGE_REGISTER, STAGE_PROFILE, STAGE_SYNTHESIZE,
            STAGE_CONFIRM, STAGE_WATCH, STAGE_MATCH,
        ):
            n, mean, p95 = _stage_stats(m.latency_by_stage.get(stage, []))
            if n:
                lines.append(f"  {stage:<11}{n:>7}{mean:>10.0f}{p95:>10.0f}")
        if m.errors_by_key:
            top = ", ".join(
                f"{k}×{v}" for k, v in m.errors_by_key.most_common(4)
            )
            lines.append(f"  errors: {top}")
        return lines

    def render(self, window_deadline: float) -> None:
        self.loops += 1
        lines = self._lines(window_deadline)
        if self.is_tty:
            if self._prev_lines:
                sys.stdout.write(f"\033[{self._prev_lines}A")  # cursor up
            width = shutil.get_terminal_size((80, 24)).columns
            for line in lines:
                sys.stdout.write("\033[2K" + line[: width - 1] + "\n")
            self._prev_lines = len(lines)
            sys.stdout.flush()
        else:
            # Non-TTY: emit a compact one-line snapshot periodically.
            m = self.m
            print(
                f"[{_fmt_dur(time.time() - m.started_at)}] "
                f"users {m.users_completed}/{m.target_users} "
                f"(failed {m.users_failed}) · match {m.match_done} "
                f"· req {m.requests_done} · err {m.errors}",
                flush=True,
            )


# --------------------------------------------------------------------------- #
# Scheduling + orchestration
# --------------------------------------------------------------------------- #
@dataclass
class Config:
    users: int
    window: float
    base_url: str
    max_concurrency: int
    seed: int
    all_categories_fraction: float
    synthesize: bool
    out_dir: Path
    run_id: str
    request_timeout: float
    no_live: bool
    cleanup: bool
    purge_cmd: str
    refresh_interval: float
    log_file: Path
    log_level: str
    log_requests: bool


def pick_categories(rng: random.Random, cfg: Config) -> list[str]:
    """Recommendation categories for one user — most get all four, some a subset."""
    always = ["graph"]  # non-area signal kept on, mirrors the UI default
    if rng.random() < cfg.all_categories_fraction:
        chosen = list(MATCH_AREAS)
    else:
        # Drop a random 1–3 of the four areas, but always keep at least one.
        keep = rng.randint(1, 3)
        chosen = rng.sample(list(MATCH_AREAS), keep)
    return chosen + always


async def _run_user(
    sim: UserSim, cfg: Config, sem: asyncio.Semaphore, delay: float
) -> None:
    await asyncio.sleep(delay)
    async with sem:
        # Each user gets an isolated cookie jar (own session), like a real browser.
        async with httpx.AsyncClient(
            base_url=cfg.base_url,
            timeout=cfg.request_timeout,
            follow_redirects=False,
        ) as client:
            await sim.run(client)


async def _live_loop(dashboard: Dashboard, deadline: float, done: asyncio.Event, cfg: Config) -> None:
    while not done.is_set():
        dashboard.render(deadline)
        try:
            await asyncio.wait_for(done.wait(), timeout=cfg.refresh_interval)
        except asyncio.TimeoutError:
            pass
    dashboard.render(deadline)  # final frame


async def run_load_test(cfg: Config) -> Metrics:
    rng = random.Random(cfg.seed)
    selector = build_selector(rng)

    metrics = Metrics(target_users=cfg.users, started_at=time.time())
    window_deadline = metrics.started_at + cfg.window
    sem = asyncio.Semaphore(cfg.max_concurrency)

    # Random start offsets across the window (not evenly spaced — bursts allowed).
    sims: list[tuple[float, UserSim]] = []
    for idx in range(cfg.users):
        picks = selector()
        categories = pick_categories(rng, cfg)
        sim = UserSim(idx, cfg.run_id, picks, categories, cfg, metrics)
        delay = rng.uniform(0.0, cfg.window)
        sims.append((delay, sim))

    dashboard = Dashboard(metrics, cfg)
    done = asyncio.Event()
    live = asyncio.create_task(_live_loop(dashboard, window_deadline, done, cfg))

    tasks = [
        asyncio.create_task(_run_user(sim, cfg, sem, delay)) for delay, sim in sims
    ]
    # The run ends only when EVERY user has fully finished (may exceed the window
    # if a late starter is still processing) — matching the completion criteria.
    await asyncio.gather(*tasks)
    done.set()
    await live
    return metrics


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def write_csvs(metrics: Metrics, cfg: Config) -> tuple[Path, Path]:
    cfg.out_dir.mkdir(parents=True, exist_ok=True)
    ops_path = cfg.out_dir / f"operations_{cfg.run_id}.csv"
    summary_path = cfg.out_dir / f"summary_{cfg.run_id}.csv"

    with ops_path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            ["run_id", "user_idx", "username", "stage", "area", "method",
             "status_code", "ok", "latency_ms", "started_at", "error"]
        )
        for r in metrics.records:
            writer.writerow(
                [cfg.run_id, r.user_idx, r.username, r.stage, r.area, r.method,
                 r.status_code, int(r.ok), f"{r.latency_ms:.1f}",
                 f"{r.started_at:.3f}", r.error]
            )

    wall = time.time() - metrics.started_at
    with summary_path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["metric", "value"])
        rows = [
            ("run_id", cfg.run_id),
            ("target_users", cfg.users),
            ("window_seconds", f"{cfg.window:.0f}"),
            ("wall_clock_seconds", f"{wall:.1f}"),
            ("users_started", metrics.users_started),
            ("users_completed", metrics.users_completed),
            ("users_failed", metrics.users_failed),
            ("requests_total", metrics.requests_done),
            ("errors_total", metrics.errors),
            ("match_calls", metrics.match_done),
            ("matched_items_total", metrics.matched_total),
            ("llm_scores_total", metrics.llm_scores),
            ("fallback_scores_total", metrics.fallback_scores),
            ("embedding_generation_ops", metrics.embed_gen_done),
            ("embedding_filter_ops", metrics.embed_filter_done),
        ]
        for stage in (
            STAGE_CSRF, STAGE_REGISTER, STAGE_PROFILE, STAGE_SYNTHESIZE,
            STAGE_CONFIRM, STAGE_WATCH, STAGE_MATCH,
        ):
            n, mean, p95 = _stage_stats(metrics.latency_by_stage.get(stage, []))
            if n:
                rows.append((f"{stage}_count", n))
                rows.append((f"{stage}_mean_ms", f"{mean:.1f}"))
                rows.append((f"{stage}_p95_ms", f"{p95:.1f}"))
        for key, count in metrics.errors_by_key.most_common():
            rows.append((f"error[{key}]", count))
        writer.writerows(rows)

    return ops_path, summary_path


def diagnose(metrics: Metrics) -> list[str]:
    """Plain-language hints about *why* users failed, from the error mix."""
    hints: list[str] = []
    keys = metrics.errors_by_key
    if any("429" in k for k in keys):
        n = sum(v for k, v in keys.items() if "429" in k)
        hints.append(
            f"{n} request(s) were throttled (HTTP 429). The register endpoint "
            "caps anonymous signups (default 20/hour). Start the backend with "
            "DJANGO_REGISTER_THROTTLE_RATE set high, e.g. 1000000/hour."
        )
    if any("403" in k for k in keys):
        n = sum(v for k, v in keys.items() if "403" in k)
        hints.append(
            f"{n} request(s) got HTTP 403 (often a CSRF failure) — the base URL "
            "host may not be a trusted origin, or the csrf cookie/header was not "
            "sent. Check CSRF_TRUSTED_ORIGINS and that --base-url matches how the "
            "server is actually served."
        )
    if any(
        any(tok in k for tok in ("Timeout", "Connect", "Read", "Pool", "Remote"))
        for k in keys
    ):
        hints.append(
            "Connection/timeout errors — the server or client is saturated. Lower "
            "--max-concurrency, raise --request-timeout, or widen the --window."
        )
    if any("400" in k and "register" in k for k in keys):
        hints.append(
            "400 at register — likely duplicate usernames/emails from a prior run "
            "left in the DB. Purge old load-test users (loadtest_purge) or use a "
            "fresh --run-id."
        )
    return hints


def build_summary_lines(
    metrics: Metrics, cfg: Config, ops_path: Path, summary_path: Path
) -> list[str]:
    """The full summary as text lines (shared by the console and the log)."""
    wall = time.time() - metrics.started_at
    line = "=" * 64
    out = [
        line,
        f" LOAD TEST SUMMARY · run {cfg.run_id}",
        line,
        f" Target users            {cfg.users}",
        f" Completed               {metrics.users_completed}"
        f"  ({_pct(metrics.users_completed, cfg.users):.1f}%)",
        f" Failed (users)          {metrics.users_failed}",
        f" Wall-clock              {_fmt_dur(wall)}  (window {_fmt_dur(cfg.window)})",
        f" Total requests          {metrics.requests_done}",
        f" Total errors            {metrics.errors}",
        f" Match (LLM) calls       {metrics.match_done}",
        f"   matched items         {metrics.matched_total}",
        f"   genuine LLM scores    {metrics.llm_scores}",
        f"   deterministic fallbk  {metrics.fallback_scores}",
        f" Embedding generation    {metrics.embed_gen_done}",
        f" Embedding filter/search {metrics.embed_filter_done}",
        f" Throughput              "
        f"{(metrics.users_completed / wall * 60.0) if wall else 0:.1f} users/min · "
        f"{(metrics.requests_done / wall) if wall else 0:.1f} req/s",
        line,
        f" {'stage':<12}{'count':>7}{'mean ms':>10}{'p95 ms':>10}{'max ms':>10}",
    ]
    for stage in (
        STAGE_CSRF, STAGE_REGISTER, STAGE_PROFILE, STAGE_SYNTHESIZE,
        STAGE_CONFIRM, STAGE_WATCH, STAGE_MATCH,
    ):
        samples = metrics.latency_by_stage.get(stage, [])
        n, mean, p95 = _stage_stats(samples)
        if n:
            out.append(f" {stage:<12}{n:>7}{mean:>10.0f}{p95:>10.0f}{max(samples):>10.0f}")
    if metrics.user_fail_stage:
        out.append(line)
        out.append(" User failures by stage:")
        for key, count in metrics.user_fail_stage.most_common():
            out.append(f"   {key:<40} {count}")
    if metrics.errors_by_key:
        out.append(line)
        out.append(" Error breakdown (stage + status):")
        for key, count in metrics.errors_by_key.most_common():
            out.append(f"   {key:<40} {count}")
    hints = diagnose(metrics)
    if hints:
        out.append(line)
        out.append(" Likely cause(s):")
        for hint in hints:
            out.append(f"   • {hint}")
    out.append(line)
    out.append(f" operations CSV : {ops_path}")
    out.append(f" summary CSV    : {summary_path}")
    out.append(f" run log        : {cfg.log_file}")
    out.append(line)
    return out


def print_summary(metrics: Metrics, cfg: Config, ops_path: Path, summary_path: Path) -> None:
    lines = build_summary_lines(metrics, cfg, ops_path, summary_path)
    print("\n" + "\n".join(lines) + "\n")
    # Mirror the whole summary into the run log so the file is self-contained.
    for text in lines:
        logger.info("%s", text)


# --------------------------------------------------------------------------- #
# Cleanup
# --------------------------------------------------------------------------- #
def cleanup_users(cfg: Config) -> None:
    """Delete the fake users via the loadtest_purge management command."""
    cmd = cfg.purge_cmd.split() + ["--run-id", cfg.run_id]
    print(f"Cleaning up fake users: {' '.join(cmd)}")
    logger.info("CLEANUP running: %s", " ".join(cmd))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except Exception as exc:
        print(f"  cleanup FAILED to launch: {exc}", file=sys.stderr)
        print(f"  Run manually: {' '.join(cmd)}", file=sys.stderr)
        logger.error("CLEANUP failed to launch: %s — run manually: %s", exc, " ".join(cmd))
        return
    out = (result.stdout or "").strip()
    err = (result.stderr or "").strip()
    if out:
        print(f"  {out}")
    if result.returncode != 0:
        print(f"  cleanup command exited {result.returncode}", file=sys.stderr)
        if err:
            print(f"  {err}", file=sys.stderr)
        print(f"  Run manually: {' '.join(cmd)}", file=sys.stderr)
        logger.error("CLEANUP exited %s: %s", result.returncode, err or out)
    else:
        logger.info("CLEANUP ok: %s", out)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def parse_window(value: str) -> float:
    """Parse a window like '30m', '90s', '1h', or a bare number of seconds."""
    v = value.strip().lower()
    try:
        if v.endswith("ms"):
            return float(v[:-2]) / 1000.0
        if v.endswith("s"):
            return float(v[:-1])
        if v.endswith("m"):
            return float(v[:-1]) * 60.0
        if v.endswith("h"):
            return float(v[:-1]) * 3600.0
        return float(v)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"bad window {value!r}") from exc


def build_config(argv: list[str] | None = None) -> Config:
    p = argparse.ArgumentParser(
        description="Simulate concurrent user onboarding to stress-test the server.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--users", type=int, default=500, help="Number of fake users.")
    p.add_argument("--window", type=parse_window, default="30m",
                   help="Onboarding window (e.g. 30m, 90s, 1h, or seconds).")
    p.add_argument("--base-url", default="http://localhost:11350/api",
                   help="API base URL. Defaults to the compose backend published "
                        "on host :11350 (→ container :8000); hits Django directly.")
    p.add_argument("--max-concurrency", type=int, default=50,
                   help="Max simultaneous in-flight users.")
    p.add_argument("--seed", type=int, default=1337, help="RNG seed (reproducible).")
    p.add_argument("--all-categories-fraction", type=float, default=0.8,
                   help="Fraction of users who enable all four match areas.")
    p.add_argument("--synthesize", action="store_true",
                   help="Also POST a résumé to /intake/synthesize (extra LLM load).")
    p.add_argument("--out-dir", type=Path, default=Path("loadtest_results"),
                   help="Directory for the CSV reports.")
    p.add_argument("--run-id", default="",
                   help="Run identifier (used in usernames + filenames). Auto if blank.")
    p.add_argument("--request-timeout", type=float, default=120.0,
                   help="Per-request timeout in seconds.")
    p.add_argument("--refresh-interval", type=float, default=0.5,
                   help="Live dashboard refresh interval in seconds.")
    p.add_argument("--no-live", action="store_true",
                   help="Disable the in-place live table (print snapshots instead).")
    p.add_argument("--no-cleanup", action="store_true",
                   help="Do NOT delete the fake users at the end (purge manually).")
    p.add_argument("--purge-cmd",
                   default=("uv run --project web/backend python "
                            "web/backend/manage.py loadtest_purge"),
                   help="Command used to delete fake users after the run.")
    p.add_argument("--log-file", type=Path, default=None,
                   help="Run log path (default: <out-dir>/loadtest_<run-id>.log).")
    p.add_argument("--log-level", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                   help="File log verbosity. DEBUG also logs each successful request.")
    p.add_argument("--log-requests", action="store_true",
                   help="Log every request (not just failures) to the log file.")
    args = p.parse_args(argv)

    run_id = args.run_id.strip() or uuid.uuid4().hex[:8]
    log_file = args.log_file or (args.out_dir / f"loadtest_{run_id}.log")
    return Config(
        users=args.users,
        window=args.window,
        base_url=args.base_url.rstrip("/"),
        max_concurrency=max(1, args.max_concurrency),
        seed=args.seed,
        all_categories_fraction=min(1.0, max(0.0, args.all_categories_fraction)),
        synthesize=args.synthesize,
        out_dir=args.out_dir,
        run_id=run_id,
        request_timeout=args.request_timeout,
        no_live=args.no_live,
        cleanup=not args.no_cleanup,
        purge_cmd=args.purge_cmd,
        refresh_interval=max(0.1, args.refresh_interval),
        log_file=log_file,
        log_level=args.log_level,
        log_requests=args.log_requests,
    )


def setup_logging(cfg: Config) -> None:
    """Send the full run log to ``cfg.log_file`` (never to the console)."""
    cfg.log_file.parent.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if cfg.log_requests else getattr(
        logging, cfg.log_level.upper(), logging.INFO
    )
    logger.setLevel(level)
    logger.handlers.clear()
    handler = logging.FileHandler(cfg.log_file, mode="w", encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S")
    )
    logger.addHandler(handler)
    logger.propagate = False  # keep log lines out of the live console table


def main(argv: list[str] | None = None) -> int:
    cfg = build_config(argv)
    setup_logging(cfg)
    print(
        f"Load test · {cfg.users} users over {_fmt_dur(cfg.window)} · "
        f"run {cfg.run_id} · base {cfg.base_url}\n"
        f"Catalog: {len(CATALOG)} interests / {len(FIELDS)} fields · "
        f"concurrency {cfg.max_concurrency} · synthesize={cfg.synthesize}\n"
        f"Run log → {cfg.log_file}\n"
    )
    logger.info(
        "START run=%s users=%d window=%ss base=%s concurrency=%d "
        "synthesize=%s seed=%d all_categories_fraction=%.2f",
        cfg.run_id, cfg.users, int(cfg.window), cfg.base_url,
        cfg.max_concurrency, cfg.synthesize, cfg.seed, cfg.all_categories_fraction,
    )
    interrupted = False
    try:
        metrics = asyncio.run(run_load_test(cfg))
    except KeyboardInterrupt:
        print("\nInterrupted — reporting partial results and cleaning up.")
        logger.warning("INTERRUPTED by user (KeyboardInterrupt)")
        interrupted = True
        metrics = None  # type: ignore[assignment]

    if metrics is not None:
        ops_path, summary_path = write_csvs(metrics, cfg)
        print_summary(metrics, cfg, ops_path, summary_path)

    if cfg.cleanup:
        cleanup_users(cfg)
    else:
        print(f"Skipping cleanup (--no-cleanup). Purge later with:\n"
              f"  {cfg.purge_cmd} --run-id {cfg.run_id}")

    logger.info("END run=%s (see summary above)", cfg.run_id)
    print(f"Full run log: {cfg.log_file}")
    return 130 if interrupted else 0


if __name__ == "__main__":
    raise SystemExit(main())
