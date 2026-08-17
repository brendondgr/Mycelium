"""Fold a saved extraction checkpoint onto the corpus, without re-running it.

``collect_opportunities`` applies extraction verdicts only after its whole
worker pool has drained. That is fine when the model server is healthy and
wrong when it is not: a single upstream that half-closes a socket leaves a
worker blocked, and every verdict already settled -- potentially thousands --
waits behind it, unwritten. The one-time backfill hit exactly that, with 4,856
of 4,871 records settled and none of them applied.

The checkpoint already holds those verdicts; it is written per record, as each
one settles, precisely so that work survives an interrupted run. This command
finishes the job the checkpoint was keeping safe:

    uv run --project web/backend python web/backend/manage.py \
        apply_extraction_checkpoint --checkpoint <path>

It calls the same :func:`apply_to_metadata` the collector calls, so a record
written here is byte-identical to one written by a clean run. Records whose
verdict is still *retryable* (``model_failed``, ``fetch_failed``, ``thin_page``,
``pending``) are skipped by default rather than written as refusals -- they have
not been decided yet, and writing them would turn "we did not manage to ask"
into "we asked and the answer was no". Re-running ``collect_opportunities``
against the same checkpoint picks them up.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.content.models import ContentItem
from apps.scraper.collect.extract import (
    RETRYABLE_STATUSES,
    ExtractionOutcome,
    apply_to_metadata,
)
from apps.scraper.collect.paths import DEFAULT_ROOT

#: The two areas the open collector sources. Papers and fellowships are written
#: by other pipelines and must never be touched by an extraction verdict.
TYPES = (ContentItem.Type.GRANT, ContentItem.Type.CONFERENCE)


class Command(BaseCommand):
    help = "Apply a saved extraction checkpoint's verdicts to the corpus."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--checkpoint",
            default=str(DEFAULT_ROOT / "extraction-checkpoint.jsonl"),
            help="JSON-lines file of extraction verdicts.",
        )
        parser.add_argument(
            "--include-retryable",
            action="store_true",
            help=(
                "Also write verdicts that are not settled yet. Off by default: "
                "an undecided record is not a refused one."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing anything.",
        )

    def handle(self, *args, **options) -> None:
        path = Path(options["checkpoint"])
        if not path.exists():
            raise CommandError(f"no checkpoint at {path}")

        # Last verdict per key wins: the file is append-only, so a record that
        # was retried appears more than once and only the final line is current.
        verdicts: dict[str, dict] = {}
        malformed = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                # A killed run can leave one truncated trailing line. Tolerated
                # here for the same reason the checkpoint reader tolerates it.
                malformed += 1
                continue
            if isinstance(record, dict) and record.get("key"):
                verdicts[record["key"]] = record

        if not verdicts:
            raise CommandError(
                f"{path} holds no usable verdicts -- nothing to apply. That is a "
                "failed read, not an empty corpus."
            )

        # One query rather than one per record: the corpus is thousands of rows
        # and the checkpoint is keyed by external_id alone.
        by_external: dict[str, ContentItem] = {}
        for item in ContentItem.objects.filter(type__in=TYPES).only(
            "id", "external_id", "metadata"
        ):
            by_external[item.external_id] = item

        applied = skipped_retryable = unmatched = 0
        by_status: dict[str, int] = {}
        to_write: list[ContentItem] = []

        for key, record in verdicts.items():
            status = record.get("status", "")
            if status in RETRYABLE_STATUSES and not options["include_retryable"]:
                skipped_retryable += 1
                continue
            item = by_external.get(key)
            if item is None:
                # An overlay grant, or a record pruned since the run. Neither is
                # an error: the mapper filters overlays before ingest.
                unmatched += 1
                continue
            outcome = ExtractionOutcome(
                **{k: v for k, v in record.items() if k in ExtractionOutcome.__annotations__}
            )
            item.metadata = apply_to_metadata(dict(item.metadata or {}), outcome)
            to_write.append(item)
            applied += 1
            by_status[status] = by_status.get(status, 0) + 1

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run — nothing written."))
        else:
            ContentItem.objects.bulk_update(to_write, ["metadata"], batch_size=500)

        self.stdout.write(f"checkpoint      : {path}")
        self.stdout.write(f"verdicts read   : {len(verdicts):,}")
        if malformed:
            self.stdout.write(f"malformed lines : {malformed}")
        self.stdout.write(f"applied         : {applied:,}")
        for status, n in sorted(by_status.items(), key=lambda kv: -kv[1]):
            self.stdout.write(f"    {status:<16}{n:>6}")
        self.stdout.write(f"skipped (retryable): {skipped_retryable:,}")
        self.stdout.write(f"unmatched          : {unmatched:,}")
