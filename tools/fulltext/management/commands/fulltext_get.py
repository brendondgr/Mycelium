"""Get papers' full text from the shell, through the same path as everything else.

    manage.py fulltext_get 10.1371/journal.pone.0185809 arXiv:1706.03762 PMC7286232
    manage.py fulltext_get --check-only 10.1016/j.watres.2020.116073
    manage.py fulltext_get --background 32723588        (queue on a worker)

Prints, per identifier, the outcome, the source, the explanation and where the
stored files are. Nothing here is printed that is not also on the request row.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from tools.fulltext import read, service


class Command(BaseCommand):
    help = "Check for, or fetch and store, papers' full text."

    def add_arguments(self, parser):
        parser.add_argument(
            "identifiers",
            nargs="+",
            help="PMIDs, PMCIDs, DOIs, arXiv ids, or paper URLs.",
        )
        parser.add_argument(
            "--check-only",
            action="store_true",
            help="Say whether each paper is within reach; fetch nothing.",
        )
        parser.add_argument(
            "--background",
            action="store_true",
            help="Queue the requests on a Celery worker and return.",
        )

    def handle(self, *args, identifiers, check_only=False, background=False, **options):
        if check_only:
            for res in service.check(identifiers):
                self._line(
                    res["input"], res["availability"], res.get("explanation", "")
                )
                if res.get("will_try"):
                    self.stdout.write(f"    would try: {', '.join(res['will_try'])}")
            return
        reqs = service.request(identifiers, background=background)
        if background:
            for r in reqs:
                self._line(r.identifier, "queued", f"request {r.pk}")
            return
        for r in reqs:
            self._line(r.identifier, r.status, r.explanation)
            if r.document_id:
                doc = read.document_by_id(r.document_id)
                self.stdout.write(f"    markdown: {doc.markdown_path}")
                if doc.original_path:
                    self.stdout.write(f"    original: {doc.original_path}")
            for step in r.next_steps:
                self.stdout.write(f"    next: {step}")

    def _line(self, ident, status, text):
        ok = status in ("full_text", "stored", "open", "subscription", "queued")
        style = self.style.SUCCESS if ok else self.style.WARNING
        self.stdout.write(style(f"{ident}: {status}") + (f" — {text}" if text else ""))
