"""Project developments from conversation, proposed as state edits (Plan 08).

A development someone told Mylo or confirmed — "the annotation budget came
through", "we dropped graph neural networks" — may mean the project's stated
state is out of date. It never edits the state: it becomes a
:class:`~tools.delivery.models.ReflectionProposal` on the project page, in the
shape a state PATCH would take, with the development as its evidence, and the
existing accept path (``ReflectionProposalActionView``) is what applies it —
for an editor of the project only. A personal development (said in a DM) is
proposed to the person who said it; a lab one to the lab's PI, owners and
admins.

Deterministic: which blocker or method a development names is the literal
match the alerts use (``matchers/developments.py``). Proposals expire in 14
days and a declined one is not raised again for 28, like every reflection.
"""

from __future__ import annotations

from datetime import date, timedelta

from apps.ambient.read import developments_to_propose
from django.utils import timezone

from tools.delivery.matchers.developments import names
from tools.delivery.models import ReflectionProposal

EXPIRY_DAYS = 14
COOLDOWN_DAYS = 28


def _editors(project) -> list:
    from apps.research.views import _user_can_edit

    people = set(project.members.all())
    if project.scope_user_id:
        people.add(project.scope_user)
    if project.scope_lab_id:
        from apps.accounts.models import LabMembership

        people |= {
            m.user
            for m in LabMembership.objects.filter(lab=project.scope_lab).select_related(
                "user"
            )
        }
    return [person for person in people if _user_can_edit(person, project)]


def edit_for(development) -> tuple[str, dict, str] | None:
    """``(kind, PATCH, field)`` for a development, or None when the stated
    state already agrees (or has nothing it names)."""
    state = getattr(development.project, "state", None)
    slow = dict(getattr(state, "slow", None) or {})
    topic = development.topic
    if development.change == "blocker_closed":
        blockers = list(slow.get("blockers") or [])
        kept = [b for b in blockers if not names(topic, str(b.get("text") or ""))]
        if len(kept) == len(blockers):
            return None
        return (
            ReflectionProposal.Kind.CLOSE_BLOCKER,
            {"slow": {"blockers": kept}},
            "slow.blockers",
        )
    methods = list(slow.get("method") or [])
    if development.change == "method_dropped":
        kept = [m for m in methods if not names(topic, str(m))]
        if len(kept) == len(methods):
            return None
        return (
            ReflectionProposal.Kind.DROP_METHOD,
            {"slow": {"method": kept}},
            "slow.method",
        )
    if development.change == "method_adopted":
        if any(names(topic, str(m)) for m in methods):
            return None
        return (
            ReflectionProposal.Kind.ADD_METHOD,
            {"slow": {"method": methods + [topic]}},
            "slow.method",
        )
    return None


def withdraw_stale() -> int:
    """Expire pending proposals whose development is no longer in effect —
    undone, declined, superseded or forgotten (Plan 08 step 6): a proposal
    must not outlive its only evidence."""
    live = {str(pk) for pk in developments_to_propose().values_list("pk", flat=True)}
    stale = [
        row.pk
        for row in ReflectionProposal.objects.filter(
            status=ReflectionProposal.Status.PENDING,
            evidence__source="conversation",
        ).only("pk", "evidence")
        if str((row.evidence or {}).get("development")) not in live
    ]
    from tools.delivery.models import Notification

    Notification.objects.filter(
        dedupe_key__in=[f"ambient-proposal-{pk}" for pk in stale],
        dismissed_at__isnull=True,
    ).update(dismissed_at=timezone.now())
    return ReflectionProposal.objects.filter(pk__in=stale).update(
        status=ReflectionProposal.Status.EXPIRED, decided_at=timezone.now()
    )


_BELL_TITLES = {
    ReflectionProposal.Kind.CLOSE_BLOCKER: "Is “{topic}” still blocking {project}?",
    ReflectionProposal.Kind.DROP_METHOD: "Did {project} drop {topic}?",
    ReflectionProposal.Kind.ADD_METHOD: "Is {topic} now part of {project}'s method?",
}


def _ring(person, proposal, development) -> None:
    """The bell for a proposal from conversation (Plan 09 step 6), once."""
    from tools.delivery.models import Notification

    title = _BELL_TITLES.get(proposal.kind, "Mylo suggests a change to {project}")
    Notification.objects.get_or_create(
        dedupe_key=f"ambient-proposal-{proposal.pk}",
        defaults={
            "user": person,
            "kind": Notification.Kind.SUGGESTION_PENDING,
            "title": title.format(
                topic=development.topic, project=development.project.name
            )[:500],
            "body": "Heard in conversation. Accept or decline it on the project page.",
            "url": f"/app/projects/{development.project_id}",
        },
    )


def propose(*, today: date | None = None) -> int:
    """Raise tonight's proposals. Idempotent: one per (development, person)."""
    today = today or timezone.localdate()
    withdraw_stale()
    created = 0
    for development in developments_to_propose():
        edit = edit_for(development)
        if edit is None:
            continue
        kind, patch, field = edit
        if development.visibility == "personal":
            targets = [development.speaker] if development.speaker_id else []
        else:
            targets = _editors(development.project)
        for person in targets:
            earlier = ReflectionProposal.objects.filter(
                target_user=person,
                project=development.project,
                kind=kind,
                evidence__development=development.pk,
            )
            if earlier.filter(status=ReflectionProposal.Status.PENDING).exists():
                continue
            if (
                earlier.filter(
                    status=ReflectionProposal.Status.REJECTED,
                    decided_at__gte=timezone.now() - timedelta(days=COOLDOWN_DAYS),
                ).exists()
                or earlier.filter(status=ReflectionProposal.Status.ACCEPTED).exists()
            ):
                continue
            proposal = ReflectionProposal.objects.create(
                target_user=person,
                project=development.project,
                kind=kind,
                proposal=patch,
                evidence={
                    "source": "conversation",
                    "development": development.pk,
                    "topic": development.topic,
                    "field": field,
                    "occurred_on": development.occurred_on.isoformat(),
                    "account": development.text,
                    "explanation": development.explanation
                    or (
                        development.finding.explanation
                        if development.finding_id
                        else ""
                    ),
                    "visibility": development.visibility,
                },
                expires_on=today + timedelta(days=EXPIRY_DAYS),
            )
            _ring(person, proposal, development)
            created += 1
    return created
