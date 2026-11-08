"""Stage 5: persist and prune.

Upsert on the stable key, preserve ``first_seen`` forever, and report honestly
whether anything actually changed — the idempotency check in the smoke list is
only meaningful if "updated" means "the source differs", not "we ran again".
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from tools.retrieval.collect.core.rawstore import utc_now
from tools.retrieval.collect.grants.history import Change, diff_rows
from tools.retrieval.collect.grants.normalize import is_past
from tools.retrieval.collect.grants.record import BOOKKEEPING_COLUMNS, Opportunity

SCHEMA = """
CREATE TABLE IF NOT EXISTS opportunities (
    stable_key                TEXT PRIMARY KEY,
    source                    TEXT NOT NULL,
    source_record_id          TEXT NOT NULL,
    source_url                TEXT,
    opportunity_number        TEXT,
    parent_opportunity_number TEXT,
    record_kind               TEXT NOT NULL,
    title                     TEXT,
    funder                    TEXT,
    funder_subunit            TEXT,
    description               TEXT,
    categories                TEXT,
    status                    TEXT NOT NULL,
    posted_date               TEXT,
    open_date                 TEXT,
    close_date                TEXT,
    close_date_text           TEXT,
    additional_due_dates      TEXT,
    expiration_date           TEXT,
    original_close_date       TEXT,
    intent_date               TEXT,
    intent_date_text          TEXT,
    dates_inferred            INTEGER DEFAULT 0,
    award_floor               REAL,
    award_ceiling             REAL,
    total_program_funding     REAL,
    expected_awards           INTEGER,
    currency                  TEXT,
    applicant_types           TEXT,
    funding_instruments       TEXT,
    activity_codes            TEXT,
    assistance_listings       TEXT,
    cost_sharing              INTEGER,
    agency_code               TEXT,
    funder_canonical          TEXT,
    opportunity_category      TEXT,
    action_types              TEXT,
    deadline_model            TEXT,
    topic_keywords            TEXT,
    participating_units       TEXT,
    related_numbers           TEXT,
    eligibility               TEXT,
    first_seen                TEXT,
    last_fetched              TEXT,
    contributing_sources      TEXT,
    review_candidates         TEXT,
    unresolved_parent         INTEGER DEFAULT 0,
    raw                       TEXT
);
CREATE TABLE IF NOT EXISTS runs (
    run_id       TEXT PRIMARY KEY,
    started_at   TEXT,
    finished_at  TEXT,
    sources      TEXT,
    inserted     INTEGER DEFAULT 0,
    updated      INTEGER DEFAULT 0,
    unchanged    INTEGER DEFAULT 0,
    pruned       INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS opportunity_history (
    stable_key TEXT NOT NULL,
    field      TEXT NOT NULL,
    label      TEXT,
    before     TEXT,
    after      TEXT,
    at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_errors (
    run_id  TEXT,
    source  TEXT,
    stage   TEXT,
    message TEXT,
    at      TEXT
);
"""

#: Kept out of SCHEMA and applied *after* the migration: an index over a column
#: the migration is about to add cannot be created before it exists, and on every
#: real database that is exactly the ordering.
INDEXES = """
CREATE INDEX IF NOT EXISTS idx_opp_number ON opportunities(opportunity_number);
CREATE INDEX IF NOT EXISTS idx_opp_close  ON opportunities(close_date);
CREATE INDEX IF NOT EXISTS idx_opp_parent ON opportunities(parent_opportunity_number);
CREATE INDEX IF NOT EXISTS idx_opp_kind   ON opportunities(record_kind);
CREATE INDEX IF NOT EXISTS idx_opp_agency ON opportunities(agency_code);
CREATE INDEX IF NOT EXISTS idx_opp_funder ON opportunities(funder_canonical);
"""


def _declared_columns(table: str) -> list[tuple[str, str]]:
    """(name, type declaration) for one table, read out of SCHEMA itself.

    Parsed rather than repeated so the column list and the schema cannot drift
    apart — the migration below adds whatever SCHEMA gained, which only works if
    it is reading the same text the table was created from.
    """
    body = SCHEMA.split(f"CREATE TABLE IF NOT EXISTS {table} (")[1].split(");")[0]
    out: list[tuple[str, str]] = []
    for line in body.strip().splitlines():
        parts = line.strip().rstrip(",").split(None, 1)
        if parts:
            out.append((parts[0], parts[1] if len(parts) > 1 else "TEXT"))
    return out


_COLUMNS = _declared_columns("opportunities")
_COLUMN_NAMES = [name for name, _ in _COLUMNS]


@dataclass
class UpsertStats:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0

    @property
    def total(self) -> int:
        return self.inserted + self.updated + self.unchanged


class Store:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.executescript(INDEXES)
        self.conn.commit()

    def _migrate(self) -> None:
        """Add columns SCHEMA has gained since this database was created.

        ``CREATE TABLE IF NOT EXISTS`` silently does nothing to an existing
        table, so without this a new field would read fine on a fresh store and
        raise on everybody's actual one. Only additive changes are handled, which
        is all this schema has needed — a column that changes meaning gets a new
        name instead, so an old row is never reinterpreted as something it isn't.
        """
        for table in ("opportunities",):
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

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- upsert -----------------------------------------------------------

    def upsert_all(self, records: list[Opportunity], *, now: str | None = None) -> UpsertStats:
        stamp = now or utc_now()
        stats = UpsertStats()
        for record in records:
            self._upsert_one(record, stamp, stats)
        self.conn.commit()
        return stats

    def _upsert_one(self, record: Opportunity, stamp: str, stats: UpsertStats) -> None:
        row = record.to_row()
        existing = self.conn.execute(
            "SELECT * FROM opportunities WHERE stable_key = ?", (row["stable_key"],)
        ).fetchone()

        if existing is None:
            row["first_seen"] = stamp
            row["last_fetched"] = stamp
            columns = ", ".join(row)
            placeholders = ", ".join(f":{name}" for name in row)
            self.conn.execute(
                f"INSERT INTO opportunities ({columns}) VALUES ({placeholders})", row
            )
            # A record we are seeing for the first time can still have a history,
            # when the source itself reports the deadline it used to have. Without
            # this, an extension announced before we started watching is invisible
            # forever — and 755 of the 1,201 Grants.gov records report one.
            if record.original_close_date and record.original_close_date != record.close_date:
                self._record_changes(
                    {"close_date": record.original_close_date},
                    {"stable_key": row["stable_key"], "close_date": record.close_date},
                    record.first_seen or stamp,
                )
            stats.inserted += 1
            return

        # first_seen is set once and never overwritten, no matter what a later
        # run claims about the record.
        row["first_seen"] = existing["first_seen"] or stamp
        changed = any(
            existing[column] != value
            for column, value in row.items()
            if column not in BOOKKEEPING_COLUMNS
        )

        if not changed:
            # Touch nothing at all — not even last_fetched. Writing a timestamp on
            # every run would make the idempotency check unfalsifiable.
            stats.unchanged += 1
            return

        # Record what moved before overwriting it. The comparison above already
        # had to work this out to decide whether to write at all; keeping the
        # answer is what makes "did anything I was tracking change?" answerable.
        self._record_changes(dict(existing), row, stamp)

        row["last_fetched"] = stamp
        assignments = ", ".join(f"{name} = :{name}" for name in row if name != "stable_key")
        self.conn.execute(
            f"UPDATE opportunities SET {assignments} WHERE stable_key = :stable_key", row
        )
        stats.updated += 1

    def _record_changes(self, before: dict, after: dict, stamp: str) -> None:
        changes = diff_rows(after["stable_key"], before, after, stamp)
        if not changes:
            return
        self.conn.executemany(
            """INSERT INTO opportunity_history (stable_key, field, label, before, after, at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [(c.stable_key, c.field, c.label, c.before, c.after, c.at) for c in changes],
        )

    # -- reads ------------------------------------------------------------

    def all_records(self, *, with_raw: bool = True) -> list[Opportunity]:
        """Every stored record.

        ``with_raw=False`` skips the verbatim source payload. That payload is the
        bulk of the database — tens of megabytes of JSON — and deserializing it
        dominates the read for any caller that only wants the normalized fields,
        which is every caller outside the parse stage.
        """
        if with_raw:
            rows = self.conn.execute("SELECT * FROM opportunities").fetchall()
            return [Opportunity.from_row(dict(row)) for row in rows]

        columns = [name for name in _COLUMN_NAMES if name != "raw"]
        rows = self.conn.execute(f"SELECT {', '.join(columns)} FROM opportunities").fetchall()
        return [Opportunity.from_row({**dict(row), "raw": "{}"}) for row in rows]

    def count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0])

    def count_by_source(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT source, COUNT(*) AS n FROM opportunities GROUP BY source"
        ).fetchall()
        return {row["source"]: row["n"] for row in rows}

    def numbers_present(self) -> set[str]:
        from tools.retrieval.collect.grants.normalize import (
            normalize_opportunity_number,
        )

        rows = self.conn.execute(
            "SELECT opportunity_number FROM opportunities WHERE opportunity_number != ''"
        ).fetchall()
        return {normalize_opportunity_number(row[0]) for row in rows if row[0]}

    # -- prune ------------------------------------------------------------

    def prune(self, today: date | None = None) -> int:
        """Delete records whose last live date has passed.

        Status flags lag reality — funders amend, extend, and reissue — so this
        runs off stored dates rather than trusting the source's own flag. Three
        rules from briefing section 6 are load-bearing here:

        * a null close date means open indefinitely and must survive;
        * a recurring opportunity survives while *any* known due date is future;
        * an overlay expires on its own schedule, independent of its parent.
        """
        today = today or date.today()
        doomed: list[str] = []
        for record in self.all_records():
            if self._is_expired(record, today):
                doomed.append(record.stable_key)
        for key in doomed:
            self.conn.execute("DELETE FROM opportunities WHERE stable_key = ?", (key,))
        self.conn.commit()
        return len(doomed)

    @staticmethod
    def _is_expired(record: Opportunity, today: date) -> bool:
        if record.record_kind == "overlay":
            # An overlay pointing at a still-open parent still dies on its own
            # expiration. The parent is a separate record and is untouched.
            return is_past(record.expiration_date, today)

        known = record.all_due_dates
        if not known:
            return False  # rolling: open indefinitely
        # Every round must have passed. Keying on the displayed date instead would
        # delete a recurring call the moment its nearest round closed, discarding
        # every remaining cycle.
        return all(is_past(value, today) for value in known)

    def vacuum(self, sources: list[str], seen_keys: set[str]) -> int:
        """Delete records a complete run over ``sources`` no longer produces.

        Pruning only removes records whose deadlines have passed, which leaves two
        kinds of row behind forever: an opportunity the funder has withdrawn, and
        a row stranded under an identifier scheme we have since changed. The
        second is what surfaced this — giving NSF's program descriptions a real
        identifier left their old source-local keys sitting alongside the new
        rows as duplicates.

        Only safe after a *complete* pass over a source. A limited or failed
        fetch produces a partial key set, and vacuuming against that would delete
        most of the corpus, so the caller has to assert completeness rather than
        this method assuming it.
        """
        if not sources or not seen_keys:
            return 0
        placeholders = ", ".join("?" for _ in sources)
        rows = self.conn.execute(
            f"SELECT stable_key, source FROM opportunities WHERE source IN ({placeholders})",
            sources,
        ).fetchall()
        doomed = [row["stable_key"] for row in rows if row["stable_key"] not in seen_keys]
        for key in doomed:
            self.conn.execute("DELETE FROM opportunities WHERE stable_key = ?", (key,))
        self.conn.commit()
        return len(doomed)

    # -- full-text search --------------------------------------------------

    def rebuild_search_index(self) -> int:
        """(Re)build the FTS5 index over the searchable text.

        Replaces a Python substring scan over every row on every request. Beyond
        speed, this is what makes ``funder:NIH``, phrases, and negation possible
        at all — a scan can only answer "does this string appear somewhere".

        Rebuilt wholesale rather than kept in sync by trigger: the corpus is a
        few thousand rows, a rebuild takes well under a second, and a trigger
        that silently drifts out of step would make search quietly wrong, which
        is worse than making it briefly stale.
        """
        self.conn.executescript(
            """
            DROP TABLE IF EXISTS opportunity_fts;
            CREATE VIRTUAL TABLE opportunity_fts USING fts5(
                stable_key UNINDEXED,
                title, funder, number, subject, body,
                tokenize = 'porter unicode61'
            );
            """
        )
        rows = self.conn.execute(
            """SELECT stable_key, title, funder_canonical, funder, funder_subunit, agency_code,
                      opportunity_number, activity_codes, assistance_listings,
                      categories, topic_keywords, description, eligibility
               FROM opportunities"""
        ).fetchall()
        self.conn.executemany(
            "INSERT INTO opportunity_fts (stable_key, title, funder, number, subject, body)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    row["stable_key"],
                    row["title"] or "",
                    # Subunit and agency code go in too, so the acronyms people
                    # actually type reach the funder column: "National Institutes
                    # of Health" contains no token "NIH", and funder:NIH finding
                    # nothing is a worse answer than it looks.
                    " ".join(
                        filter(
                            None,
                            (
                                row["funder_canonical"],
                                row["funder"],
                                row["funder_subunit"],
                                row["agency_code"],
                            ),
                        )
                    ),
                    # Activity codes and assistance listings are identifiers a
                    # reader searches by name: "R21", "93.213".
                    " ".join(
                        filter(
                            None,
                            (
                                row["opportunity_number"],
                                row["activity_codes"],
                                row["assistance_listings"],
                            ),
                        )
                    ),
                    f"{row['categories'] or ''} {row['topic_keywords'] or ''}",
                    f"{row['description'] or ''}\n{row['eligibility'] or ''}",
                )
                for row in rows
            ],
        )
        self.conn.commit()
        return len(rows)

    def search_keys(self, expression: str, *, limit: int = 5000) -> list[str] | None:
        """Keys matching an FTS5 expression, best match first.

        ``None`` means the index is missing or the expression is not valid FTS5
        syntax — an unbalanced quote, a bare ``AND``. The caller falls back to a
        plain substring scan rather than showing zero results, because a user who
        typed a stray quote meant to search for something.
        """
        try:
            rows = self.conn.execute(
                """SELECT stable_key FROM opportunity_fts
                   WHERE opportunity_fts MATCH ? ORDER BY rank LIMIT ?""",
                (expression, limit),
            ).fetchall()
        except sqlite3.Error:
            return None
        return [row[0] for row in rows]

    # -- history ----------------------------------------------------------

    def changes_since(self, since: str = "", *, limit: int = 500) -> list[Change]:
        """Reader-visible changes, most recent first."""
        sql = "SELECT * FROM opportunity_history"
        params: tuple = ()
        if since:
            sql += " WHERE at >= ?"
            params = (since,)
        sql += " ORDER BY at DESC, stable_key LIMIT ?"
        rows = self.conn.execute(sql, (*params, limit)).fetchall()
        return [
            Change(
                stable_key=row["stable_key"],
                field=row["field"],
                label=row["label"] or row["field"],
                before=row["before"] or "",
                after=row["after"] or "",
                at=row["at"],
            )
            for row in rows
        ]

    def changes_for(self, stable_key: str) -> list[Change]:
        rows = self.conn.execute(
            "SELECT * FROM opportunity_history WHERE stable_key = ? ORDER BY at DESC",
            (stable_key,),
        ).fetchall()
        return [
            Change(
                stable_key=row["stable_key"],
                field=row["field"],
                label=row["label"] or row["field"],
                before=row["before"] or "",
                after=row["after"] or "",
                at=row["at"],
            )
            for row in rows
        ]

    def live_close_dates(self) -> list[str | None]:
        rows = self.conn.execute("SELECT close_date FROM opportunities").fetchall()
        return [row[0] for row in rows]

    # -- bookkeeping ------------------------------------------------------

    def record_run(
        self,
        run_id: str,
        *,
        started_at: str,
        sources: list[str],
        stats: UpsertStats,
        pruned: int,
    ) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO runs
               (run_id, started_at, finished_at, sources, inserted, updated, unchanged, pruned)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                started_at,
                utc_now(),
                ",".join(sources),
                stats.inserted,
                stats.updated,
                stats.unchanged,
                pruned,
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
