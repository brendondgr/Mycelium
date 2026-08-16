"""The five stages, wired together but never fused.

    1. fetch      network only, writes raw payloads, does nothing else
    2. parse      raw payload -> canonical record, no network
    3. normalize  dates, amounts, text cleanup, pure transformation
    4. dedupe     across the full normalized set
    5. persist    upsert on the stable key, preserve first_seen, prune expired

Each stage is separately callable and re-runnable from the previous stage's stored
output. That is the whole reason for the split: when a parse bug surfaces you
re-run stage 2 over yesterday's payloads in seconds instead of re-hitting five
APIs, and the sources never notice.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from apps.scraper.collect.core.http import PoliteClient
from apps.scraper.collect.core.rawstore import RawStore, new_run_id, utc_now
from apps.scraper.collect.grants.adapters import build_registry
from apps.scraper.collect.grants.dedupe import (
    DedupeReport,
    deduplicate,
    resolve_overlay_parents,
)
from apps.scraper.collect.grants.enrich import apply_enrichment as enrich_records
from apps.scraper.collect.grants.funders import canonical_funder
from apps.scraper.collect.grants.normalize import (
    clean_dates,
    clean_text,
    dedupe_preserving_order,
    is_past,
    to_amount,
)
from apps.scraper.collect.grants.record import Opportunity
from apps.scraper.collect.grants.store import Store, UpsertStats

DEFAULT_ROOT = Path("data/collect")


@dataclass
class CollectConfig:
    root: Path = DEFAULT_ROOT
    sources: list[str] = field(default_factory=list)
    limit: int | None = None
    offline: bool = False
    #: How many raw run directories to keep on disk.
    keep_runs: int = 7
    min_interval: float = 0.5

    def __post_init__(self) -> None:
        self.root = Path(self.root)

    @property
    def raw_root(self) -> Path:
        return self.root / "raw"

    @property
    def cache_dir(self) -> Path:
        return self.root / "cache"

    @property
    def db_path(self) -> Path:
        return self.root / "opportunities.db"

    @property
    def enrichment_path(self) -> Path:
        """Announcement pages fetched by `collect enrich`, replayed on every run."""
        return self.root / "enrichment.json"


@dataclass
class RunReport:
    run_id: str
    started_at: str
    fetched: dict[str, int] = field(default_factory=dict)
    parsed: dict[str, int] = field(default_factory=dict)
    errors: list[tuple[str, str, str]] = field(default_factory=list)
    dedupe: DedupeReport | None = None
    stats: UpsertStats | None = None
    pruned: int = 0
    #: Records whose text was replaced by a fuller fetched announcement page.
    enriched: int = 0
    #: Records the source stopped listing — withdrawn, or stranded under an
    #: identifier scheme we have since changed. Distinct from pruned, which is
    #: about deadlines passing.
    withdrawn: int = 0
    unresolved_overlays: int = 0

    def as_lines(self) -> list[str]:
        lines = [f"run {self.run_id}"]
        for source, count in sorted(self.fetched.items()):
            lines.append(f"  fetch  {source:<12} {count} raw records")
        for source, count in sorted(self.parsed.items()):
            lines.append(f"  parse  {source:<12} {count} canonical records")
        for source, stage, message in self.errors:
            lines.append(f"  ERROR  {source:<12} [{stage}] {message}")
        if self.dedupe:
            lines.append(f"  dedupe {self.dedupe.summary()}")
        if self.unresolved_overlays:
            lines.append(f"  overlays with unresolved parents: {self.unresolved_overlays}")
        if self.stats:
            lines.append(
                f"  persist inserted={self.stats.inserted} updated={self.stats.updated} "
                f"unchanged={self.stats.unchanged}"
            )
        if self.enriched:
            lines.append(f"  enrich {self.enriched} records given fuller announcement text")
        if self.withdrawn:
            lines.append(f"  vacuum removed {self.withdrawn} no longer listed by their source")
        lines.append(f"  prune  removed {self.pruned}")
        return lines


class Pipeline:
    def __init__(self, config: CollectConfig) -> None:
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

    def fetch(self, run_id: str | None = None) -> tuple[str, dict[str, int], list[tuple[str, str, str]]]:
        """Network only. Writes raw payloads to disk and returns counts."""
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
                # OSError) list — so one broken feed took the other five down.
                errors.append((name, "fetch", f"{type(exc).__name__}: {exc}"))
                continue
            # The bundle carries the adapter's own run id; force the run's.
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

    def parse(self, run_id: str | None = None) -> tuple[list[Opportunity], dict[str, int], list[tuple[str, str, str]]]:
        """Raw payloads to canonical records. Reads disk; touches no network."""
        resolved = self.raw_store.resolve(run_id)
        if resolved is None:
            raise FileNotFoundError(f"no raw payloads on disk under {self.config.raw_root}")

        records: list[Opportunity] = []
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
                parsed = self.registry[name].parse(bundle)
            except Exception as exc:  # noqa: BLE001 - a parse bug in one adapter is not fatal
                errors.append((name, "parse", f"{type(exc).__name__}: {exc}"))
                continue
            records.extend(parsed)
            counts[name] = len(parsed)

        return records, counts, errors

    # -- stage 3 ----------------------------------------------------------

    @staticmethod
    def normalize(records: list[Opportunity], today: date | None = None) -> list[Opportunity]:
        """Final tidy-up and the open-set invariant, as a pure transformation.

        Adapters already normalize their own fields; this is the cross-source
        pass that enforces what must be true of *every* record regardless of who
        produced it.
        """
        today = today or date.today()
        out: list[Opportunity] = []

        for record in records:
            record.title = clean_text(record.title)
            record.funder = clean_text(record.funder)
            # Derived here rather than per-adapter for the same reason the
            # deadline rule is: six adapters agreeing by hand is six chances to
            # disagree, and the last two did.
            record.funder_canonical = canonical_funder(record.funder, record.agency_code)
            record.categories = dedupe_preserving_order(
                [clean_text(value) for value in record.categories if clean_text(value)]
            )
            # Canonicalize the deadline set centrally rather than trusting each
            # adapter to agree about which end of its own list means what. Two
            # of them did not: the EU portal kept the first entry and NIH kept
            # the last, so the same shape of data produced opposite errors.
            # close_date is the *final* round, because pruning keys on it and
            # deleting a recurring call the moment its nearest round passes would
            # discard every remaining cycle. Which round to display is a separate
            # question, answered by Opportunity.due_on.
            rounds = clean_dates([record.close_date, *record.additional_due_dates])
            if rounds:
                record.close_date = rounds[-1]
                record.additional_due_dates = rounds[:-1]
            else:
                record.additional_due_dates = []

            # A paragraph must never survive in a numeric field. The adapters
            # guard this too; belt and braces, because it silently corrupts every
            # downstream comparison if it slips through.
            record.award_floor = to_amount(record.award_floor)
            record.award_ceiling = to_amount(record.award_ceiling)
            record.total_program_funding = to_amount(record.total_program_funding)
            if (
                record.award_floor is not None
                and record.award_ceiling is not None
                and record.award_floor > record.award_ceiling
            ):
                record.award_floor, record.award_ceiling = (
                    record.award_ceiling,
                    record.award_floor,
                )

            if not record.title and not record.description:
                continue  # an empty husk is not a record
            if _already_closed(record, today):
                continue  # filter at parse time; closed records never enter the store

            out.append(record)
        return out

    # -- stage 4 ----------------------------------------------------------

    @staticmethod
    def deduplicate(records: list[Opportunity]) -> tuple[list[Opportunity], DedupeReport, int]:
        merged, report = deduplicate(records)
        unresolved = resolve_overlay_parents(merged)
        return merged, report, unresolved

    # -- stage 4b ---------------------------------------------------------

    def apply_enrichment(self, records: list[Opportunity]) -> int:
        """Fold previously-fetched announcement pages into the records. No network.

        The pages were fetched by ``collect enrich`` and stored; this replays
        them, so the seam is the same one fetch and parse have and for the same
        reason. Absent or unreadable, the pipeline runs exactly as before.
        """
        path = self.config.enrichment_path
        if not path.exists():
            return 0
        try:
            pages = json.loads(path.read_text())
        except (OSError, ValueError):
            return 0
        improved, _ = enrich_records(records, pages)
        return improved

    # -- stage 5 ----------------------------------------------------------

    def persist(
        self,
        records: list[Opportunity],
        *,
        today: date | None = None,
        complete_sources: list[str] | None = None,
    ) -> tuple[UpsertStats, int, int]:
        """Upsert, drop withdrawn records, prune expired ones.

        ``complete_sources`` names the sources this run covered in full. Only
        those are vacuumed, because a partial key set would delete everything it
        did not happen to see.
        """
        with Store(self.config.db_path) as store:
            stats = store.upsert_all(records)
            store.rebuild_search_index()
            removed = 0
            if complete_sources:
                removed = store.vacuum(
                    complete_sources, {record.stable_key for record in records}
                )
            pruned = store.prune(today)
        return stats, pruned, removed

    # -- the whole thing --------------------------------------------------

    def run(
        self,
        *,
        skip_fetch: bool = False,
        run_id: str | None = None,
        today: date | None = None,
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

        records, parse_counts, parse_errors = self.parse(report.run_id)
        report.parsed = parse_counts
        report.errors.extend(parse_errors)

        records = self.normalize(records, today)
        records, dedupe_report, unresolved = self.deduplicate(records)
        report.dedupe = dedupe_report
        report.unresolved_overlays = unresolved

        # Enrichment is part of the deterministic offline pipeline, not a patch
        # applied to the store afterwards. Applied afterwards it would be undone
        # by the next ordinary run, which rebuilds every description from the raw
        # payloads — and the idempotency check would report 62 updates on a run
        # where nothing at the source had changed.
        report.enriched = self.apply_enrichment(records)

        # A source is "complete" only if it parsed without error and the run was
        # not capped. Vacuuming against a truncated key set would delete the rest
        # of that source's corpus.
        failed = {source for source, _, _ in report.errors}
        complete = (
            [name for name in parse_counts if name not in failed]
            if self.config.limit is None
            else []
        )
        stats, pruned, withdrawn = self.persist(
            records, today=today, complete_sources=complete
        )
        report.stats = stats
        report.pruned = pruned
        report.withdrawn = withdrawn

        with Store(self.config.db_path) as store:
            store.record_run(
                report.run_id,
                started_at=started_at,
                sources=self.selected_sources(),
                stats=stats,
                pruned=pruned,
            )
            for source, stage, message in report.errors:
                store.record_error(report.run_id, source, stage, message)

        self.raw_store.prune_runs(self.config.keep_runs)
        return report


def _already_closed(record: Opportunity, today: date) -> bool:
    """The "currently open" invariant, applied before anything is stored.

    Filtering here rather than after the fact keeps the corpus small and means a
    closed record never enters the store in the first place. The three special
    cases all resolve to "keep": a null close date is rolling, a recurring
    opportunity lives while any round is future, and an overlay is judged on its
    own expiration rather than a deadline it does not have.
    """
    if record.record_kind == "overlay":
        return is_past(record.expiration_date, today)
    known = [value for value in [record.close_date, *record.additional_due_dates] if value]
    if not known:
        return False
    return all(is_past(value, today) for value in known)
