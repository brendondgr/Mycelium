"""The evolving profile layer: findings become understanding (Plan 05).

Runs nightly after deliberation. It turns what Plan 04 decided into the two
stores Plan 05 keeps, beside — never inside — the declared profile:

* **Conversational edges** in the knowledge core, one per (person, concept,
  relation), for a ``suggest`` or ``capability`` finding. Born ``pending``: a
  pending edge ranks nothing and nobody else can read it (principle 9, 19).
  Plan 06 asks; a yes makes it ``active``, from the next nightly run.
* **Project developments** (:class:`~.models.ProjectDevelopment`): a fact told
  to Mylo directly is ``active`` at once, with undo (OD-A3); one seen
  consistently in ambient talk is ``pending``. A later development on the same
  subject supersedes the earlier.

And it keeps both honest over time:

* **Fade.** A confirmed curiosity nobody came back to for two half-lives is
  ``faded`` — it stops ranking, stays visible, and can be kept again.
* **Retractions.** When evidence is deleted (a platform deletion, "forget
  that", an opt-out), its pointers leave every edge and development; a pending
  edge or development with nothing left behind it goes too.

Nothing here writes ``Profile.interests`` or ``ProjectState`` — that is Plan
08's proposal path, and only on a yes.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import (
    PERSONAL_KINDS,
    Change,
    Finding,
    Observation,
    ProjectDevelopment,
    UnderstandingKind,
)

logger = logging.getLogger(__name__)

#: Kinds whose conversational edge decays; the rest are slow and do not.
DECAYING = frozenset({UnderstandingKind.CURRENT_CURIOSITY})


@dataclass
class EvolveRun:
    edges: int = 0
    developments: Counter = field(default_factory=Counter)
    superseded: int = 0
    faded: int = 0
    retractions: int = 0

    def as_dict(self) -> dict:
        data = dict(self.__dict__)
        data["developments"] = dict(self.developments)
        return data


def evidence_items(observation_ids) -> list[str]:
    """How an observation is cited on an edge: an id, never text."""
    return [f"obs:{pk}" for pk in observation_ids]


# -- findings → understanding ---------------------------------------------------------


def _edges(run: EvolveRun, now) -> None:
    from apps.knowledge.service import record_conversational

    findings = Finding.objects.filter(
        outcome__in=[Finding.Outcome.SUGGEST, Finding.Outcome.CAPABILITY],
        user__isnull=False,
        project__isnull=True,
        understanding_kind__in=list(PERSONAL_KINDS),
    ).select_related("user")
    for finding in findings:
        if not finding.observation_ids:
            continue
        view = record_conversational(
            finding.user,
            surface=finding.topic,
            relation=finding.relation,
            evidence=evidence_items(finding.observation_ids),
            weight=max(0.0, finding.influence),
            half_life_days=(
                float(settings.AMBIENT_HALF_LIFE_DAYS)
                if finding.understanding_kind in DECAYING
                else None
            ),
            concept_id=finding.concept_id,
            qualifier=finding.understanding_kind,
        )
        if view is None:
            continue
        run.edges += 1
        if finding.handled_outcome != finding.outcome:
            Finding.objects.filter(pk=finding.pk).update(
                handled_outcome=finding.outcome, handled_at=now
            )


def _latest_change(observations: list[Observation]) -> str:
    changes = [o.change for o in observations if o.change]
    return changes[-1] if changes else Change.OTHER


def _supersede(development: ProjectDevelopment, run: EvolveRun, now) -> None:
    """A later development on the same subject retires the earlier ones."""
    earlier = ProjectDevelopment.objects.filter(
        project=development.project,
        concept=development.concept,
        visibility=development.visibility,
        status__in=[
            ProjectDevelopment.Status.PENDING,
            ProjectDevelopment.Status.ACTIVE,
            ProjectDevelopment.Status.CONFIRMED,
        ],
        occurred_on__lte=development.occurred_on,
    ).exclude(pk=development.pk)
    if development.visibility != "lab":
        earlier = earlier.filter(speaker=development.speaker)
    for row in earlier:
        row.status = ProjectDevelopment.Status.SUPERSEDED
        row.save(update_fields=["status", "updated_at"])
        if development.supersedes_id is None:
            development.supersedes = row
            development.save(update_fields=["supersedes", "updated_at"])
        run.superseded += 1


def _developments(run: EvolveRun, now) -> None:
    findings = Finding.objects.filter(
        project__isnull=False,
        understanding_kind=UnderstandingKind.PROJECT_DEVELOPMENT,
        outcome__in=[Finding.Outcome.RECORD, Finding.Outcome.SUGGEST],
    ).select_related("project")
    for finding in findings:
        observations = list(
            Observation.objects.filter(pk__in=finding.observation_ids).order_by(
                "observed_at", "pk"
            )
        )
        if not observations:
            continue
        told = finding.outcome == Finding.Outcome.RECORD
        if told:
            anchor = [
                o
                for o in observations
                if o.explicit and o.force in ("fact", "decision")
            ][-1:] or observations[-1:]
        else:
            anchor = observations[-1:]
        latest = anchor[0]
        # One development per thing that happened: keyed by the finding and
        # the observation it rests on, so rerunning the night changes nothing
        # and an undone development is not brought back.
        if ProjectDevelopment.objects.filter(
            finding=finding, observation_ids__contains=[latest.pk]
        ).exists():
            continue
        with transaction.atomic():
            development = ProjectDevelopment.objects.create(
                project=finding.project,
                speaker=latest.speaker,
                change=latest.change or _latest_change(observations),
                topic=finding.topic,
                concept_id=finding.concept_id,
                text=latest.text,
                explanation=finding.explanation,
                force=latest.force,
                occurred_on=timezone.localtime(latest.observed_at).date(),
                status=(
                    ProjectDevelopment.Status.ACTIVE
                    if told
                    else ProjectDevelopment.Status.PENDING
                ),
                origin=(
                    ProjectDevelopment.Origin.TOLD
                    if told
                    else ProjectDevelopment.Origin.CONVERSATION
                ),
                visibility=finding.visibility,
                finding=finding,
                observation_ids=[o.pk for o in observations],
            )
            _supersede(development, run, now)
            Finding.objects.filter(pk=finding.pk).update(
                handled_outcome=finding.outcome, handled_at=now
            )
        run.developments[development.status] += 1


# -- keeping it honest ----------------------------------------------------------------


def _fade(run: EvolveRun, now) -> None:
    """A confirmed curiosity with no reinforcement for two half-lives fades."""
    from apps.knowledge.service import fade, unreinforced_since

    cutoff = now - timedelta(days=2 * float(settings.AMBIENT_HALF_LIFE_DAYS))
    for view in unreinforced_since(
        cutoff, qualifier=UnderstandingKind.CURRENT_CURIOSITY
    ):
        if view.user_id is None:
            continue
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.filter(pk=view.user_id).first()
        if user is not None and fade(user, view.concept_id, view.relation):
            run.faded += 1


def _people_citing(observation_ids: set[int]) -> set[int]:
    people = set()
    for user_id, ids in Finding.objects.filter(user__isnull=False).values_list(
        "user_id", "observation_ids"
    ):
        if observation_ids & set(ids or []):
            people.add(user_id)
    return people


def _retractions(run: EvolveRun, now) -> None:
    """Take deleted evidence back out of everything Plan 05 built on it."""
    from django.contrib.auth import get_user_model

    from apps.knowledge.service import drop_evidence

    from .read import mark_recomputed, pending_retractions

    User = get_user_model()
    for retraction in pending_retractions():
        ids = {int(pk) for pk in retraction.observation_ids or []}
        people = _people_citing(ids)
        if retraction.user_id:
            people.add(retraction.user_id)
        for user in User.objects.filter(pk__in=people):
            drop_evidence(user, evidence_items(sorted(ids)))
        for development in ProjectDevelopment.objects.exclude(
            status=ProjectDevelopment.Status.REJECTED
        ):
            kept = [pk for pk in development.observation_ids if pk not in ids]
            if kept == development.observation_ids:
                continue
            development.observation_ids = kept
            fields = ["observation_ids", "updated_at"]
            if not kept and development.status in (
                ProjectDevelopment.Status.PENDING,
                ProjectDevelopment.Status.ACTIVE,
            ):
                development.status = ProjectDevelopment.Status.REJECTED
                development.decided_at = now
                fields += ["status", "decided_at"]
            development.save(update_fields=fields)
        for finding in Finding.objects.all():
            kept = [pk for pk in finding.observation_ids if pk not in ids]
            if kept != finding.observation_ids:
                finding.observation_ids = kept
                fields = ["observation_ids", "updated_at"]
                if not kept:
                    # Nothing left to rest on: it is no longer a suggestion,
                    # so nothing tonight may rebuild what was just removed.
                    finding.outcome = Finding.Outcome.IGNORE
                    finding.reason = "retracted"
                    fields += ["outcome", "reason"]
                finding.save(update_fields=fields)
        mark_recomputed(retraction)
        run.retractions += 1


def evolve(*, now=None) -> EvolveRun:
    """The nightly pass. Idempotent: a rerun changes nothing new."""
    now = now or timezone.now()
    run = EvolveRun()
    _retractions(run, now)
    _edges(run, now)
    _developments(run, now)
    _fade(run, now)
    return run


def undo_development(development: ProjectDevelopment, *, by) -> ProjectDevelopment:
    """Undo a development: it stops counting, stays visible, is not recreated."""
    development.status = ProjectDevelopment.Status.REJECTED
    development.decided_by = by
    development.decided_at = timezone.now()
    development.save(update_fields=["status", "decided_by", "decided_at", "updated_at"])
    return development
