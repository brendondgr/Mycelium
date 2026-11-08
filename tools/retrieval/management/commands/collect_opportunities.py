"""Run the open collector end to end, inside the backend container.

    uv run --project web/backend python web/backend/manage.py collect_opportunities
    uv run --project web/backend python web/backend/manage.py collect_opportunities \\
        --sources nsf,ccf_deadlines --limit 20 --no-extract
    uv run --project web/backend python web/backend/manage.py collect_opportunities \\
        --new-only --no-prune          # the nightly invocation (manual_all.py)

Six steps, in order (plan Phase 12, point 2):

    1. collect     the vendored collector's own four stages — extraction
                    (fetch -> parse -> normalize -> resolve), deduplication,
                    new-item flagging, field validation — over every requested
                    source. Unmodified: this command narrates through the same
                    ``tools.retrieval.collect.runner.Console`` the standalone
                    ``runner.py`` CLI does.
    2. map         ``tools.retrieval.collect.mapping.map_grant`` / ``map_conference``
                    turn each collected record into a ``ContentItem``-shaped dict
                    (plan Phase 3).
    3. ingest       ``tools.retrieval.collect.ingest.upsert_items`` writes them,
                    preserving ``first_seen`` and anything a later stage already
                    settled for that record (plan Phase 4). Deadlines project as
                    a side effect of this step — ``upsert_items`` rebuilds the
                    ``ContentDeadline`` row for every created/updated item, so
                    there is no separate "project deadlines" call here.
    4. extract      Phase 8's schema-checked, verified LLM description, unless
                    ``--no-extract``. ``--new-only`` scopes it to records the
                    collector itself flags as never seen before (the newness
                    gate the standalone project's ``plan_enrichment`` never
                    wired up — plan §8.5/§8.6) — the nightly's realistic
                    tens-of-records-a-day case. Without it, every collected
                    record is a candidate: the one-time backfill.
    5. embed        ``tools.retrieval.collect.ingest.embed_pending`` re-embeds only
                    what extraction actually changed (a content-hash compare),
                    so a night that changes nothing costs no embedding call.
    6. prune        ``tools.retrieval.collect.ingest.prune_expired``, unless
                    ``--no-prune``. The nightly always passes ``--no-prune``:
                    deleting here, before the reminder tick has seen tonight's
                    deadlines, is exactly the R2 ordering bug the daily chain's
                    ``run_reminder_tick -> prune_opportunities`` sequencing
                    exists to prevent (see ``manual_all.py``'s
                    ``CONTAINER_STAGES`` comment). A standalone/manual run
                    prunes by default, since nothing downstream is relying on a
                    deferred delete.

Raw payload runs (~54 MB grants + ~14 MB conferences per live run) are pruned to
the last ``--keep-runs`` (default 7 — a week's worth at one run/night) after a
live fetch. The vendored pipelines' own ``persist()`` already calls
``RawStore.prune_runs`` for exactly this reason, but this command drives the
runner's stage functions directly rather than ``pipeline.persist()`` (it needs
the in-memory records for mapping, not just what the collector's own SQLite
store), so pruning has to happen here instead (plan Phase 12, point 6). Skipped
under ``--skip-fetch``: replaying stored payloads is not evidence anything is
safe to delete, and deleting the very runs being replayed would be actively
counterproductive.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from tools.retrieval.collect.extract import (
    DEFAULT_WORKERS,
    ExtractionInput,
    JsonFileCheckpoint,
    apply_to_metadata,
    run_extraction,
)
from tools.retrieval.collect.ingest import (
    embed_pending,
    ingest_collected,
    prune_expired,
)
from tools.retrieval.collect.mapping import map_conference, map_grant
from tools.retrieval.collect.runner import (
    CONFERENCES,
    DEFAULT_ROOT,
    DOMAINS,
    GRANTS,
    Console,
    RunContext,
    new_run_id,
    sources_for,
    stage_deduplicate,
    stage_extract,
    stage_flag_new,
    stage_validate,
    write_report,
)
from tools.retrieval.models import ContentItem

#: A week's worth of raw payloads at one nightly run apiece — enough to replay
#: any recent night with ``--skip-fetch`` without letting the directory grow
#: toward the ~25 GB/year an unpruned collector would reach (plan Phase 12,
#: point 6).
DEFAULT_KEEP_RUNS = 7

#: JSON-lines file of settled extraction verdicts, so a killed backfill resumes
#: without re-billing the model for a record it already finished (plan §8,
#: risk register: "run once outside the nightly, with per-record
#: checkpointing so an interrupted run resumes"). The nightly's own
#: ``--new-only`` scope never touches an already-settled record at all, so this
#: mostly matters for the one-time backfill, but there is no reason a nightly
#: run should be the *one* extraction pass with no resumption story either.
#:
#: Anchored to ``DEFAULT_ROOT`` rather than to the caller's CWD for the reason
#: spelled out there: a checkpoint the run cannot find is not an error, it is an
#: empty checkpoint, and an empty checkpoint means re-extracting records that
#: were already settled. The file whose whole job is preventing repeated work
#: must not itself depend on which directory you happened to start from.
DEFAULT_CHECKPOINT = DEFAULT_ROOT / "extraction-checkpoint.jsonl"


class Command(BaseCommand):
    help = (
        "Collect grants and conferences from the open registries end to end: "
        "collect -> map -> ingest -> extract -> embed (deadlines project as a "
        "side effect of ingest)."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--domain",
            choices=[*DOMAINS, "all"],
            default="all",
            help="Which corpus to collect (default: all).",
        )
        parser.add_argument(
            "--sources",
            default="",
            help=(
                "Comma-separated source names (default: every registered, "
                "enabled source)."
            ),
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help=(
                "Cap records fetched per source (smoke-testing; never used "
                "by the nightly)."
            ),
        )
        parser.add_argument(
            "--skip-fetch",
            action="store_true",
            help=(
                "Offline replay of the most recently stored raw payloads; "
                "touches no network."
            ),
        )
        parser.add_argument(
            "--run-id",
            default=None,
            help="With --skip-fetch, replay this run id instead of the latest.",
        )
        parser.add_argument(
            "--root",
            default=str(DEFAULT_ROOT),
            help=f"Collector data root (default: {DEFAULT_ROOT}).",
        )
        parser.add_argument(
            "--min-interval",
            type=float,
            default=0.5,
            help=(
                "Minimum seconds between requests to one host (published "
                "per-host floors still apply)."
            ),
        )
        parser.add_argument(
            "--keep-runs",
            type=int,
            default=DEFAULT_KEEP_RUNS,
            help=(
                "Raw payload run directories to keep per domain "
                f"(default: {DEFAULT_KEEP_RUNS})."
            ),
        )
        parser.add_argument(
            "--workers",
            type=int,
            default=DEFAULT_WORKERS,
            help=(
                f"Parallel LLM extraction workers (default: {DEFAULT_WORKERS} -- "
                "measured, no plateau; see EXP-2026-08-007)."
            ),
        )
        parser.add_argument(
            "--extract",
            dest="extract",
            action="store_true",
            default=True,
            help="Run Phase 8 structured extraction after ingest (default: on).",
        )
        parser.add_argument(
            "--no-extract",
            dest="extract",
            action="store_false",
            help=(
                "Skip extraction; ingested records keep whatever search_text "
                "they already had (or none)."
            ),
        )
        parser.add_argument(
            "--new-only",
            action="store_true",
            help=(
                "Restrict extraction to records the collector itself flags "
                "as genuinely new this run (the nightly default). Without "
                "it, every collected record is a candidate -- the one-time "
                "backfill."
            ),
        )
        parser.add_argument(
            "--checkpoint",
            default=str(DEFAULT_CHECKPOINT),
            help=(
                "JSON-lines file of settled extraction verdicts. Pass '' to "
                "disable checkpointing."
            ),
        )
        parser.add_argument(
            "--no-prune",
            action="store_true",
            help=(
                "Keep expired grants/conferences instead of deleting them. "
                "The nightly always passes this -- see the module "
                "docstring's R2 ordering note."
            ),
        )
        parser.add_argument(
            # No short form: Django's own BaseCommand already claims -v for
            # --verbosity (a different, unrelated 0-3 scale).
            "--verbose-collector", action="store_true",
            help="Per-record narration from the collector's own console.",
        )
        parser.add_argument(
            "--quiet-collector", action="store_true",
            help="Collector stage summaries only.",
        )

    def handle(self, *args, **options) -> None:
        domains = (
            list(DOMAINS) if options["domain"] == "all" else [options["domain"]]
        )
        selected = [
            name.strip() for name in options["sources"].split(",") if name.strip()
        ]
        sources = sources_for(domains, selected)

        level = (
            Console.VERBOSE if options["verbose_collector"]
            else Console.QUIET if options["quiet_collector"]
            else Console.NORMAL
        )
        console = Console(level)
        context = RunContext(
            run_id=options["run_id"] or new_run_id(),
            started_at=timezone.now().isoformat(timespec="seconds"),
            root=Path(options["root"]),
            domains=[d for d in domains if d in sources],
            console=console,
            sources=sources,
            limit=options["limit"],
            skip_fetch=options["skip_fetch"],
            requested_run_id=options["run_id"],
            min_interval=options["min_interval"],
        )

        # Stages 1-4 of the vendored collector, run exactly as its own CLI runs
        # them -- see runner.py's module docstring. stage_flag_new's diff
        # against the collector's OWN opportunities.db/conferences.db is what
        # ``--new-only`` reads below (data[domain].new_keys); everything else
        # here is unaware Mycelium exists at all.
        try:
            data = stage_extract(context)
            stage_deduplicate(context, data)
            stage_flag_new(context, data)
            stage_validate(context, data)
        except Exception:
            write_report(context)
            raise
        write_report(context)

        if not options["skip_fetch"]:
            for domain in context.domains:
                pipeline = data[domain].pipeline
                removed = pipeline.raw_store.prune_runs(options["keep_runs"])
                if removed:
                    self.stdout.write(
                        f"prune-runs[{domain}]: removed {len(removed)} old raw run(s), "
                        f"kept the last {options['keep_runs']}."
                    )

        # -- map: collector records -> ContentItem-shaped dicts (plan Phase 3).
        today = timezone.now().date()
        today_iso = today.isoformat()
        now = datetime.now(UTC)
        series_by_key = (
            {s.series_key: s for s in data[CONFERENCES].series}
            if CONFERENCES in data else {}
        )

        mapped: list[dict] = []
        if GRANTS in data:
            for opportunity in data[GRANTS].items:
                item = map_grant(opportunity, today=today)
                if item is not None:  # filtered overlay record (plan Phase 3.1)
                    mapped.append(item)
        if CONFERENCES in data:
            for instance in data[CONFERENCES].items:
                mapped.append(
                    map_conference(
                        instance, series_by_key.get(instance.series_key), now=now
                    )
                )

        if not mapped:
            # Not a warning-and-carry-on. A collection that mapped nothing has
            # failed, and saying so quietly is how it stays failed.
            #
            # This repository has already lost a feature to exactly this shape:
            # `extract_fellowship_constraints` filtered on the wrong source
            # string, matched zero rows on every run, reported success each
            # time, and was documented in the repo map as working for months.
            #
            # The blast radius here is wider. The nightly does not stop when
            # collection returns nothing -- it goes on to rank, slate and report
            # over whatever corpus already exists, so a dead collector produces
            # a perfectly ordinary-looking daily report for as long as it takes
            # somebody to notice the listings have stopped moving.
            raise CommandError(
                "no records were collected at all -- nothing was mapped, so "
                "ingest, extraction and embedding were all skipped. That is a "
                "failed run, not an empty one: check that the sources are "
                "reachable, that at least one adapter is enabled, and that the "
                "collector's own stores under --root are writable."
            )

        # -- ingest: upsert into ContentItem, deadlines project as a side
        # effect. Embedding waits for extraction (D10); pruning waits for
        # --no-prune (R2) -- both happen explicitly, below, not here.
        summary = ingest_collected(
            mapped, embed=False, prune=False, today=today_iso, log=self.stdout.write
        )
        key_to_source = {item["external_id"]: item["source"] for item in mapped}

        # -- extract: Phase 8's verified, schema-checked description (D9/D10).
        extracted = 0
        if options["extract"]:
            # Built from ``key_to_source`` (the *mapped* set), not straight off
            # ``data[...].items`` (the *raw* set): ``map_grant`` returns ``None``
            # for an ``overlay`` record (a NIH policy notice with no deadline of
            # its own, plan Phase 3.1) and that record is never ingested as a
            # ``ContentItem`` -- so extracting it anyway would bill the model for
            # a record the outcomes loop below can never attach anywhere
            # (``key_to_source.get(key)`` returns ``None`` and the outcome is
            # dropped). Filtering here, on the same key the outcomes loop already
            # looks up, keeps the two in lockstep by construction rather than by
            # re-deriving ``map_grant``'s overlay rule a second time.
            records: list[ExtractionInput] = []
            if GRANTS in data:
                records.extend(
                    ExtractionInput.from_opportunity(op)
                    for op in data[GRANTS].items
                    if op.stable_key in key_to_source
                )
            if CONFERENCES in data:
                # map_conference never filters (every instance maps), so this
                # condition is always true today -- kept for symmetry with the
                # grants branch above, so "records only ever holds mapped items"
                # stays true by construction even if that changes later.
                records.extend(
                    ExtractionInput.from_conference(
                        instance, series_by_key.get(instance.series_key)
                    )
                    for instance in data[CONFERENCES].items
                    if instance.instance_key in key_to_source
                )

            only_keys = None
            if options["new_only"]:
                only_keys = set()
                for domain in context.domains:
                    only_keys |= set(data[domain].new_keys)
                self.stdout.write(
                    f"extract: --new-only scoped to {len(only_keys):,} of "
                    f"{len(records):,} collected record(s)."
                )

            checkpoint = (
                JsonFileCheckpoint(options["checkpoint"])
                if options["checkpoint"] else None
            )
            outcomes = run_extraction(
                records,
                max_workers=options["workers"],
                checkpoint=checkpoint,
                only_keys=only_keys,
                # The collector's own cache directory, shared with both
                # pipelines' clients, so a venue page fetched during
                # enrichment is not fetched again here.
                cache_dir=context.root / "cache",
            )
            for key, outcome in outcomes.items():
                source = key_to_source.get(key)
                if source is None:
                    continue
                item = ContentItem.objects.filter(
                    source=source, external_id=key
                ).first()
                if item is None:  # e.g. an overlay grant, filtered before ingest
                    continue
                item.metadata = apply_to_metadata(dict(item.metadata or {}), outcome)
                item.save(update_fields=["metadata"])
                extracted += 1
            self.stdout.write(f"extract: {extracted:,} record(s) settled.")

        # -- embed: only what extraction actually changed the search text for.
        embedded = embed_pending(log=self.stdout.write)

        # -- prune: deferred to the caller by default (R2 -- see this module's
        # docstring and manual_all.py's CONTAINER_STAGES comment).
        pruned = 0
        if not options["no_prune"]:
            pruned = prune_expired(today=today_iso, log=self.stdout.write)

        line = (
            f"collect_opportunities: {summary.created:,} created, "
            f"{summary.updated:,} updated, {extracted:,} extracted, "
            f"{embedded:,} embedded, {pruned:,} pruned."
        )

        # A run that saw nothing at all is a failure wearing a success message.
        #
        # This is the shape that hid the fellowship eligibility engine never
        # running: a queryset filtered on the wrong source matched zero rows,
        # every pass reported success, and nobody noticed for months. The same
        # trap is live here — a killed fetch, a renamed adapter, or a key that
        # drifts between the collector and the mapper all end in "0 created,
        # 0 updated" and exit 0, and the nightly would go on recommending over
        # a corpus that quietly stopped being refreshed.
        #
        # ``seen`` rather than ``created`` is the right test: a healthy re-run
        # over an unchanged corpus legitimately creates and updates nothing
        # (that is the idempotency contract), but it can never *see* nothing.
        if not summary.seen:
            raise CommandError(
                f"{line} — no records were collected at all. That is a failed "
                "run, not an empty one: check that the sources are reachable "
                "and that at least one adapter is enabled."
            )

        self.stdout.write(self.style.SUCCESS(line))
