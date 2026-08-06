"""Compile the nightly internal usage analytics: a JSON summary and a PDF.

The measurement stage of the daily run. It writes two artifacts and posts
nothing itself:

* ``data/logs/mylo-run-analytics.json`` — the metrics, read by ``manual_all.py``
  on the host to build the Discord "Daily run complete" message. The host runner
  has no Django and no database, so a file under the shared ``data/`` bind mount
  is the seam between the two halves.
* ``data/analytics/mycelium-run-analytics-<date>.pdf`` — the report attached
  beneath that message.

Kept as its own command, and run *after* the pipeline stages rather than as one
of them, for one reason: a broken chart or an unwritable directory must never
turn a good night's run into a failed one. The daily orchestrator treats a
non-zero exit here as a note, not a failure.

    manage.py run_analytics_report [--date YYYY-MM-DD] [--no-pdf] [--stdout]

(prefix with `uv run --project web/backend python web/backend/`.)
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = "Compile the daily internal usage analytics (JSON + PDF)."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--date",
            dest="day",
            help="The run date to measure (YYYY-MM-DD). Defaults to today.",
        )
        parser.add_argument(
            "--no-pdf",
            action="store_true",
            help="Collect and write the JSON, but skip rendering the PDF.",
        )
        parser.add_argument(
            "--stdout",
            action="store_true",
            help="Also print the metrics as JSON.",
        )
        parser.add_argument(
            "--json-path",
            help="Override the metrics path (default RUN_ANALYTICS_JSON_PATH).",
        )
        parser.add_argument(
            "--pdf-dir",
            help="Override the PDF directory (default RUN_ANALYTICS_PDF_DIR).",
        )

    def handle(self, *args, **options) -> None:
        from apps.content.run_analytics import collect_run_analytics

        day = self._resolve_day(options.get("day"))
        data = collect_run_analytics(day)
        payload = data.as_dict()

        json_path = Path(
            options.get("json_path") or settings.RUN_ANALYTICS_JSON_PATH
        )
        pdf_dir = Path(options.get("pdf_dir") or settings.RUN_ANALYTICS_PDF_DIR)

        if not options.get("no_pdf"):
            pdf_path = self._render_pdf(data, pdf_dir)
            if pdf_path is not None:
                payload["pdf_path"] = str(pdf_path)
                payload["pdf_filename"] = pdf_path.name

        self._write_json(json_path, payload)

        if options.get("stdout"):
            self.stdout.write(json.dumps(payload, indent=2))

        self.stdout.write(self.style.SUCCESS(data.headline()))
        self.stdout.write(
            f"analytics: {payload['llm']['calls']} LLM call(s), "
            f"{payload['llm']['failures']} failed, "
            f"{payload['llm']['total_tokens']:,} token(s); "
            f"{payload['delivery']['briefings_generated']} report(s) generated, "
            f"{payload['delivery']['reports_delivered']} delivered."
        )

    # -- steps -------------------------------------------------------------- #
    def _resolve_day(self, raw: str | None) -> date:
        if not raw:
            return timezone.localdate()
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError as exc:
            raise CommandError(f"--date must be YYYY-MM-DD, got {raw!r}") from exc

    def _render_pdf(self, data, pdf_dir: Path) -> Path | None:
        """Render the PDF, or warn and continue — the metrics matter more."""
        from apps.content.analytics_report_pdf import render_analytics_pdf

        try:
            pdf_dir.mkdir(parents=True, exist_ok=True)
            path = pdf_dir / f"mycelium-run-analytics-{data.generated_on}.pdf"
            path.write_bytes(render_analytics_pdf(data))
        except Exception as exc:  # noqa: BLE001 — never fail the run over a chart
            self.stderr.write(f"analytics PDF not written: {exc}")
            return None
        self.stdout.write(f"analytics PDF: {path}")
        self._sweep(pdf_dir, keep=path)
        return path

    def _sweep(self, pdf_dir: Path, *, keep: Path) -> None:
        """Delete reports past the retention window. Best-effort, never fatal.

        These are not the source of truth for anything — the numbers stay in the
        database and can be re-rendered for any past day with ``--date`` — so an
        old PDF is a convenience, and one a day kept forever is a disk leak.
        """
        days = int(getattr(settings, "RUN_ANALYTICS_RETENTION_DAYS", 90) or 0)
        if days <= 0:
            return
        cutoff = timezone.localdate() - timedelta(days=days)
        removed = 0
        for candidate in pdf_dir.glob("mycelium-run-analytics-*.pdf"):
            if candidate == keep:
                continue
            stamp = candidate.stem.rsplit("-", 3)[-3:]
            try:
                when = date(int(stamp[0]), int(stamp[1]), int(stamp[2]))
            except (ValueError, IndexError):
                continue  # not one of ours; leave it alone
            if when < cutoff:
                try:
                    candidate.unlink()
                    removed += 1
                except OSError:
                    pass
        if removed:
            self.stdout.write(f"analytics: pruned {removed} report(s) past {days} days")

    def _write_json(self, json_path: Path, payload: dict) -> None:
        try:
            json_path.parent.mkdir(parents=True, exist_ok=True)
            json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError as exc:
            raise CommandError(f"could not write {json_path}: {exc}") from exc
        self.stdout.write(f"analytics metrics: {json_path}")
