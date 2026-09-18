"""Re-project a profile, lab or project into the graph after it is saved.

The hook only queues. Linking a wording may need the embedder, and a person
saving their profile should not wait on a model load; the Celery task does the
work, and the nightly sweep catches anything a missed hook left behind.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.accounts.models import LabProfile, Profile
from apps.research.models import Project, ProjectState

logger = logging.getLogger(__name__)


def _queue(kind: str, pk) -> None:
    from .tasks import project_subject

    try:
        project_subject.delay(kind, str(pk))
    except Exception:  # noqa: BLE001 - a broker outage must never fail a save
        logger.warning("could not queue a %s projection for %s", kind, pk)


def _after_commit(kind: str, pk) -> None:
    if settings.KNOWLEDGE_PROJECT_ON_SAVE:
        transaction.on_commit(lambda: _queue(kind, pk))


def _touches(update_fields, *names: str) -> bool:
    """A save that names its fields and none of ours cannot change the graph."""
    return update_fields is None or bool(set(update_fields) & set(names))


@receiver(post_save, sender=Profile)
def profile_saved(sender, instance, update_fields=None, **kwargs) -> None:
    if _touches(update_fields, "interests"):
        _after_commit("user", instance.user_id)


@receiver(post_save, sender=LabProfile)
def lab_profile_saved(sender, instance, update_fields=None, **kwargs) -> None:
    if _touches(update_fields, "interests", "areas"):
        _after_commit("lab", instance.lab_id)


@receiver(post_save, sender=Project)
def project_saved(sender, instance, update_fields=None, **kwargs) -> None:
    if _touches(update_fields, "goals"):
        _after_commit("project", instance.pk)


@receiver(post_save, sender=ProjectState)
def project_state_saved(sender, instance, update_fields=None, **kwargs) -> None:
    if _touches(update_fields, "slow", "fast", "provenance"):
        _after_commit("project", instance.project_id)
