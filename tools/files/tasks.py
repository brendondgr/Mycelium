"""Celery tasks: extract a large upload's text; purge deleted files' bytes."""

from __future__ import annotations

from celery import shared_task


@shared_task(name="tools.files.tasks.extract")
def extract(file_id: str) -> str:
    from . import service
    from .models import StoredFile

    row = StoredFile.objects.filter(pk=file_id).first()
    if row is None:
        return "missing"
    return service.run_extract(row).status


@shared_task(name="tools.files.tasks.purge_deleted")
def purge_deleted() -> int:
    from . import service

    return service.purge_deleted()
