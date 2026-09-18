"""Scheduled and queued work for the knowledge core."""

from __future__ import annotations

from celery import shared_task

from . import papers, projection


@shared_task(name="apps.knowledge.project_subject")
def project_subject(kind: str, pk: str) -> dict:
    """Re-project one saved profile, lab or project."""
    return projection.project_by_key(kind, pk).as_dict()


@shared_task(name="apps.knowledge.sweep")
def sweep() -> dict:
    """Reconcile every declared edge and prune orphaned private concepts."""
    return projection.sweep().as_dict()


@shared_task(name="apps.knowledge.facet_user_works")
def facet_user_works(user_id: str) -> dict:
    """Read one person's papers and rebuild their demonstrated edges."""
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.filter(pk=user_id).first()
    if user is None:
        return {}
    return papers.refresh_person(user).as_dict()
