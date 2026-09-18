"""Scheduled and queued work for the knowledge core."""

from __future__ import annotations

from celery import shared_task

from . import projection


@shared_task(name="apps.knowledge.project_subject")
def project_subject(kind: str, pk: str) -> dict:
    """Re-project one saved profile, lab or project."""
    return projection.project_by_key(kind, pk).as_dict()


@shared_task(name="apps.knowledge.sweep")
def sweep() -> dict:
    """Reconcile every declared edge and prune orphaned private concepts."""
    return projection.sweep().as_dict()
