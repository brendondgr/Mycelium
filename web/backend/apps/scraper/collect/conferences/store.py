"""Persist series and instances, and mark past instances inactive.

This is where conferences diverge most sharply from the funding collector, and
the difference is easy to get wrong by copying: the grants store *deletes*
expired opportunities, and doing that here would be a bug.

Past instances are retained for two reasons the briefing is explicit about: they
let you predict next year's deadline for a series whose CFP has not been posted
yet, and they are the longevity signal that feeds the trust tier. On the
structured corpus that is 1,516 of 1,605 deadline entries — deleting them would
throw away almost the entire dataset on the first run and destroy the evidence
that a venue has run for thirty years.

So ``mark_inactive`` flips a flag. Nothing is ever pruned.

The other subtlety is deadline extensions, which are extremely common. An upsert
must *update* an existing deadline rather than appending a duplicate, and record
that an extension happened — because repeated extensions are themselves a
predatory red flag.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from apps.scraper.collect.conferences.record import (
    BOOKKEEPING_COLUMNS,
    CARRY_FORWARD_COLUMNS,
    ConferenceInstance,
    ConferenceSeries,
    Deadline,
)
from apps.scraper.collect.conferences.timezones import is_future
from apps.scraper.collect.core.rawstore import utc_now

SCHEMA = """
CREATE TABLE IF NOT EXISTS series (
    series_key           TEXT PRIMARY KEY,
    acronym              TEXT,
    acronym_variants     TEXT,
    full_name            TEXT,
    name_variants        TEXT,
    field_codes          TEXT,
    rankings             TEXT,
    dblp_key             TEXT,
    dblp_found           INTEGER DEFAULT 0,
    indexed_years        INTEGER DEFAULT 0,
    first_year           INTEGER,
    last_year            INTEGER,
    dblp_candidates      TEXT,
    trust_tier           TEXT NOT NULL DEFAULT 'unassigned',
    red_flags            TEXT,
    contributing_sources TEXT,
    license              TEXT
);
CREATE INDEX IF NOT EXISTS idx_series_acronym ON series(acronym);
CREATE INDEX IF NOT EXISTS idx_series_tier    ON series(trust_tier);
CREATE INDEX IF NOT EXISTS idx_series_dblp    ON series(dblp_key);

CREATE TABLE IF NOT EXISTS instances (
    instance_key         TEXT PRIMARY KEY,
    source               TEXT NOT NULL,
    source_record_id     TEXT NOT NULL,
    series_key           TEXT,
    parent_instance_key  TEXT,
    record_kind          TEXT NOT NULL,
    title                TEXT,
    acronym              TEXT,
    year_label           TEXT,
    ordinal              TEXT,
    event_start          TEXT,
    event_end            TEXT,
    event_dates_text     TEXT,
    city                 TEXT,
    country_code         TEXT,
    place_text           TEXT,
    is_virtual           INTEGER DEFAULT 0,
    is_hybrid            INTEGER DEFAULT 0,
    url                  TEXT,
    cfp_text             TEXT,
    topics               TEXT,
    deadlines            TEXT,
    generated_summary    TEXT,
    generated_topics     TEXT,
    enrichment_status    TEXT,
    source_url           TEXT,
    first_seen           TEXT,
    last_fetched         TEXT,
    contributing_sources TEXT,
    review_candidates    TEXT,
    quality_warnings     TEXT,
    unresolved_parent    INTEGER DEFAULT 0,
    active               INTEGER DEFAULT 1,
    license              TEXT,
    raw                  TEXT
);
CREATE INDEX IF NOT EXISTS idx_inst_series ON instances(series_key);
CREATE INDEX IF NOT EXISTS idx_inst_active ON instances(active);
CREATE INDEX IF NOT EXISTS idx_inst_parent ON instances(parent_instance_key);
CREATE INDEX IF NOT EXISTS idx_inst_kind   ON instances(record_kind);

CREATE TABLE IF NOT EXISTS runs (
    run_id      TEXT PRIMARY KEY,
    started_at  TEXT,
    finished_at TEXT,
    sources     TEXT,
    inserted    INTEGER DEFAULT 0,
    updated     INTEGER DEFAULT 0,
    unchanged   INTEGER DEFAULT 0,
    deactivated INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS source_errors (
    run_id  TEXT,
    source  TEXT,
    stage   TEXT,
    message TEXT,
    at      TEXT
);

CREATE TABLE IF NOT EXISTS enrichment (
    instance_key     TEXT PRIMARY KEY,
    url              TEXT,
    status           TEXT,
    detail           TEXT,
    page_hash        TEXT,
    fetched_at       TEXT,
    generated_at     TEXT,
    model            TEXT,
    summary          TEXT,
    purpose          TEXT,
    audience         TEXT,
    topics           TEXT,
    submission_types TEXT,
    deadlines        TEXT,
    rejected         TEXT,
    raw_response     TEXT
);
CREATE INDEX IF NOT EXISTS idx_enrich_status ON enrichment(status);
"""


def _columns_of(table: str) -> list[str]:
    return [name for name, _ in _declared_columns(table)]


def _declared_columns(table: str) -> list[tuple[str, str]]:
    """(name, type declaration) for one table, parsed out of SCHEMA itself.

    Read rather than repeated so the column list and the schema cannot drift —
    the migration below adds whatever SCHEMA gained, which only works if it is
    reading the same text the table was created from.
    """
    body = SCHEMA.split(f"CREATE TABLE IF NOT EXISTS {table} (")[1].split(");")[0]
    out: list[tuple[str, str]] = []
    for line in body.strip().splitlines():
        parts = line.strip().rstrip(",").split(None, 1)
        if parts:
            out.append((parts[0], parts[1] if len(parts) > 1 else "TEXT"))
    return out


_INSTANCE_COLUMNS = _columns_of("instances")


@dataclass
class UpsertStats:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    #: Deadlines that moved later on an existing record.
    extensions: int = 0

    @property
    def total(self) -> int:
        return self.inserted + self.updated + self.unchanged


def order_deadlines(deadlines: list[Deadline]) -> list[Deadline]:
    """Chronological, with undated entries last.

    Applied on insert *and* on merge. Applying it only on merge is what it used
    to do, and that made the first run store whatever order the adapter happened
    to emit while the second run sorted it — one phantom update per record with
    out-of-order deadlines, and a freshly built store that could fail the
    "multi-round venues are ordered" check until it had been run twice.
    """
    return sorted(deadlines, key=lambda d: (d.instant or "9999", d.kind))


def merge_deadlines(existing: list[Deadline], incoming: list[Deadline]) -> tuple[list[Deadline], int]:
    """Fold incoming deadlines into stored ones, updating rather than appending.

    Extensions are extremely common, so matching is on ``(kind, round_label)``
    and deliberately *not* on the date — otherwise every extension appends a
    duplicate and a venue that moved its deadline twice shows three entries.

    Returns the merged list and the number of extensions observed.
    """
    by_identity = {d.identity: d for d in existing}
    extensions = 0
    out = list(existing)

    for candidate in incoming:
        prior = by_identity.get(candidate.identity)
        if prior is None:
            by_identity[candidate.identity] = candidate
            out.append(candidate)
            continue
        # A source that only knows the calendar date must never overwrite one
        # that published an explicit timezone — that would silently move the
        # deadline by up to a day, which is the exact failure the three-value
        # timezone model exists to prevent.
        if _downgrades_basis(prior, candidate):
            prior.source = prior.source or candidate.source
            continue

        moved_later = (
            prior.instant is not None
            and candidate.instant is not None
            and candidate.instant > prior.instant
        )
        if moved_later:
            extensions += 1
        prior.raw = candidate.raw or prior.raw
        prior.instant = candidate.instant if candidate.instant else prior.instant
        prior.basis = candidate.basis or prior.basis
        prior.source = candidate.source or prior.source
        prior.is_estimated = candidate.is_estimated
        if moved_later:
            # The count is the signal: one extension is normal, four is a flag.
            prior.extension_count += 1

    return order_deadlines(out), extensions


def _has_value(value: object) -> bool:
    """True for real content. ``"[]"`` is a JSON-encoded empty list, not a value."""
    return bool(value) and value not in ("[]", "{}", "")


def _downgrades_basis(prior: Deadline, candidate: Deadline) -> bool:
    """True when accepting the candidate would lose a real timezone basis."""
    prior_inferred = not prior.basis or prior.basis.startswith("inferred")
    candidate_inferred = not candidate.basis or candidate.basis.startswith("inferred")
    return candidate_inferred and not prior_inferred


class ConferenceStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        """Add columns SCHEMA has gained since this database was created.

        ``CREATE TABLE IF NOT EXISTS`` silently does nothing to an existing table,
        so without this the enrichment columns would read fine on a fresh store
        and raise on the one that already holds the corpus. Additive only: a
        column that changes meaning gets a new name instead, so an old row is
        never reinterpreted as something it is not.
        """
        for table in ("instances", "series", "enrichment"):
            existing = {
                row["name"] for row in self.conn.execute(f"PRAGMA table_info({table})").fetchall()
            }
            if not existing:
                continue
            for name, declaration in _declared_columns(table):
                if name not in existing:
                    self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> ConferenceStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- series -----------------------------------------------------------

    def upsert_series(self, records: list[ConferenceSeries]) -> UpsertStats:
        stats = UpsertStats()
        for record in records:
            row = record.to_row()
            existing = self.conn.execute(
                "SELECT * FROM series WHERE series_key = ?", (row["series_key"],)
            ).fetchone()
            if existing is None:
                columns = ", ".join(row)
                placeholders = ", ".join(f":{name}" for name in row)
                self.conn.execute(f"INSERT INTO series ({columns}) VALUES ({placeholders})", row)
                stats.inserted += 1
                continue
            if all(existing[column] == value for column, value in row.items()):
                stats.unchanged += 1
                continue
            assignments = ", ".join(f"{n} = :{n}" for n in row if n != "series_key")
            self.conn.execute(
                f"UPDATE series SET {assignments} WHERE series_key = :series_key", row
            )
            stats.updated += 1
        self.conn.commit()
        return stats

    def all_series(self) -> list[ConferenceSeries]:
        rows = self.conn.execute("SELECT * FROM series").fetchall()
        return [ConferenceSeries.from_row(dict(row)) for row in rows]

    def series_for(self, series_key: str) -> ConferenceSeries | None:
        row = self.conn.execute(
            "SELECT * FROM series WHERE series_key = ?", (series_key,)
        ).fetchone()
        return ConferenceSeries.from_row(dict(row)) if row else None

    # -- instances --------------------------------------------------------

    def upsert_instances(
        self, records: list[ConferenceInstance], *, now: str | None = None
    ) -> UpsertStats:
        stamp = now or utc_now()
        stats = UpsertStats()
        for record in records:
            self._upsert_instance(record, stamp, stats)
        self.conn.commit()
        return stats

    def _upsert_instance(
        self, record: ConferenceInstance, stamp: str, stats: UpsertStats
    ) -> None:
        existing = self.conn.execute(
            "SELECT * FROM instances WHERE instance_key = ?", (record.instance_key,)
        ).fetchone()

        if existing is None:
            row = record.copy(deadlines=order_deadlines(record.deadlines)).to_row()
            row["first_seen"] = stamp
            row["last_fetched"] = stamp
            columns = ", ".join(row)
            placeholders = ", ".join(f":{name}" for name in row)
            self.conn.execute(f"INSERT INTO instances ({columns}) VALUES ({placeholders})", row)
            stats.inserted += 1
            return

        # Fold the incoming deadlines into the stored ones before comparing, so
        # an extension updates in place and the extension counter survives.
        stored = ConferenceInstance.from_row(dict(existing))
        merged, extensions = merge_deadlines(stored.deadlines, record.deadlines)
        stats.extensions += extensions
        record = record.copy(deadlines=merged)

        row = record.to_row()
        # first_seen is set once and never overwritten, whatever a later run says.
        row["first_seen"] = existing["first_seen"] or stamp
        # The enrichment columns belong to the website layer, not the adapter. An
        # ordinary run re-emits every record with them empty, and without this the
        # generated summaries would survive exactly until the next fetch.
        for column in CARRY_FORWARD_COLUMNS:
            if not _has_value(row.get(column)):
                row[column] = existing[column]
        changed = any(
            existing[column] != value
            for column, value in row.items()
            if column not in BOOKKEEPING_COLUMNS
        )

        if not changed:
            # Touch nothing at all — not even last_fetched. Writing a timestamp
            # on every run would make the idempotency check unfalsifiable.
            stats.unchanged += 1
            return

        row["last_fetched"] = stamp
        assignments = ", ".join(f"{n} = :{n}" for n in row if n != "instance_key")
        self.conn.execute(
            f"UPDATE instances SET {assignments} WHERE instance_key = :instance_key", row
        )
        stats.updated += 1

    def all_instances(self, *, with_raw: bool = True, active_only: bool = False):
        """Every stored instance.

        ``with_raw=False`` skips the verbatim payload, which dominates the read
        for any caller that only wants normalized fields — i.e. everything
        outside the parse stage.
        """
        columns = "*" if with_raw else ", ".join(c for c in _INSTANCE_COLUMNS if c != "raw")
        where = " WHERE active = 1" if active_only else ""
        rows = self.conn.execute(f"SELECT {columns} FROM instances{where}").fetchall()
        return [
            ConferenceInstance.from_row({**dict(row), **({} if with_raw else {"raw": "{}"})})
            for row in rows
        ]

    # -- the "currently relevant" invariant -------------------------------

    def mark_inactive(self, now: datetime | None = None) -> int:
        """Deactivate instances with no future submission deadline. Deletes nothing.

        Retention is the point. A past instance still tells you the venue exists,
        how long it has run, and roughly when next year's deadline will fall.
        """
        now = now or datetime.now(UTC)
        changed = 0
        for record in self.all_instances(with_raw=False):
            should_be_active = record.is_relevant(now)
            if should_be_active != record.active:
                self.conn.execute(
                    "UPDATE instances SET active = ? WHERE instance_key = ?",
                    (int(should_be_active), record.instance_key),
                )
                changed += 1
        self.conn.commit()
        return changed

    # -- reads ------------------------------------------------------------

    def count_instances(self, *, active_only: bool = False) -> int:
        where = " WHERE active = 1" if active_only else ""
        return int(self.conn.execute(f"SELECT COUNT(*) FROM instances{where}").fetchone()[0])

    def count_series(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM series").fetchone()[0])

    def count_by_source(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT source, COUNT(*) AS n FROM instances GROUP BY source"
        ).fetchall()
        return {row["source"]: row["n"] for row in rows}

    def count_by_tier(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT trust_tier, COUNT(*) AS n FROM series GROUP BY trust_tier"
        ).fetchall()
        return {row["trust_tier"]: row["n"] for row in rows}

    def quarantined_count(self) -> int:
        """Tier C instances withheld from default output.

        Reported rather than silently dropped — a user is entitled to know that
        records were withheld and how many.
        """
        return int(
            self.conn.execute(
                "SELECT COUNT(*) FROM instances i JOIN series s USING (series_key)"
                " WHERE s.trust_tier = 'C'"
            ).fetchone()[0]
        )

    # -- enrichment -------------------------------------------------------

    def read_enrichment(self) -> dict[str, object]:
        """Every cached website verdict, keyed by instance. Terminal ones included.

        A recorded failure is as much an answer as a success: re-asking a dead
        host on every run is how a polite crawler becomes an impolite one.
        """
        from apps.scraper.collect.conferences.enrich import EnrichmentRecord

        return {
            row["instance_key"]: EnrichmentRecord.from_row(dict(row))
            for row in self.conn.execute("SELECT * FROM enrichment")
        }

    def write_enrichment(self, records: list[object]) -> int:
        rows = [record.to_row() for record in records]
        if not rows:
            return 0
        columns = ", ".join(rows[0])
        placeholders = ", ".join(f":{name}" for name in rows[0])
        self.conn.executemany(
            f"INSERT OR REPLACE INTO enrichment ({columns}) VALUES ({placeholders})", rows
        )
        self.conn.commit()
        return len(rows)

    def count_by_enrichment_status(self) -> dict[str, int]:
        return {
            row["status"]: row["n"]
            for row in self.conn.execute(
                "SELECT status, COUNT(*) AS n FROM enrichment GROUP BY status"
            )
        }

    # -- bookkeeping ------------------------------------------------------

    def record_run(
        self,
        run_id: str,
        *,
        started_at: str,
        sources: list[str],
        stats: UpsertStats,
        deactivated: int,
    ) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO runs
               (run_id, started_at, finished_at, sources, inserted, updated, unchanged, deactivated)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                started_at,
                utc_now(),
                ",".join(sources),
                stats.inserted,
                stats.updated,
                stats.unchanged,
                deactivated,
            ),
        )
        self.conn.commit()

    def record_error(self, run_id: str, source: str, stage: str, message: str) -> None:
        self.conn.execute(
            "INSERT INTO source_errors (run_id, source, stage, message, at) VALUES (?, ?, ?, ?, ?)",
            (run_id, source, stage, message, utc_now()),
        )
        self.conn.commit()

    def errors_for(self, run_id: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM source_errors WHERE run_id = ?", (run_id,)
        ).fetchall()

    def last_run(self) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()


__all__ = [
    "ConferenceStore",
    "UpsertStats",
    "merge_deadlines",
    "order_deadlines",
    "is_future",
    "SCHEMA",
]
