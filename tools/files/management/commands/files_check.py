"""``manage.py files_check [--fix]``: the store against the database.

Reports folders with no row (orphans on disk) and live rows with no bytes
(orphans in the database). Repairs nothing without ``--fix``: then orphan
folders are removed and rows with no bytes are marked failed.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Check stored files against the database."

    def add_arguments(self, parser):
        parser.add_argument("--fix", action="store_true")

    def handle(self, *args, **opts):
        from tools.files import storage
        from tools.files.models import StoredFile

        root = storage.root()
        rows = {str(r.pk): r for r in StoredFile.objects.filter(purged_at__isnull=True)}
        on_disk = {}
        if root.exists():
            for path in root.glob("*/*/*"):
                if path.is_dir():
                    on_disk[path.name] = path
        disk_orphans = [p for name, p in on_disk.items() if name not in rows]
        db_orphans = [
            r for pk, r in rows.items() if pk not in on_disk and r.deleted_at is None
        ]
        for p in disk_orphans:
            self.stdout.write(f"orphan folder: {p}")
        for r in db_orphans:
            self.stdout.write(f"missing bytes: {r.pk} ({r.filename})")
        if opts["fix"]:
            for p in disk_orphans:
                storage.remove(p)
            for r in db_orphans:
                StoredFile.objects.filter(pk=r.pk).update(
                    status=StoredFile.Status.FAILED,
                    extract_error="missing: bytes not found",
                )
        self.stdout.write(
            f"{len(disk_orphans)} orphan folders, {len(db_orphans)} rows "
            f"without bytes{' (fixed)' if opts['fix'] else ''}."
        )
