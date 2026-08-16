"""Six stages, wired together but never fused.

    1. fetch      network only, writes raw payloads, interprets nothing
    2. parse      raw payload -> series and instance candidates, no network
    3. normalize  dates, locations, acronyms, text; pure transformation
    4. resolve    join to the registry, assign series keys, tiers, red flags
    5. dedupe     four layers across the full normalized set
    6. persist    upsert preserving first_seen; mark past instances inactive

Stage 4 is the one the funding pipeline does not have, and it is the most
important. It must be re-runnable from stored normalized output with **no
network access**, because trust thresholds get tuned constantly and re-fetching
seven sources to try a new threshold is not acceptable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from apps.scraper.collect.conferences.adapters import build_registry
from apps.scraper.collect.conferences.record import ConferenceInstance, ConferenceSeries
from apps.scraper.collect.conferences.store import ConferenceStore, UpsertStats
from apps.scraper.collect.core.http import PoliteClient
from apps.scraper.collect.core.rawstore import RawStore, new_run_id, utc_now
from apps.scraper.collect.core.text import clean_text, dedupe_preserving_order

DEFAULT_ROOT = Path("data/collect")


@dataclass
class ConferenceConfig:
    root: Path = DEFAULT_ROOT
    sources: list[str] = field(default_factory=list)
    limit: int | None = None
    offline: bool = False
    keep_runs: int = 7
    min_interval: float = 0.5

    def __post_init__(self) -> None:
        self.root = Path(self.root)

    @property
    def raw_root(self) -> Path:
        return self.root / "raw-conferences"

    @property
    def cache_dir(self) -> Path:
        return self.root / "cache"

    @property
    def db_path(self) -> Path:
        return self.root / "conferences.db"

    @property
    def registry_dir(self) -> Path:
        return self.root / "registry"


@dataclass
class RunReport:
    run_id: str
    started_at: str
    fetched: dict[str, int] = field(default_factory=dict)
    parsed: dict[str, int] = field(default_factory=dict)
    errors: list[tuple[str, str, str]] = field(default_factory=list)
    series_count: int = 0
    instance_count: int = 0
    dedupe: object | None = None
    resolve: object | None = None
    stats: UpsertStats | None = None
    series_stats: UpsertStats | None = None
    deactivated: int = 0
    quarantined: int = 0

    def as_lines(self) -> list[str]:
        lines = [f"run {self.run_id}"]
        for source, count in sorted(self.fetched.items()):
            lines.append(f"  fetch    {source:<16} {count} raw records")
        for source, count in sorted(self.parsed.items()):
            lines.append(f"  parse    {source:<16} {count} instances")
        for source, stage, message in self.errors:
            lines.append(f"  ERROR    {source:<16} [{stage}] {message}")
        if self.resolve is not None:
            lines.append(f"  resolve  {self.resolve.summary()}")
        if self.dedupe is not None:
            lines.append(f"  dedupe   {self.dedupe.summary()}")
        if self.series_stats:
            lines.append(
                f"  series   inserted={self.series_stats.inserted} "
                f"updated={self.series_stats.updated} unchanged={self.series_stats.unchanged}"
            )
        if self.stats:
            lines.append(
                f"  persist  inserted={self.stats.inserted} updated={self.stats.updated} "
                f"unchanged={self.stats.unchanged} extensions={self.stats.extensions}"
            )
        lines.append(f"  inactive {self.deactivated} instances marked (retained, not deleted)")
        if self.quarantined:
            lines.append(f"  tier C   {self.quarantined} instances quarantined from default output")
        return lines


class ConferencePipeline:
    def __init__(self, config: ConferenceConfig) -> None:
        self.config = config
        self.registry = build_registry()
        self.raw_store = RawStore(config.raw_root)

    # -- selection --------------------------------------------------------

    def selected_sources(self) -> list[str]:
        names = self.config.sources or list(self.registry)
        unknown = [name for name in names if name not in self.registry]
        if unknown:
            raise ValueError(f"unknown source(s): {', '.join(unknown)}")
        return names

    def client(self) -> PoliteClient:
        return PoliteClient(
            cache_dir=self.config.cache_dir,
            offline=self.config.offline,
            min_interval=self.config.min_interval,
        )

    # -- stage 1 ----------------------------------------------------------

    def fetch(self, run_id: str | None = None):
        run_id = run_id or new_run_id()
        client = self.client()
        counts: dict[str, int] = {}
        errors: list[tuple[str, str, str]] = []

        for name in self.selected_sources():
            adapter = self.registry[name]
            enabled, reason = adapter.available()
            if not enabled:
                errors.append((name, "fetch", f"disabled: {reason}"))
                continue
            try:
                bundle = adapter.fetch(client, limit=self.config.limit)
            except Exception as exc:  # noqa: BLE001 — isolation is the whole point
                # One dead source must never sink the run; the rest still collect.
                # Every exception, not a curated tuple: a source that starts
                # serving malformed XML raises ParseError, which is a SyntaxError
                # and escaped the old (FetchError, RuntimeError, ValueError,
                # OSError) list — so one broken feed took the other six down.
                errors.append((name, "fetch", f"{type(exc).__name__}: {exc}"))
                continue
            bundle = type(bundle)(
                source=bundle.source,
                run_id=run_id,
                fetched_at=bundle.fetched_at,
                records=bundle.records,
                meta=bundle.meta,
            )
            self.raw_store.write(bundle)
            counts[name] = len(bundle.records)

        return run_id, counts, errors

    # -- stage 2 ----------------------------------------------------------

    def parse(self, run_id: str | None = None):
        """Raw payloads to candidates. Reads disk; touches no network."""
        resolved = self.raw_store.resolve(run_id)
        if resolved is None:
            raise FileNotFoundError(f"no raw payloads on disk under {self.config.raw_root}")

        series: list[ConferenceSeries] = []
        instances: list[ConferenceInstance] = []
        counts: dict[str, int] = {}
        errors: list[tuple[str, str, str]] = []

        wanted = set(self.selected_sources())
        for name in self.raw_store.sources_in(resolved):
            if name not in wanted or name not in self.registry:
                continue
            bundle = self.raw_store.read(resolved, name)
            if bundle is None:
                continue
            try:
                parsed_series, parsed_instances = self.registry[name].parse(bundle)
            except Exception as exc:  # noqa: BLE001 - one adapter's bug is not fatal
                errors.append((name, "parse", f"{type(exc).__name__}: {exc}"))
                continue
            series.extend(parsed_series)
            instances.extend(parsed_instances)
            counts[name] = len(parsed_instances)

        return series, instances, counts, errors

    # -- stage 3 ----------------------------------------------------------

    @staticmethod
    def normalize(
        series: list[ConferenceSeries], instances: list[ConferenceInstance]
    ) -> tuple[list[ConferenceSeries], list[ConferenceInstance]]:
        """Cross-source tidy-up, as a pure transformation.

        Deliberately does *not* filter on deadlines. Past instances are retained
        and marked inactive at persist time — dropping them here would destroy
        the longevity signal the trust tier depends on.
        """
        for record in series:
            record.acronym = clean_text(record.acronym)
            record.full_name = clean_text(record.full_name)
            record.acronym_variants = dedupe_preserving_order(
                [clean_text(v) for v in record.acronym_variants if clean_text(v)]
            )
            record.name_variants = dedupe_preserving_order(
                [clean_text(v) for v in record.name_variants if clean_text(v)]
            )

        kept: list[ConferenceInstance] = []
        for record in instances:
            record.title = clean_text(record.title)
            record.acronym = clean_text(record.acronym)
            record.topics = dedupe_preserving_order(
                [clean_text(t) for t in record.topics if clean_text(t)]
            )
            if not record.title and not record.acronym:
                continue  # an empty husk is not a record
            kept.append(record)

        return series, kept

    # -- stage 6 ----------------------------------------------------------

    def persist(
        self,
        series: list[ConferenceSeries],
        instances: list[ConferenceInstance],
        *,
        now: datetime | None = None,
    ) -> tuple[UpsertStats, UpsertStats, int, int]:
        now = now or datetime.now(UTC)
        with ConferenceStore(self.config.db_path) as store:
            series_stats = store.upsert_series(series)
            stats = store.upsert_instances(instances)
            deactivated = store.mark_inactive(now)
            quarantined = store.quarantined_count()
        return series_stats, stats, deactivated, quarantined

    # -- the whole thing --------------------------------------------------

    def run(
        self,
        *,
        skip_fetch: bool = False,
        run_id: str | None = None,
        now: datetime | None = None,
    ) -> RunReport:
        started_at = utc_now()

        if skip_fetch:
            resolved = self.raw_store.resolve(run_id)
            if resolved is None:
                raise FileNotFoundError("--skip-fetch requested but no raw payloads exist")
            report = RunReport(run_id=resolved, started_at=started_at)
        else:
            fetched_run_id, counts, errors = self.fetch(run_id)
            report = RunReport(run_id=fetched_run_id, started_at=started_at, fetched=counts)
            report.errors.extend(errors)

        series, instances, parse_counts, parse_errors = self.parse(report.run_id)
        report.parsed = parse_counts
        report.errors.extend(parse_errors)

        series, instances = self.normalize(series, instances)

        series, instances, resolve_report = self.resolve(series, instances)
        report.resolve = resolve_report

        series, instances, dedupe_report = self.deduplicate(series, instances)
        report.dedupe = dedupe_report

        report.series_count = len(series)
        report.instance_count = len(instances)

        series_stats, stats, deactivated, quarantined = self.persist(series, instances, now=now)
        report.series_stats = series_stats
        report.stats = stats
        report.deactivated = deactivated
        report.quarantined = quarantined

        with ConferenceStore(self.config.db_path) as store:
            store.record_run(
                report.run_id,
                started_at=started_at,
                sources=self.selected_sources(),
                stats=stats,
                deactivated=deactivated,
            )
            for source, stage, message in report.errors:
                store.record_error(report.run_id, source, stage, message)

        self.raw_store.prune_runs(self.config.keep_runs)
        return report

    # -- stages 4 and 5 ---------------------------------------------------
    #
    # Implemented in resolve.py and dedupe.py and wired here so the stage order
    # stays readable in one place.

    def resolve(self, series, instances):
        from apps.scraper.collect.conferences.resolve import resolve_all

        return resolve_all(series, instances, registry_dir=self.config.registry_dir)

    def deduplicate(self, series, instances):
        from apps.scraper.collect.conferences.dedupe import deduplicate

        return deduplicate(series, instances)
