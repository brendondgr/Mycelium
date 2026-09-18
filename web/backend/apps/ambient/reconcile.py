"""Keeping the ledger honest when the conversation behind it changes.

A message is edited, a message is deleted, a person asks for evidence to be
removed, somebody opts out entirely. Each of these makes something Mylo
understood wrong or unwanted, and each has to reach whatever was built on it.

The rules:

* An **edit** invalidates the reading, not the record. The reference is updated
  and every observation resting on that message is marked ``stale``, so Plan 04
  re-extracts it rather than carrying an out-of-date understanding forward.
* A **deletion** removes the evidence. The body is dropped, the reference is
  tombstoned, and every observation citing that message is deleted outright —
  not hidden, not flagged.
* Anything that deletes leaves a :class:`~apps.ambient.models.Retraction`
  naming what went, so the influence it had can be taken back out. Plans 05 and
  08 subscribe to those rows; until they exist the rows simply wait, which is
  the correct behaviour rather than a gap.

A retraction never holds the text it retracted. Recording what was removed by
copying it would defeat the whole point.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from . import buffer
from .ingest import find_repeat_root
from .models import Observation, RawMessageRef, Retraction, Source
from .text import content_hash

logger = logging.getLogger(__name__)


def _observations_citing(source: Source, external_id: str):
    """Observations whose evidence includes ``external_id``.

    ``external_message_ids`` is a JSON list, and the containment lookup is not
    available on every backend this runs on, so the filter is narrowed in the
    database by source and finished in Python. The candidate set is one source's
    observations, which is small enough for this to be the honest trade.
    """
    candidates = Observation.objects.filter(source=source).filter(
        Q(external_message_ids__isnull=False)
    )
    return [
        observation
        for observation in candidates
        if external_id in (observation.external_message_ids or [])
    ]


@transaction.atomic
def message_edited(source: Source, external_id: str, text: str, *, edited_at=None):
    """A message was edited on the platform.

    The new text replaces the old in the buffer, the hash and the repeat
    linkage are recomputed, and every observation resting on this message is
    marked stale so it is read again rather than trusted.
    """
    ref = RawMessageRef.objects.filter(
        source=source, external_id=external_id, deleted_at__isnull=True
    ).first()
    if ref is None:
        return 0

    ttl = buffer.ttl_seconds(source)
    held = buffer.put(source.pk, external_id, text, ttl=ttl) if text else False

    digest = content_hash(text)
    ref.content_hash = digest
    ref.edited_at = edited_at or timezone.now()
    ref.buffered_until = (
        timezone.now() + timedelta(seconds=ttl) if held else None
    )
    # The edited text may now repeat something else, or nothing.
    ref.repeat_of = None
    ref.save(
        update_fields=["content_hash", "edited_at", "buffered_until", "repeat_of"]
    )
    if ref.speaker_id is not None:
        root = find_repeat_root(ref.speaker, digest, before=ref.sent_at)
        if root is not None and root.pk != ref.pk:
            ref.repeat_of = root
            ref.save(update_fields=["repeat_of"])

    # Anything that repeated the old text is no longer repeating this. Re-root
    # each orphan on its own terms rather than leaving it pointing at text that
    # is gone.
    for child in list(ref.repeats.all()):
        child.repeat_of = None
        child.save(update_fields=["repeat_of"])
        root = find_repeat_root(child.speaker, child.content_hash, before=child.sent_at)
        if root is not None and root.pk != child.pk:
            child.repeat_of = root
            child.save(update_fields=["repeat_of"])

    stale = _observations_citing(source, external_id)
    for observation in stale:
        observation.status = Observation.Status.STALE
        observation.save(update_fields=["status"])
    return len(stale)


@transaction.atomic
def message_deleted(source: Source, external_id: str) -> Retraction | None:
    """A message was deleted on the platform. Its evidence goes with it."""
    ref = RawMessageRef.objects.filter(
        source=source, external_id=external_id
    ).first()
    buffer.drop(source.pk, [external_id])

    observations = _observations_citing(source, external_id)
    observation_ids = [observation.pk for observation in observations]
    project_ids = sorted(
        {
            str(observation.project_id)
            for observation in observations
            if observation.project_id
        }
    )
    speaker = ref.speaker if ref is not None else None
    if observations:
        Observation.objects.filter(pk__in=observation_ids).delete()

    if ref is not None:
        # A tombstone, not a row: the id stays so the same message arriving
        # again from a gateway replay is not re-recorded, and the hash goes so
        # it can never be matched as a repeat.
        ref.deleted_at = timezone.now()
        ref.content_hash = ""
        ref.buffered_until = None
        ref.attachment_urls = []
        ref.save(
            update_fields=[
                "deleted_at",
                "content_hash",
                "buffered_until",
                "attachment_urls",
            ]
        )

    if not observation_ids:
        return None
    return Retraction.objects.create(
        reason=Retraction.Reason.PLATFORM_DELETE,
        user=speaker,
        source=source,
        observation_ids=observation_ids,
        project_ids=project_ids,
        note="a message was deleted on the platform",
    )


@transaction.atomic
def forget_observations(
    user: User, observation_ids, *, reason=Retraction.Reason.PERSON_REQUEST
) -> Retraction | None:
    """Remove specific evidence at the person's request, and say what it touched."""
    rows = list(Observation.objects.filter(speaker=user, pk__in=list(observation_ids)))
    if not rows:
        return None
    ids = [row.pk for row in rows]
    project_ids = sorted({str(row.project_id) for row in rows if row.project_id})
    Observation.objects.filter(pk__in=ids).delete()
    return Retraction.objects.create(
        reason=reason,
        user=user,
        observation_ids=ids,
        project_ids=project_ids,
        note="the person removed this evidence",
    )


@transaction.atomic
def forget_person(user: User) -> Retraction:
    """"Delete my observations": everything derived from this person, gone.

    Every observation, every verdict they gave, every reference, and every body
    still sitting in the buffer. The retraction that survives names what has to
    be recomputed and holds nothing but ids — it is the receipt, not a copy.
    """
    observations = list(Observation.objects.filter(speaker=user))
    observation_ids = [observation.pk for observation in observations]
    project_ids = sorted(
        {
            str(observation.project_id)
            for observation in observations
            if observation.project_id
        }
    )

    refs = list(RawMessageRef.objects.filter(speaker=user))
    by_source: dict[int, list[str]] = {}
    for ref in refs:
        by_source.setdefault(ref.source_id, []).append(ref.external_id)
    for source_id, external_ids in by_source.items():
        buffer.drop(source_id, external_ids)

    # Feedback rows cascade from the observations; anything the person left on
    # somebody else's observation goes here.
    Observation.objects.filter(pk__in=observation_ids).delete()
    RawMessageRef.objects.filter(speaker=user).delete()
    user.ambient_feedback.all().delete()

    logger.info(
        "ambient: forgot %s observations and %s references for user %s",
        len(observation_ids),
        len(refs),
        user.pk,
    )
    return Retraction.objects.create(
        reason=Retraction.Reason.OPT_OUT,
        user=user,
        observation_ids=observation_ids,
        project_ids=project_ids,
        note="the person opted out and asked for deletion",
    )


@transaction.atomic
def revoke_source(source: Source, *, delete_observations: bool = False):
    """A surface withdrew consent. Listening stops at once.

    Observations are **not** deleted by default: they are the people's own
    record, not the server's, and a lab turning the feature off does not entitle
    it to erase what its members confirmed about themselves. Deletion is
    available, and when it is used it leaves a retraction like any other.
    """
    source.consent_state = Source.Consent.REVOKED
    source.consent_changed_at = timezone.now()
    source.save(update_fields=["consent_state", "consent_changed_at"])

    external_ids = list(
        RawMessageRef.objects.filter(source=source).values_list(
            "external_id", flat=True
        )
    )
    buffer.drop(source.pk, external_ids)
    RawMessageRef.objects.filter(source=source).update(buffered_until=None)

    if not delete_observations:
        return None

    observations = list(Observation.objects.filter(source=source))
    observation_ids = [observation.pk for observation in observations]
    project_ids = sorted(
        {
            str(observation.project_id)
            for observation in observations
            if observation.project_id
        }
    )
    Observation.objects.filter(pk__in=observation_ids).delete()
    return Retraction.objects.create(
        reason=Retraction.Reason.SOURCE_REVOKED,
        source=source,
        observation_ids=observation_ids,
        project_ids=project_ids,
        note="the surface withdrew consent and its evidence was deleted",
    )
