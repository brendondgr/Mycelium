"""The whole collection pipeline, in one importable module.

    main(["--domain", "conferences"])   # one domain
    main(["--skip-fetch"])              # re-run offline from stored payloads
    main(["--list-sources"])            # what is registered and usable

Four stages, in this order, over every registered source in the package:

    1. EXTRACTION    pull records from every source
    2. DEDUPLICATION collapse duplicates within and across sources
    3. NEW ITEMS     persist, and flag what had never been seen before
    4. VALIDATION    confirm the required fields actually came out of each item

This file orchestrates; it does not reimplement. The adapters, the dedupe
layers, and the registry resolver all live under ``apps.scraper.collect`` and
are imported as they are. What is added here is the cross-domain run order,
the new-item diff, the required-field validator, and the narration.

**The narration is a feature, not decoration.** Every line says what is
running, how it is being done, and where in the pipeline it sits, and every
quantity is reported as a running counter. A run that fails halfway must leave
behind a transcript from which the failure is obvious without re-running
anything.

There is deliberately no scheduler. A run runs once and returns; a Mycelium
management command decides when that happens.

**This module performs no LLM work at all.** Adapted from the standalone
``research-collector`` project's root ``pipeline.py`` (plan Phase 1), which
had *two* model-touching stages beyond the import rewrite:

* **The embedding stage is gone.** The original stage 5 embedded records
  straight from the collector's own SQLite stores, using ``rank.py``'s
  embedding-text composition — and ``rank.py`` was dropped when this was
  vendored (it pulled in the standalone project's whole retrieval engine,
  which Mycelium does not use; see ``grants/__init__.py``). Mycelium embeds in
  its own ingest step, after LLM extraction, once records have been mapped
  into ``ContentItem`` (plan D10, Phase 4) — a different pipeline entirely.
* **The enrichment stage is gone too.** The original stage 4 recovered
  missing descriptions, topics and deadlines by calling a local model server
  through a vendored ``_LLMClient``, configured from ``COLLECT_LLM_*``
  environment variables that named their own host and port
  (``http://localhost:9090/v1`` by default). That is a second, disagreeing
  LLM configuration sitting beside Mycelium's real one —
  ``settings.LLM_BASE_URL`` (``config/settings.py``), consumed through
  ``apps.core.llm.build_llm_client`` — and it probed a port nothing in this
  deployment serves. Per plan decision D9, every record's description is now
  produced by a *universal* structured-extraction stage that runs in
  Mycelium and drives ``apps.core.llm`` (plan Phase 8), not by a
  conferences-only, gap-gated pass living inside the vendored collector. The
  deterministic parts of that old stage — gap detection, page reduction, and
  above all the claim-by-claim ``verify()`` step that never trusted the
  model's word for anything checkable — stay in
  ``apps.scraper.collect.conferences.enrich`` for Phase 8 to reuse; only the
  parts that actually called a model came out. See that module's docstring.

Five stages (the original module docstring said "five" but never actually
counted enrichment, so it was really six) became four: extraction,
deduplication, new items, validation.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from apps.scraper.collect.conferences.adapters import (
    build_registry as conference_registry,
)
from apps.scraper.collect.grants.adapters import build_registry as grants_registry
from apps.scraper.collect.paths import DEFAULT_ROOT as _DEFAULT_ROOT

#: Re-exported so the many existing ``from ...runner import DEFAULT_ROOT``
#: imports keep working. See :mod:`apps.scraper.collect.paths` for why it is
#: anchored to the checkout rather than to the caller's working directory.
#: Callers that genuinely want another location still pass ``--root``.
DEFAULT_ROOT = _DEFAULT_ROOT

GRANTS, CONFERENCES = "grants", "conferences"
DOMAINS = (GRANTS, CONFERENCES)

STAGES = (
    "extraction",
    "deduplication",
    "new items",
    "validation",
)


# ═══════════════════════════════════════════════════════════════════════════
# Verbosity primitives
# ═══════════════════════════════════════════════════════════════════════════
#
# Every log line is built from the same three questions the run has to answer at
# all times: what is happening, how, and where. ``Console`` holds the "where" as
# state (set by ``stage`` and ``step``) so no call site can forget to say it, and
# formats every count identically so numbers can be compared down a column.


def plural(count: int, noun: str, suffix: str = "s") -> str:
    return f"{count:,} {noun}{'' if count == 1 else suffix}"


def humanize(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, rest = divmod(seconds, 60)
    return f"{int(minutes)}m{rest:04.1f}s"


class Stopwatch:
    """Elapsed time for a stage or a step. Started on construction."""

    def __init__(self) -> None:
        self.started = time.monotonic()

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started

    def __str__(self) -> str:
        return humanize(self.elapsed)


class Console:
    """Every line the pipeline prints goes through here.

    Three verbosity levels. ``quiet`` keeps stage banners and their summaries,
    which is the minimum from which a run can still be judged. ``normal`` is the
    default and narrates every source, every layer and every counter tick.
    ``verbose`` additionally prints per-record detail, which is only readable for
    a small run but is exactly what you want when one record is wrong.
    """

    QUIET, NORMAL, VERBOSE = 0, 1, 2
    WIDTH = 78

    def __init__(self, level: int = NORMAL, stream=None) -> None:
        self.level = level
        self.stream = stream or sys.stdout
        self.clock = Stopwatch()
        self.stage_label = "start"
        self.step_label = ""
        self.counts: dict[str, int] = {}

    # -- location ---------------------------------------------------------

    @property
    def location(self) -> str:
        """The "where in the pipeline" half of every line."""
        if self.step_label:
            return f"{self.stage_label}·{self.step_label}"
        return self.stage_label

    def _write(self, text: str = "") -> None:
        print(text, file=self.stream, flush=True)

    def _line(self, symbol: str, message: str) -> str:
        return f"{f'+{self.clock}':>9} {symbol} [{self.location}] {message}"

    # -- structure --------------------------------------------------------

    def banner(self, title: str, lines: list[str]) -> None:
        rule = "═" * self.WIDTH
        self._write(rule)
        self._write(f"  {title}")
        for line in lines:
            self._write(f"  {line}")
        self._write(rule)

    def stage(self, number: int, name: str, *, what: str, how: str, where: str) -> Stopwatch:
        """Open a stage. Returns its stopwatch so the caller can report duration."""
        self.stage_label = f"{number}/{len(STAGES)} {name}"
        self.step_label = ""
        self._write()
        self._write("┏" + "━" * (self.WIDTH - 1))
        self._write(f"┃ STAGE {number}/{len(STAGES)} · {name.upper()}")
        self._write(f"┃   what  : {what}")
        self._write(f"┃   how   : {how}")
        self._write(f"┃   where : {where}")
        self._write("┗" + "━" * (self.WIDTH - 1))
        return Stopwatch()

    def step(self, label: str, message: str = "") -> None:
        """Open a sub-step inside the current stage; it becomes part of `where`."""
        self.step_label = label
        if message and self.level >= self.NORMAL:
            self._write(self._line("▸", message))

    def endstep(self) -> None:
        self.step_label = ""

    # -- messages ---------------------------------------------------------

    def info(self, message: str) -> None:
        if self.level >= self.NORMAL:
            self._write(self._line("·", message))

    def detail(self, message: str) -> None:
        """Per-record narration. Only at -v; too loud for a full corpus."""
        if self.level >= self.VERBOSE:
            self._write(self._line(" ", f"  {message}"))

    def ok(self, message: str) -> None:
        if self.level >= self.NORMAL:
            self._write(self._line("✓", message))

    def warn(self, message: str) -> None:
        self._write(self._line("!", message))

    def error(self, message: str) -> None:
        self._write(self._line("✗", message))

    def summary(self, message: str) -> None:
        """Stage-level conclusion. Survives --quiet: it is the point of the stage."""
        self._write(self._line("=", message))

    # -- counters ---------------------------------------------------------

    @staticmethod
    def counter(done: int, total: int) -> str:
        """The `4/13` the request asks for, width-matched so columns line up."""
        width = len(f"{total:,}")
        return f"[{done:>{width},}/{total:,}]"

    def item(self, done: int, total: int, label: str, message: str) -> None:
        """One numbered unit of work — a source, a batch, a domain."""
        if self.level >= self.NORMAL:
            self._write(self._line("·", f"{self.counter(done, total)} {label:<18} {message}"))

    def progress(self, done: int, total: int, noun: str, *, every: int = 0) -> None:
        """A running counter inside a long loop.

        Printed on a cadence rather than per record: 12,000 lines is not
        verbosity, it is a wall. The first and last tick always print, so the
        counter both starts and finishes visibly.
        """
        if self.level < self.NORMAL or total <= 0:
            return
        every = every or max(1, total // 20)
        if done != total and done % every != 0 and done != 1:
            return
        percent = 100 * done / total
        self._write(self._line(" ", f"  {self.counter(done, total)} {noun} ({percent:.0f}%)"))

    def table(self, headers: list[str], rows: list[list[str]]) -> None:
        """A fixed-width table, because a column of numbers is read by eye."""
        if self.level < self.NORMAL or not rows:
            return
        widths = [
            max(len(str(headers[i])), *(len(str(row[i])) for row in rows))
            for i in range(len(headers))
        ]
        head = "  ".join(str(h).ljust(widths[i]) for i, h in enumerate(headers))
        self._write(self._line(" ", f"  {head}"))
        self._write(self._line(" ", f"  {'  '.join('-' * w for w in widths)}"))
        for row in rows:
            body = "  ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row))
            self._write(self._line(" ", f"  {body}"))


# ═══════════════════════════════════════════════════════════════════════════
# Run context
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class RunContext:
    """Everything a stage needs, plus the report every stage writes into."""

    run_id: str
    started_at: str
    root: Path
    domains: list[str]
    console: Console
    sources: dict[str, list[str]] = field(default_factory=dict)
    limit: int | None = None
    skip_fetch: bool = False
    #: The run the user asked to replay, or None for "the latest on disk". Kept
    #: apart from ``run_id`` because a fresh run always has an id and replaying
    #: one that was never fetched must resolve to LATEST rather than to nothing.
    requested_run_id: str | None = None
    min_interval: float = 0.5
    now: datetime | None = None
    report: dict[str, Any] = field(default_factory=dict)

    @property
    def grants_db(self) -> Path:
        return self.root / "opportunities.db"

    @property
    def conferences_db(self) -> Path:
        return self.root / "conferences.db"

    @property
    def report_path(self) -> Path:
        return self.root / "pipeline-runs" / f"{self.run_id}.json"

    def stage_report(self, name: str) -> dict[str, Any]:
        return self.report.setdefault("stages", {}).setdefault(name, {})


# ═══════════════════════════════════════════════════════════════════════════
# Source enumeration
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class SourceInfo:
    domain: str
    name: str
    phase: int
    native: bool
    license: str
    enabled: bool
    reason: str


def all_sources() -> list[SourceInfo]:
    """Every adapter registered anywhere in the repo, both domains, in run order."""
    out: list[SourceInfo] = []
    for name, adapter in sorted(grants_registry().items(), key=lambda kv: kv[1].phase):
        enabled, reason = adapter.available()
        out.append(
            SourceInfo(
                domain=GRANTS,
                name=name,
                phase=adapter.phase,
                native=bool(getattr(adapter, "funder_native", False)),
                license=getattr(adapter, "license", "") or "",
                enabled=enabled,
                reason=reason,
            )
        )
    for name, adapter in sorted(conference_registry().items(), key=lambda kv: kv[1].phase):
        enabled, reason = adapter.available()
        out.append(
            SourceInfo(
                domain=CONFERENCES,
                name=name,
                phase=adapter.phase,
                native=bool(getattr(adapter, "venue_native", False)),
                license=getattr(adapter, "license", "") or "",
                enabled=enabled,
                reason=reason,
            )
        )
    return out


def sources_for(domains: list[str], selected: list[str]) -> dict[str, list[str]]:
    """Resolve the CLI's domain and source filters to a per-domain name list."""
    by_name: dict[str, list[str]] = {}
    for info in all_sources():
        by_name.setdefault(info.name, []).append(info.domain)

    if selected:
        unknown = [name for name in selected if name not in by_name]
        if unknown:
            raise SystemExit(f"unknown source(s): {', '.join(sorted(unknown))}")

    out: dict[str, list[str]] = {}
    for domain in domains:
        names = [
            info.name
            for info in all_sources()
            if info.domain == domain and (not selected or info.name in selected)
        ]
        if names:
            out[domain] = names
    if selected and not out:
        raise SystemExit("the selected sources are not in the selected domain(s)")
    return out


def list_sources(console: Console) -> int:
    """`--list-sources`: what exists, in what order it runs, and what is off."""
    infos = all_sources()
    console.banner(
        f"{len(infos)} registered sources",
        [
            f"{sum(1 for i in infos if i.enabled)} usable now, "
            f"{sum(1 for i in infos if not i.enabled)} disabled",
            "run order is domain, then build phase",
        ],
    )
    rows = [
        [
            info.domain,
            f"P{info.phase}",
            info.name,
            "native" if info.native else "aggregator",
            (info.license[:24] + "…") if len(info.license) > 25 else (info.license or "-"),
            "ready" if info.enabled else f"disabled: {info.reason[:40]}",
        ]
        for info in infos
    ]
    console.table(["domain", "phase", "source", "kind", "license", "state"], rows)
    return 0


# ═══════════════════════════════════════════════════════════════════════════
# Stage 1 — Extraction
# ═══════════════════════════════════════════════════════════════════════════
#
# fetch → parse → normalize, and for conferences → resolve. The fetch/parse seam
# is preserved exactly as the per-domain pipelines define it: fetch is the only
# thing that touches the network, parse reads nothing but disk. That is what lets
# --skip-fetch replay a whole run offline.
#
# The per-source loop is written out here rather than delegated to
# ``Pipeline.fetch``, which loops internally and reports only totals. Same calls,
# same error isolation, same raw-store writes — but one narrated line per source,
# which is the entire point of this file.


@dataclass
class DomainData:
    """One domain's records as they move through the stages."""

    domain: str
    #: Grants: Opportunity records. Conferences: ConferenceInstance records.
    items: list[Any] = field(default_factory=list)
    #: Conferences only. Identity and trust live on the series, never the instance.
    series: list[Any] = field(default_factory=list)
    fetched: dict[str, int] = field(default_factory=dict)
    parsed: dict[str, int] = field(default_factory=dict)
    errors: list[tuple[str, str, str]] = field(default_factory=list)
    resolve_report: Any = None
    dedupe_report: Any = None
    dedupe_in: int = 0
    unresolved_overlays: int = 0
    new_keys: list[str] = field(default_factory=list)
    pipeline: Any = None
    run_id: str = ""

    @property
    def noun(self) -> str:
        return "opportunity record" if self.domain == GRANTS else "conference instance"


def _grants_pipeline(context: RunContext):
    from apps.scraper.collect.grants.pipeline import CollectConfig, Pipeline

    return Pipeline(
        CollectConfig(
            root=context.root,
            sources=list(context.sources.get(GRANTS, [])),
            limit=context.limit,
            offline=context.skip_fetch,
            min_interval=context.min_interval,
        )
    )


def _conferences_pipeline(context: RunContext):
    from apps.scraper.collect.conferences.pipeline import (
        ConferenceConfig,
        ConferencePipeline,
    )

    return ConferencePipeline(
        ConferenceConfig(
            root=context.root,
            sources=list(context.sources.get(CONFERENCES, [])),
            limit=context.limit,
            offline=context.skip_fetch,
            min_interval=context.min_interval,
        )
    )


def _fetch_domain(context: RunContext, data: DomainData, position: list[int], total: int) -> None:
    """Stage 1.1 for one domain. Network only; one dead source never sinks the run."""
    console = context.console
    pipeline = data.pipeline
    console.step(f"1.1 fetch · {data.domain}")

    if context.skip_fetch:
        resolved = pipeline.raw_store.resolve(context.requested_run_id)
        if resolved is None:
            # Reported, not raised. The other domain may well have payloads, and
            # one empty raw store is not a reason to abandon the whole run.
            data.errors.append(
                (data.domain, "fetch", f"no raw payloads under {pipeline.raw_store.root}")
            )
            console.warn(
                f"--skip-fetch: nothing stored under {pipeline.raw_store.root}; "
                f"the {data.domain} domain will contribute no records"
            )
            return
        data.run_id = resolved
        console.info(f"offline replay of stored run {resolved}; no requests will be made")
        return

    client = pipeline.client()
    data.run_id = context.run_id
    for name in context.sources[data.domain]:
        position[0] += 1
        adapter = pipeline.registry[name]
        enabled, reason = adapter.available()
        if not enabled:
            data.errors.append((name, "fetch", f"disabled: {reason}"))
            console.item(position[0], total, name, f"skipped — {reason[:60]}")
            continue

        watch = Stopwatch()
        try:
            bundle = adapter.fetch(client, limit=context.limit)
        except Exception as exc:  # noqa: BLE001 — isolation is the whole point
            # Deliberately every exception, not a curated tuple. A source that
            # starts serving malformed XML raises ParseError, which is a
            # SyntaxError and therefore escapes (FetchError, RuntimeError,
            # ValueError, OSError) — one upstream feed breaking then takes down
            # the other twelve sources, which is exactly what this must prevent.
            data.errors.append((name, "fetch", f"{type(exc).__name__}: {exc}"))
            console.item(
                position[0], total, name, f"FAILED after {watch} — {type(exc).__name__}: {exc}"
            )
            continue

        # The adapter stamps its own run id; the run's id wins so every source in
        # this run lands in one directory and can be replayed together.
        bundle = type(bundle)(
            source=bundle.source,
            run_id=data.run_id,
            fetched_at=bundle.fetched_at,
            records=bundle.records,
            meta=bundle.meta,
        )
        pipeline.raw_store.write(bundle)
        data.fetched[name] = len(bundle.records)
        console.item(
            position[0], total, name,
            f"{plural(len(bundle.records), 'raw record')} in {watch} "
            f"→ {pipeline.raw_store.root / data.run_id}",
        )


def _parse_domain(context: RunContext, data: DomainData, position: list[int], total: int) -> None:
    """Stage 1.2 for one domain. Reads disk, touches no network, ever."""
    console = context.console
    pipeline = data.pipeline
    console.step(f"1.2 parse · {data.domain}")

    resolved = pipeline.raw_store.resolve(data.run_id or None)
    if resolved is None:
        # Every source in this domain failed to fetch, or none has ever run.
        # The other domain's records are still perfectly good.
        console.warn(
            f"no raw payloads on disk under {pipeline.raw_store.root}; "
            f"nothing to parse for {data.domain}"
        )
        return
    data.run_id = resolved

    wanted = set(context.sources[data.domain])
    available = [n for n in pipeline.raw_store.sources_in(resolved) if n in wanted]
    missing = sorted(wanted - set(available))
    for name in missing:
        console.warn(f"{name}: no raw payload in run {resolved}; nothing to parse")

    for name in available:
        position[0] += 1
        bundle = pipeline.raw_store.read(resolved, name)
        if bundle is None:
            console.item(position[0], total, name, "raw payload unreadable; skipped")
            continue
        watch = Stopwatch()
        try:
            parsed = pipeline.registry[name].parse(bundle)
        except Exception as exc:  # noqa: BLE001 — one adapter's bug is not fatal
            data.errors.append((name, "parse", f"{type(exc).__name__}: {exc}"))
            console.item(position[0], total, name, f"PARSE FAILED — {type(exc).__name__}: {exc}")
            continue

        if data.domain == CONFERENCES:
            series, instances = parsed
            data.series.extend(series)
            data.items.extend(instances)
            count = len(instances)
            extra = f" and {len(series):,} series"
            emitted = instances
        else:
            data.items.extend(parsed)
            count = len(parsed)
            extra = ""
            emitted = parsed
        data.parsed[name] = count
        console.item(
            position[0], total, name,
            f"{len(bundle.records):,} raw → {plural(count, data.noun)}{extra} in {watch}",
        )
        for record in emitted:
            console.detail(f"{name}: {getattr(record, 'title', '')[:70]}")


def _normalize_domain(context: RunContext, data: DomainData) -> None:
    """Stage 1.3. A pure transformation; the only stage that may drop a record."""
    console = context.console
    console.step(f"1.3 normalize · {data.domain}")
    before = len(data.items)
    watch = Stopwatch()

    if data.domain == GRANTS:
        data.items = data.pipeline.normalize(data.items)
        dropped_because = "already closed, or an empty husk"
    else:
        data.series, data.items = data.pipeline.normalize(data.series, data.items)
        dropped_because = "an empty husk (past instances are kept, never dropped)"

    dropped = before - len(data.items)
    console.info(
        f"{before:,} in → {len(data.items):,} out "
        f"({dropped:,} dropped: {dropped_because}) in {watch}"
    )


def _resolve_domain(context: RunContext, data: DomainData) -> None:
    """Stage 1.4, conferences only: registry join, series keys, trust tiers.

    Not one of the five named stages, and deliberately not silent either. Dedupe
    keys on ``series_key``, which does not exist until this runs, so skipping it
    would not speed the run up — it would corrupt stage 2.
    """
    console = context.console
    console.step("1.4 resolve · conferences")

    from apps.scraper.collect.conferences.registry.cache import RegistryCache

    if not RegistryCache(data.pipeline.config.registry_dir).available:
        # Without the cache every series resolves to nothing, which is not an
        # error but does silently cost the whole tier-A signal. Say so.
        console.warn(
            f"no registry cache under {data.pipeline.config.registry_dir} — every series "
            "will be unresolved and no venue can reach tier A. Build it with: "
            "python -m apps.scraper.collect.conferences registry"
        )

    watch = Stopwatch()
    data.series, data.items, report = data.pipeline.resolve(data.series, data.items)
    data.resolve_report = report
    console.info(f"{report.summary()} in {watch}")
    ambiguous = [s for s in data.series if getattr(s, "dblp_candidates", None)]
    if ambiguous:
        console.warn(
            f"{len(ambiguous):,} series matched more than one registry venue and were "
            f"left unresolved rather than guessed (e.g. {ambiguous[0].acronym})"
        )


def stage_extract(context: RunContext) -> dict[str, DomainData]:
    console = context.console
    total = sum(len(names) for names in context.sources.values())
    watch = console.stage(
        1, "extraction",
        what=f"pull records from all {total} registered sources",
        how="fetch (HTTP, rate-limited) → parse (offline) → normalize"
            + (" → resolve" if CONFERENCES in context.sources else ""),
        where="runner.py → stage_extract()",
    )

    data: dict[str, DomainData] = {}
    fetch_position, parse_position = [0], [0]

    for domain in context.domains:
        data[domain] = DomainData(domain=domain)
        data[domain].pipeline = (
            _grants_pipeline(context) if domain == GRANTS else _conferences_pipeline(context)
        )

    for domain in context.domains:
        _fetch_domain(context, data[domain], fetch_position, total)
    for domain in context.domains:
        _parse_domain(context, data[domain], parse_position, total)
        _normalize_domain(context, data[domain])
        if domain == CONFERENCES:
            _resolve_domain(context, data[domain])

    console.endstep()
    report = context.stage_report("extraction")
    for domain, payload in data.items():
        report[domain] = {
            "run_id": payload.run_id,
            "fetched": payload.fetched,
            "parsed": payload.parsed,
            "normalized": len(payload.items),
            "series": len(payload.series),
            "errors": [list(e) for e in payload.errors],
        }
    report["seconds"] = round(watch.elapsed, 2)

    ok = sum(len(d.parsed) for d in data.values())
    failed = sum(len(d.errors) for d in data.values())
    extracted = sum(len(d.items) for d in data.values())
    for domain, payload in data.items():
        for source, stage, message in payload.errors:
            console.error(f"{domain}/{source} [{stage}] {message}")
    console.summary(
        f"stage 1 complete in {watch}: {console.counter(ok, total)} sources produced records, "
        f"{failed} problem(s), {extracted:,} records normalized"
    )
    return data


# ═══════════════════════════════════════════════════════════════════════════
# Stage 2 — Deduplication
# ═══════════════════════════════════════════════════════════════════════════
#
# The layers themselves are not reimplemented here; they are tested where they
# live. What this stage adds is an account of what they did, layer by layer,
# because "in 4,734 out 3,912" tells you a number and nothing about whether the
# right thing happened.
#
# One invariant is worth restating every run, so it is printed every run: the
# fuzzy layer (3 for grants, 4 for conferences) **flags and never merges**. A
# fuzzy match is a suggestion for a human, not a decision.


def _dedupe_grants(context: RunContext, data: DomainData) -> None:
    from apps.scraper.collect.grants.dedupe import deduplicate, resolve_overlay_parents

    console = context.console
    console.step("2.1 dedupe · grants")
    before = len(data.items)
    watch = Stopwatch()

    merged, report = deduplicate(data.items)
    unresolved = resolve_overlay_parents(merged)
    data.items = merged
    data.dedupe_report = report

    console.info(f"layer 1  within one source, by (source, record id)   collapsed {report.layer1_collapsed:,}")
    console.info(f"layer 2  across sources, by funder-assigned number   merged    {report.layer2_merged:,}")
    console.info(f"layer 3  fuzzy title+funder — FLAGS, NEVER MERGES    flagged   {report.layer3_flagged:,}")
    console.info(f"overlays pointing at a parent we could not resolve   {unresolved:,}")
    console.info(f"{before:,} in → {len(data.items):,} out ({before - len(data.items):,} collapsed) in {watch}")
    data.unresolved_overlays = unresolved


def _dedupe_conferences(context: RunContext, data: DomainData) -> None:
    from apps.scraper.collect.conferences.dedupe import deduplicate

    console = context.console
    console.step("2.2 dedupe · conferences")
    before_series, before = len(data.series), len(data.items)
    watch = Stopwatch()

    data.series, data.items, report = deduplicate(data.series, data.items)
    data.dedupe_report = report

    console.info(f"layer 1  within one source, by (source, record id)   collapsed {report.layer1_collapsed:,}")
    console.info(f"layer 2  by series key + edition                     merged    {report.layer2_merged:,}")
    console.info(f"layer 3  by event dates + place                      merged    {report.layer3_merged:,}")
    console.info(f"layer 4  fuzzy — FLAGS FOR REVIEW, NEVER MERGES      flagged   {report.layer4_flagged:,}")
    console.info(f"series    {before_series:,} in → {len(data.series):,} out")
    console.info(f"instances {before:,} in → {len(data.items):,} out "
                 f"({before - len(data.items):,} collapsed) in {watch}")


def stage_deduplicate(context: RunContext, data: dict[str, DomainData]) -> None:
    console = context.console
    total_in = sum(len(d.items) for d in data.values())
    watch = console.stage(
        2, "deduplication",
        what=f"collapse duplicates across {total_in:,} extracted records",
        how="exact keys first, then identifier match, then a fuzzy layer that only flags",
        where="runner.py → stage_deduplicate() → apps.scraper.collect.{grants,conferences}.dedupe",
    )

    for domain in context.domains:
        data[domain].dedupe_in = len(data[domain].items)
        if domain == GRANTS:
            _dedupe_grants(context, data[domain])
        else:
            _dedupe_conferences(context, data[domain])

    console.endstep()
    total_out = sum(len(d.items) for d in data.values())
    report = context.stage_report("deduplication")
    for domain, payload in data.items():
        report[domain] = {
            "summary": payload.dedupe_report.summary() if payload.dedupe_report else "",
            "in": payload.dedupe_in,
            "out": len(payload.items),
            "flagged_for_review": sum(
                1 for item in payload.items if getattr(item, "review_candidates", None)
            ),
        }
    report["seconds"] = round(watch.elapsed, 2)

    flagged = sum(r["flagged_for_review"] for r in report.values() if isinstance(r, dict))
    console.summary(
        f"stage 2 complete in {watch}: {total_in:,} → {total_out:,} records "
        f"({total_in - total_out:,} duplicates collapsed, {flagged:,} flagged for human review)"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Stage 3 — New-item flagging
# ═══════════════════════════════════════════════════════════════════════════
#
# "New" is defined as *the key was not in the store before this run's persist*,
# not as ``first_seen == today``. The difference matters: first_seen is a
# timestamp written by the store and survives re-imports, clock skew and manual
# edits, whereas a key snapshot taken moments before the upsert answers exactly
# the question downstream is asking — what appeared that I have not seen?
#
# The keys are written to a ``new_items`` table in the same database, so the
# ranking and web layers can join against them without re-deriving anything.

#: How many new keys the JSON report carries inline. The full set is in the table.
NEW_KEY_SAMPLE = 500

NEW_ITEMS_SCHEMA = """
CREATE TABLE IF NOT EXISTS new_items (
    item_key   TEXT NOT NULL,
    run_id     TEXT NOT NULL,
    flagged_at TEXT NOT NULL,
    source     TEXT,
    title      TEXT,
    PRIMARY KEY (item_key, run_id)
);
CREATE INDEX IF NOT EXISTS idx_new_items_run ON new_items(run_id);
"""


def _existing_keys(conn, table: str, column: str) -> set[str]:
    """The key set as it stands *before* the upsert. This is the whole mechanism."""
    return {row[0] for row in conn.execute(f"SELECT {column} FROM {table}")}


def _record_new_items(conn, run_id: str, records: list[Any], key_of, new_keys: set[str]) -> None:
    conn.executescript(NEW_ITEMS_SCHEMA)
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    conn.executemany(
        "INSERT OR REPLACE INTO new_items (item_key, run_id, flagged_at, source, title) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            (key_of(record), run_id, stamp, record.source, getattr(record, "title", ""))
            for record in records
            if key_of(record) in new_keys
        ],
    )
    conn.commit()


def _persist_grants(context: RunContext, data: DomainData) -> dict[str, Any]:
    from apps.scraper.collect.grants.store import Store

    console = context.console
    console.step("3.1 persist + flag · grants")

    with Store(context.grants_db) as store:
        before = _existing_keys(store.conn, "opportunities", "stable_key")
        console.info(f"store held {len(before):,} records before this run ({context.grants_db})")

        watch = Stopwatch()
        stats = store.upsert_all(data.items)
        console.info(
            f"upsert  inserted={stats.inserted:,} updated={stats.updated:,} "
            f"unchanged={stats.unchanged:,} in {watch}"
        )

        indexed = store.rebuild_search_index()
        console.info(f"rebuilt the full-text index over {indexed:,} rows")

        # A replay is not evidence about what a source currently lists, so it may
        # not be used to delete anything. A live, uncapped run may.
        removed = 0
        if context.skip_fetch:
            console.info("vacuum  skipped: --skip-fetch replays old payloads and cannot "
                         "prove a record was withdrawn")
        elif context.limit is not None:
            console.info(f"vacuum  skipped: --limit {context.limit} means the key set is truncated")
        else:
            failed = {source for source, _, _ in data.errors}
            complete = [name for name in data.parsed if name not in failed]
            if complete:
                removed = store.vacuum(complete, {r.stable_key for r in data.items})
                console.info(
                    f"vacuum  removed {removed:,} no longer listed by "
                    f"{len(complete)} complete source(s): {', '.join(complete)}"
                )
            else:
                console.info("vacuum  skipped: no source completed, so nothing is provably gone")

        pruned = store.prune()
        console.info(f"prune   removed {pruned:,} whose every round has passed")

        after = _existing_keys(store.conn, "opportunities", "stable_key")
        new_keys = after - before
        data.new_keys = sorted(new_keys)
        _record_new_items(
            store.conn, context.run_id, data.items, lambda r: r.stable_key, new_keys
        )

    console.ok(
        f"{len(new_keys):,} genuinely new of {len(data.items):,} presented "
        f"({100 * len(new_keys) / max(1, len(data.items)):.1f}%); "
        f"store now holds {len(after):,}"
    )
    for record in data.items:
        if record.stable_key in new_keys:
            console.detail(f"NEW {record.stable_key}  {record.title[:60]}")
    return {
        "inserted": stats.inserted, "updated": stats.updated, "unchanged": stats.unchanged,
        "vacuumed": removed, "pruned": pruned,
        "new_items": len(new_keys), "store_size": len(after),
    }


def _persist_conferences(context: RunContext, data: DomainData) -> dict[str, Any]:
    from apps.scraper.collect.conferences.store import ConferenceStore

    console = context.console
    console.step("3.2 persist + flag · conferences")
    now = context.now or datetime.now(UTC)

    with ConferenceStore(context.conferences_db) as store:
        before = _existing_keys(store.conn, "instances", "instance_key")
        console.info(
            f"store held {len(before):,} instances before this run ({context.conferences_db})"
        )

        watch = Stopwatch()
        series_stats = store.upsert_series(data.series)
        console.info(
            f"series    inserted={series_stats.inserted:,} updated={series_stats.updated:,} "
            f"unchanged={series_stats.unchanged:,}"
        )
        stats = store.upsert_instances(data.items)
        console.info(
            f"instances inserted={stats.inserted:,} updated={stats.updated:,} "
            f"unchanged={stats.unchanged:,} extensions={stats.extensions:,} in {watch}"
        )

        # Nothing is ever deleted here. Past instances are the longevity signal
        # the trust tier reads, and next year's deadline is predicted from them.
        deactivated = store.mark_inactive(now)
        quarantined = store.quarantined_count()
        console.info(
            f"inactive  {deactivated:,} instances flipped to inactive — retained, never deleted"
        )
        if quarantined:
            console.info(f"tier C    {quarantined:,} instances withheld from default output, counted")

        after = _existing_keys(store.conn, "instances", "instance_key")
        new_keys = after - before
        data.new_keys = sorted(new_keys)
        _record_new_items(
            store.conn, context.run_id, data.items, lambda r: r.instance_key, new_keys
        )

    console.ok(
        f"{len(new_keys):,} genuinely new of {len(data.items):,} presented "
        f"({100 * len(new_keys) / max(1, len(data.items)):.1f}%); "
        f"store now holds {len(after):,}"
    )
    for record in data.items:
        if record.instance_key in new_keys:
            console.detail(f"NEW {record.instance_key}  {record.title[:60]}")
    return {
        "series_inserted": series_stats.inserted, "series_updated": series_stats.updated,
        "inserted": stats.inserted, "updated": stats.updated, "unchanged": stats.unchanged,
        "extensions": stats.extensions, "deactivated": deactivated, "quarantined": quarantined,
        "new_items": len(new_keys), "store_size": len(after),
    }


def stage_flag_new(context: RunContext, data: dict[str, DomainData]) -> None:
    console = context.console
    watch = console.stage(
        3, "new items",
        what="persist every record, then flag the ones never seen before",
        how="snapshot the store's key set, upsert, diff — the difference is what is new",
        where="runner.py → stage_flag_new() → new_items table in each database",
    )

    report = context.stage_report("new items")
    for domain in context.domains:
        report[domain] = (
            _persist_grants(context, data[domain]) if domain == GRANTS
            else _persist_conferences(context, data[domain])
        )
        # A sample, not the whole list: the authoritative set is the new_items
        # table, and a first run would otherwise put 4,000 keys in a JSON file
        # nobody reads that far into.
        keys = data[domain].new_keys
        report[domain]["new_keys_sample"] = keys[:NEW_KEY_SAMPLE]
        report[domain]["new_keys_truncated"] = len(keys) > NEW_KEY_SAMPLE
        report[domain]["new_keys_table"] = "new_items"

    console.endstep()
    report["seconds"] = round(watch.elapsed, 2)
    total_new = sum(len(d.new_keys) for d in data.values())
    console.summary(
        f"stage 3 complete in {watch}: {total_new:,} new items flagged across "
        f"{len(context.domains)} domain(s), recorded under run {context.run_id}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Concurrency helper
# ═══════════════════════════════════════════════════════════════════════════
#
# This pipeline used to run a fourth stage here — website enrichment, calling a
# local model server through a vendored ``_LLMClient`` configured from
# ``COLLECT_LLM_*`` environment variables. It is gone: per plan decision D9 that
# work is now a universal structured-extraction stage that runs in Mycelium and
# drives ``apps.core.llm`` (plan Phase 8), not a conferences-only pass living
# inside the vendored collector with its own, disagreeing LLM configuration.
# The deterministic half of that old stage — gap detection, page reduction, and
# the claim-by-claim ``verify()`` that never trusted the model's word for
# anything checkable — stays in ``apps.scraper.collect.conferences.enrich`` for
# Phase 8 to reuse; see that module's docstring. Only the parts that actually
# called a model came out.
#
# ``_HostLocks`` outlives that stage because it was never LLM-specific: it is a
# per-host lock so concurrent fetches cannot become concurrent rudeness, and the
# plan's own fetch-stage parallelism (Phase 7) and Phase 8's website fetch both
# need exactly this.


class _HostLocks:
    """One lock per host, so concurrency cannot become rudeness.

    Sixteen workers against a list of a thousand mostly-distinct conference sites
    is sixteen different hosts nearly all of the time. Nearly is not always: a
    society running six of its conferences on one domain would otherwise get six
    simultaneous requests, and the per-host interval that exists to prevent
    exactly that is enforced per *request*, not per caller.
    """

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}

    def for_url(self, url: str) -> threading.Lock:
        from apps.scraper.collect.core.http import _host_of

        host = _host_of(url)
        with self._guard:
            return self._locks.setdefault(host, threading.Lock())


# ═══════════════════════════════════════════════════════════════════════════
# Stage 4 — Field validation
# ═══════════════════════════════════════════════════════════════════════════
#
# The required fields, in the priority order the brief sets:
#
#     1. Name          what the thing is called
#     2. Description    what it is actually about
#     3. Deadlines      when you have to act
#     4. Tags           subject terms; welcome, not required
#
# Presence is the floor, not the bar. A title of "N/A", a description reading
# "see the announcement", a deadline with no timezone basis and a category list
# holding eligibility prose are all *present* and none of them is extracted
# correctly, so each rule checks usability rather than non-emptiness.
#
# Rules are pure functions over a record. That is what lets a test prove a rule
# fires before the run is entitled to trust its silence.

# One definition, imported rather than restated: the enrichment layer decides
# what to go and fetch from exactly these predicates, so if they lived in two
# places the two would eventually disagree about what "missing" means and the
# fetcher would chase gaps the validator does not report.
#
# Five statements, not one: ruff's isort defaults to `combine-as-imports =
# false` (a repo-wide setting, not overridden here for one call site), which
# refuses to combine plain names with `as`-aliased ones — or multiple
# `as`-aliases from the same module — into a single `from ... import (...)`.
# Each therefore needs its own E402 suppression; the position is deliberate
# (import-near-use, right beside the rules that are its only callers) rather
# than an oversight, which is what E402 exists to flag.
from apps.scraper.collect.conferences.enrich import (  # noqa: E402
    MIN_DESCRIPTION_CHARS,
    MIN_VENUE_NAME_CHARS,
)
from apps.scraper.collect.conferences.enrich import (  # noqa: E402
    describes_something as _describes_something,
)
from apps.scraper.collect.conferences.enrich import (  # noqa: E402
    has_description as _conference_description_ok,
)
from apps.scraper.collect.conferences.enrich import (  # noqa: E402
    has_usable_deadline as _conference_deadline_ok,
)
from apps.scraper.collect.conferences.enrich import (  # noqa: E402
    text_ok as _text_ok,
)


@dataclass(frozen=True)
class FieldRule:
    """One required field, and what it means for it to have come out correctly."""

    field: str
    priority: int
    required: bool
    describe: str
    check: Any  # record -> bool
    show: Any  # record -> str, for the failure examples


def _grant_deadline_ok(record: Any) -> bool:
    """A usable deadline, or an honest rolling call — both are actionable.

    A record with no dates at all is not a defect here: rolling programmes are
    real and accepting applications continuously. What is a defect is a record
    whose only date has already gone, and normalize already refuses those.
    """
    return bool(record.all_due_dates) or not record.close_date


GRANT_RULES: tuple[FieldRule, ...] = (
    FieldRule("name", 1, True, "a real title, not a placeholder",
              lambda r: _text_ok(r.title, 3), lambda r: r.title),
    FieldRule("description", 2, True, f">= {MIN_DESCRIPTION_CHARS} chars and not a pointer",
              lambda r: _describes_something(r.description), lambda r: r.description[:60]),
    FieldRule("deadlines", 3, True, "a future due date, or an open rolling call",
              _grant_deadline_ok, lambda r: str(r.all_due_dates or r.close_date_text or "none")),
    FieldRule("tags", 4, False, "at least one subject term",
              lambda r: bool(r.categories or r.topic_keywords),
              lambda r: str(r.categories[:3])),
)


def conference_rules(series_by_key: dict[str, Any]) -> tuple[FieldRule, ...]:
    """Built per run because the description rule needs the series behind each instance."""
    return (
        FieldRule("name", 1, True, "a title or an acronym",
                  lambda r: _text_ok(r.title, 3) or _text_ok(r.acronym, 2),
                  lambda r: r.title or r.acronym),
        FieldRule("description", 2, True,
                  f"CFP prose >= {MIN_DESCRIPTION_CHARS} chars, or a spelled-out venue "
                  f"name >= {MIN_VENUE_NAME_CHARS} chars plus a topic",
                  lambda r: _conference_description_ok(r, series_by_key),
                  lambda r: (r.cfp_text or r.title)[:60]),
        FieldRule("deadlines", 3, True, "a submission deadline with an instant and a basis",
                  _conference_deadline_ok,
                  lambda r: f"{len(r.deadlines)} deadline(s), "
                            f"{sum(1 for d in r.deadlines if d.is_submission)} submission"),
        FieldRule("tags", 4, False, "at least one topic",
                  lambda r: bool(r.topics), lambda r: str(r.topics[:3])),
        FieldRule("cfp_prose", 5, False, "the full call text — the best description there is",
                  lambda r: _describes_something(r.cfp_text), lambda r: r.cfp_text[:60]),
    )


def grade(record: Any, rules: tuple[FieldRule, ...]) -> str:
    """complete / usable / partial / unusable, from the required fields only."""
    passed = {rule.field for rule in rules if rule.check(record)}
    required = {rule.field for rule in rules if rule.required}
    missing = required - passed

    if not missing:
        return "complete" if "tags" in passed else "usable"
    if "name" in missing or len(missing) == len(required):
        return "unusable"
    return "partial"


def validate_records(records: list[Any], rules: tuple[FieldRule, ...], console=None):
    """Apply every rule to every record. Pure; the console is only for the ticker."""
    per_field: dict[str, int] = {rule.field: 0 for rule in rules}
    per_source: dict[str, dict[str, int]] = {}
    grades: dict[str, int] = {"complete": 0, "usable": 0, "partial": 0, "unusable": 0}
    failures: dict[str, list[str]] = {rule.field: [] for rule in rules}

    for index, record in enumerate(records, start=1):
        bucket = per_source.setdefault(
            record.source, {"records": 0, **{rule.field: 0 for rule in rules}}
        )
        bucket["records"] += 1
        for rule in rules:
            if rule.check(record):
                per_field[rule.field] += 1
                bucket[rule.field] += 1
            elif len(failures[rule.field]) < 5:
                key = getattr(record, "stable_key", None) or record.instance_key
                failures[rule.field].append(f"{record.source}: {key} → {rule.show(record)!r}")
        grades[grade(record, rules)] += 1
        if console is not None:
            # Quarterly, not every 5%: this loop is milliseconds, and a counter
            # that outruns the work it reports is noise pretending to be progress.
            console.progress(
                index, len(records), "records validated", every=max(1, len(records) // 4)
            )

    return {
        "records": len(records),
        "per_field": per_field,
        "per_source": per_source,
        "grades": grades,
        "failures": failures,
    }


def _validate_domain(context: RunContext, data: DomainData) -> dict[str, Any]:
    console = context.console
    console.step(f"4.{1 if data.domain == GRANTS else 2} validate · {data.domain}")
    rules = (
        GRANT_RULES if data.domain == GRANTS
        else conference_rules({s.series_key: s for s in data.series})
    )

    console.info(
        "checking, in priority order: "
        + "; ".join(
            f"{rule.priority}. {rule.field} ({'required' if rule.required else 'optional'}) "
            f"— {rule.describe}"
            for rule in rules
        )
    )
    if not data.items:
        console.warn("no records to validate")
        return {"records": 0}

    watch = Stopwatch()
    result = validate_records(data.items, rules, console)
    total = result["records"]

    console.table(
        ["priority", "field", "required", "present", "of", "coverage", "missing"],
        [
            [
                rule.priority, rule.field, "yes" if rule.required else "no",
                f"{result['per_field'][rule.field]:,}", f"{total:,}",
                f"{100 * result['per_field'][rule.field] / total:.1f}%",
                f"{total - result['per_field'][rule.field]:,}",
            ]
            for rule in rules
        ],
    )
    console.info("per-source coverage:")
    console.table(
        ["source", "records", *(rule.field for rule in rules)],
        [
            [
                source, f"{counts['records']:,}",
                *(
                    f"{100 * counts[rule.field] / counts['records']:.0f}%"
                    for rule in rules
                ),
            ]
            for source, counts in sorted(result["per_source"].items())
        ],
    )

    grades = result["grades"]
    console.info(
        f"grades: complete={grades['complete']:,} usable={grades['usable']:,} "
        f"partial={grades['partial']:,} unusable={grades['unusable']:,}"
    )
    for rule in rules:
        examples = result["failures"][rule.field]
        if not examples:
            continue
        level = console.warn if rule.required else console.info
        level(f"{rule.field}: {total - result['per_field'][rule.field]:,} failed ({rule.describe})")
        for example in examples:
            console.info(f"    e.g. {example}")

    console.ok(
        f"{grades['complete'] + grades['usable']:,} of {total:,} carry every required "
        f"field ({100 * (grades['complete'] + grades['usable']) / total:.1f}%) in {watch}"
    )
    result.pop("failures_shown", None)
    result["seconds"] = round(watch.elapsed, 2)
    return result


def stage_validate(context: RunContext, data: dict[str, DomainData]) -> int:
    """Returns the number of records missing a required field."""
    console = context.console
    total = sum(len(d.items) for d in data.values())
    watch = console.stage(
        4, "validation",
        what=f"confirm the required fields came out of all {total:,} records",
        how="name → description → deadlines → tags, each checked for usability, not presence",
        where="runner.py → stage_validate()",
    )

    report = context.stage_report("validation")
    defective = 0
    for domain in context.domains:
        report[domain] = _validate_domain(context, data[domain])
        grades = report[domain].get("grades", {})
        defective += grades.get("partial", 0) + grades.get("unusable", 0)

    console.endstep()
    report["seconds"] = round(watch.elapsed, 2)
    report["records_missing_a_required_field"] = defective
    console.summary(
        f"stage 4 complete in {watch}: {total - defective:,} of {total:,} records carry "
        f"every required field, {defective:,} do not"
    )
    return defective


# ═══════════════════════════════════════════════════════════════════════════
# Handoff
# ═══════════════════════════════════════════════════════════════════════════
#
# The downstream system reads the databases, not this file. The report exists so
# that a *run* can be inspected after the fact without re-running it: what each
# stage did, which keys are new, and how the corpus scored on the required
# fields. It is written even when a stage failed, because that is when it is
# most worth having.


def write_report(context: RunContext) -> Path:
    path = context.report_path
    path.parent.mkdir(parents=True, exist_ok=True)
    # Stamped here rather than only by run_pipeline, so a report salvaged from an
    # aborted run still says which run it was.
    context.report.setdefault("run_id", context.run_id)
    context.report.setdefault("started_at", context.started_at)
    context.report.setdefault("domains", context.domains)
    context.report["finished_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    path.write_text(json.dumps(context.report, indent=1, default=str), encoding="utf-8")
    return path


def final_summary(context: RunContext, data: dict[str, DomainData], defective: int) -> None:
    console = context.console
    console.stage_label = "done"
    console.step_label = ""

    stages = context.report.get("stages", {})
    rows = []
    for index, name in enumerate(STAGES, start=1):
        block = stages.get(name, {})
        rows.append(
            [
                f"{index}/{len(STAGES)}",
                name,
                "skipped" if block.get("skipped") else "ran",
                f"{block.get('seconds', 0):.1f}s",
            ]
        )
    console.table(["stage", "name", "state", "took"], rows)

    for domain, payload in data.items():
        errors = len(payload.errors)
        console.info(
            f"{domain:<12} {len(payload.items):,} records · {len(payload.new_keys):,} new · "
            f"{len(payload.parsed)} source(s) produced data · {errors} problem(s)"
        )

    total = sum(len(d.items) for d in data.values())
    new = sum(len(d.new_keys) for d in data.values())
    console.banner(
        f"RUN {context.run_id} COMPLETE in {console.clock}",
        [
            f"records   : {total:,} through all four stages, {new:,} new this run",
            f"required  : {total - defective:,} carry every required field, {defective:,} do not",
            f"databases : {context.grants_db if GRANTS in data else ''} "
            f"{context.conferences_db if CONFERENCES in data else ''}".strip(),
            f"report    : {context.report_path}",
            "downstream: the SQLite stores are ready to be mapped into ContentItem and embedded",
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="runner.py",
        description="Run every source through extraction, dedupe, new-item flagging, "
        "and field validation.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--domain", choices=[*DOMAINS, "all"], default="all", help="which corpus to collect"
    )
    parser.add_argument("--sources", default="", help="comma-separated source names")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="data directory")
    parser.add_argument("--limit", type=int, default=None, help="cap records per source")
    parser.add_argument(
        "--skip-fetch", action="store_true", help="re-run offline from stored raw payloads"
    )
    parser.add_argument(
        "--min-interval", type=float, default=0.5,
        help="minimum seconds between requests to one host (per-host floors still apply)",
    )
    parser.add_argument("--run-id", default=None, help="raw run to re-read with --skip-fetch")
    parser.add_argument("-v", "--verbose", action="store_true", help="per-record narration")
    parser.add_argument("-q", "--quiet", action="store_true", help="stage summaries only")
    parser.add_argument("--list-sources", action="store_true", help="print sources and exit")
    return parser


def new_run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    level = Console.VERBOSE if args.verbose else Console.QUIET if args.quiet else Console.NORMAL
    console = Console(level)

    if args.list_sources:
        return list_sources(console)

    domains = list(DOMAINS) if args.domain == "all" else [args.domain]
    selected = [name.strip() for name in args.sources.split(",") if name.strip()]
    sources = sources_for(domains, selected)

    context = RunContext(
        run_id=args.run_id or new_run_id(),
        started_at=datetime.now(UTC).isoformat(timespec="seconds"),
        root=Path(args.root),
        domains=[d for d in domains if d in sources],
        console=console,
        sources=sources,
        limit=args.limit,
        skip_fetch=args.skip_fetch,
        requested_run_id=args.run_id,
        min_interval=args.min_interval,
    )
    return run_pipeline(context)


def run_pipeline(context: RunContext) -> int:
    """The four stages, in order, narrated."""
    console = context.console
    total_sources = sum(len(names) for names in context.sources.values())
    console.banner(
        "CONSOLIDATED COLLECTION PIPELINE",
        [
            f"run      : {context.run_id}   started {context.started_at}",
            f"domains  : {', '.join(context.domains)}",
            f"sources  : {total_sources} across {len(context.sources)} domain(s)",
            "stages   : " + " → ".join(f"{i}.{name}" for i, name in enumerate(STAGES, 1)),
            f"store    : {context.root}",
            f"mode     : {'offline replay' if context.skip_fetch else 'live fetch'}"
            f"{'' if not context.limit else f', limit {context.limit}/source'}",
        ],
    )
    context.report.update(
        {
            "run_id": context.run_id,
            "started_at": context.started_at,
            "domains": context.domains,
            "sources": context.sources,
            "skip_fetch": context.skip_fetch,
        }
    )

    try:
        data = stage_extract(context)
        stage_deduplicate(context, data)
        stage_flag_new(context, data)
        defective = stage_validate(context, data)
    except Exception as exc:  # noqa: BLE001 — the transcript is the deliverable
        context.report["failed"] = f"{type(exc).__name__}: {exc}"
        console.error(f"run aborted in stage {console.location}: {type(exc).__name__}: {exc}")
        console.info(f"partial report written to {write_report(context)}")
        raise

    write_report(context)
    final_summary(context, data, defective)

    # 0 clean, 1 every source failed, 2 some source failed but the run produced
    # records. A caller chaining the downstream step needs to tell those apart.
    produced = sum(len(d.parsed) for d in data.values())
    failed = sum(len(d.errors) for d in data.values())
    if not produced:
        return 1
    return 2 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
