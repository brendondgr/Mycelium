"""What changed, what Mylo knows, and the switches — the web's view (Plan 07).

Everything the "Mylo & you" page reads and every edit it makes goes through
here, so who may see and undo what is decided in one place:

* **Changes** (:class:`~.models.AppliedChange`) are a person's own, plus the
  changes to projects they are on that are lab-visible. A change one member
  made privately (a DM about a lab project) is theirs alone.
* **Undo** is never time-limited and never erases: it reverses the effect,
  stamps the original, writes its own row, and tells the evidence (an
  ``ObservationFeedback = rejected`` per observation, channel ``undo``).
* **What Mylo knows** is the person's own edges in the knowledge core, every
  tier, each marked with where it came from; conversational ones are editable
  (an edit is the person's word) and deletable.
* **Settings**: listening per platform, "shut off" for questions, a quiet
  period, and "delete my observations".

Nothing here returns anybody's words from conversation. None are kept.
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import (
    AppliedChange,
    Finding,
    ListeningConsent,
    Observation,
    ObservationFeedback,
    PendingSuggestion,
    Platform,
    ProjectDevelopment,
    Visibility,
)

STORED_STATEMENT = (
    "Mylo does not keep your messages. It keeps short summaries of interests "
    "and project changes, with the dates and the kind of place they came up, "
    "and only after you confirm them do they affect anything."
)
REST_DAYS = 30


# -- recording -----------------------------------------------------------------


def record(
    user,
    kind: str,
    topic: str,
    *,
    project=None,
    surface: str = "",
    suggestion=None,
    development=None,
    finding=None,
    concept_id=None,
    relation: str = "",
    field: str = "",
    old_value=None,
    new_value=None,
    explanation: str = "",
    visibility: str = Visibility.PERSONAL,
    proposal_id: str = "",
) -> AppliedChange:
    return AppliedChange.objects.create(
        user=user,
        kind=kind,
        topic=topic[:200],
        project=project,
        surface=surface,
        suggestion=suggestion,
        development=development,
        finding=finding,
        concept_id=concept_id,
        relation=relation,
        field=field,
        old_value=old_value,
        new_value=new_value,
        explanation=explanation,
        visibility=visibility,
        proposal_id=str(proposal_id or ""),
    )


# -- reading the changes -------------------------------------------------------


def changes_for(user, *, limit: int = 200):
    """A person's own changes, and the lab-visible ones on projects they are on."""
    from apps.research.models import Project

    projects = Project.objects.filter(Q(members=user) | Q(scope_user=user)).values("pk")
    return (
        AppliedChange.objects.filter(
            Q(user=user) | Q(project__in=projects, visibility=Visibility.LAB)
        )
        .select_related("project", "user", "undo_of")
        .distinct()
        .order_by("-created_at", "-pk")[:limit]
    )


def lab_changes(lab, *, limit: int = 200):
    """A lab's changes: lab-visible ones on the lab's shared projects only.

    The rule is the query — a personal change never matches it — so a lab
    surface cannot show one even by mistake (Plan 07, step 7). "Shared" is the
    project's own ``share_in_lab_reports`` opt-in, the rule every lab surface
    uses: a lab project that is not shared is seen by its members and heads
    only, and its changes reach them through their own "What changed".
    """
    return (
        AppliedChange.objects.filter(
            project__scope_lab=lab,
            project__share_in_lab_reports=True,
            visibility=Visibility.LAB,
        )
        .select_related("project", "user")
        .order_by("-created_at", "-pk")[:limit]
    )


def may_undo(change: AppliedChange, user) -> bool:
    """The person it was about; for a lab project's change, its editors too."""
    if change.user_id == user.pk:
        return True
    if change.project_id and change.visibility == Visibility.LAB:
        from .editing import can_edit

        return can_edit(user, change.project)
    return False


# -- undo ----------------------------------------------------------------------


def _feedback_undo(change: AppliedChange, user) -> None:
    ids = []
    if change.finding_id:
        ids = list(change.finding.observation_ids or [])
    elif change.development_id:
        ids = list(change.development.observation_ids or [])
    for observation in Observation.objects.filter(pk__in=ids):
        ObservationFeedback.objects.create(
            observation=observation,
            user=user,
            verdict=ObservationFeedback.Verdict.REJECTED,
            channel=ObservationFeedback.Channel.UNDO,
        )


def undo(change: AppliedChange, *, by, now=None) -> AppliedChange:
    """Reverse one change. Raises ``ValueError`` when it cannot be undone."""
    from apps.knowledge import service

    from .evolve import undo_development

    now = now or timezone.now()
    if not change.undoable:
        raise ValueError("This change has already been undone.")
    with transaction.atomic():
        kind = change.kind
        if (
            kind
            in (
                AppliedChange.Kind.EXPLORATION_CONFIRMED,
                AppliedChange.Kind.EXPLORATION_KEPT,
                AppliedChange.Kind.UNDERSTANDING_CONFIRMED,
            )
            and change.concept_id
        ):
            # An undone yes is a no: it rests, and is not raised again unless
            # the person comes back to it (Plan 08, step 4's cooldown).
            service.reject(change.user, change.concept_id, change.relation)
        elif kind == AppliedChange.Kind.EXPLORATION_DROPPED and change.concept_id:
            service.keep(
                change.user,
                change.concept_id,
                change.relation,
                review_on=timezone.localdate(now)
                + timedelta(days=int(settings.AMBIENT_EXPLORATION_REVIEW_DAYS)),
            )
        elif (
            kind
            in (
                AppliedChange.Kind.DEVELOPMENT_RECORDED,
                AppliedChange.Kind.DEVELOPMENT_CONFIRMED,
            )
            and change.development_id
        ):
            undo_development(change.development, by=by)
        elif kind in (AppliedChange.Kind.PROFILE_EDIT, AppliedChange.Kind.STATE_EDIT):
            from .apply import revert

            revert(change, by=by)
        _feedback_undo(change, by)
        change.undone_at = now
        change.save(update_fields=["undone_at"])
        reversal = record(
            by,
            AppliedChange.Kind.UNDONE,
            change.topic,
            project=change.project,
            surface="web",
            concept_id=change.concept_id,
            relation=change.relation,
            field=change.field,
            old_value=change.new_value,
            new_value=change.old_value,
            visibility=change.visibility,
        )
        reversal.undo_of = change
        reversal.save(update_fields=["undo_of"])
        return reversal


# -- what Mylo knows -----------------------------------------------------------

TIER_LABEL = {
    "declared": "You wrote this",
    "demonstrated": "Your papers show this",
    "conversational": "From conversation",
}


def understanding_for(user) -> dict:
    """Every edge the knowledge core holds about this person, grouped, with
    where it came from; and the project developments they may see."""
    from apps.knowledge.read import own_edges
    from apps.research.models import Project

    from .read import developments_in_effect

    today = timezone.localdate()
    edges = []
    for edge in own_edges(user):
        row = {
            "concept_id": edge.concept_id,
            "label": edge.surface or edge.label,
            "facet": edge.facet,
            "relation": edge.relation,
            "tier": edge.tier,
            "status": edge.status,
            "kind": edge.qualifier,
            "source": TIER_LABEL.get(edge.tier, edge.tier),
            "first_seen": edge.first_seen,
            "last_reinforced": edge.last_reinforced,
            "review_on": edge.review_on,
            "edited": edge.edited_by_person,
            "editable": edge.tier == "conversational",
        }
        if (
            edge.tier == "conversational"
            and edge.status == "rejected"
            and edge.updated_at
        ):
            row["eligible_again_on"] = timezone.localtime(
                edge.updated_at
            ).date() + timedelta(days=REST_DAYS)
            row["resting"] = row["eligible_again_on"] > today
        edges.append(row)
    projects = list(
        Project.objects.filter(Q(members=user) | Q(scope_user=user)).distinct()
    )
    developments = []
    for project in projects:
        for row in developments_in_effect(project, reader=user):
            developments.append(_development_row(row))
    return {
        "statement": STORED_STATEMENT,
        "edges": edges,
        "developments": developments,
    }


def _development_row(row: ProjectDevelopment) -> dict:
    return {
        "id": row.pk,
        "project": {"id": str(row.project_id), "name": row.project.name},
        "change": row.change,
        "change_label": row.get_change_display(),
        "topic": row.topic,
        "account": row.text,
        "explanation": (
            row.explanation or (row.finding.explanation if row.finding_id else "")
        ),
        "occurred_on": row.occurred_on,
        "status": row.status,
        "origin": row.origin,
        "visibility": row.visibility,
    }


def project_developments(project, viewer) -> list[dict]:
    """A project's development timeline, as this viewer may see it: in effect
    or pending, lab-visible, plus the viewer's own private ones."""
    rows = (
        ProjectDevelopment.objects.filter(project=project)
        .filter(
            Q(visibility=Visibility.LAB)
            | Q(visibility=Visibility.PERSONAL, speaker=viewer)
        )
        .exclude(status=ProjectDevelopment.Status.SUPERSEDED)
        .select_related("project", "finding")
    )
    return [_development_row(row) for row in rows.order_by("-occurred_on", "-pk")]


def edit_understanding(user, concept_id: int, relation: str, surface: str) -> bool:
    from apps.knowledge import service

    surface = " ".join((surface or "").split())[:200]
    if not surface:
        return False
    return service.edit_conversational(user, concept_id, relation, surface=surface)


def delete_understanding(user, concept_id: int, relation: str) -> bool:
    """The person deletes one thing Mylo understood: gone, and so are its
    open questions and its finding (it is not re-raised from old evidence)."""
    from apps.knowledge import service

    deleted = service.delete_conversational(user, concept_id, relation)
    if deleted:
        PendingSuggestion.objects.filter(
            user=user,
            concept_id=concept_id,
            relation=relation,
            state__in=PendingSuggestion.OPEN,
        ).update(state=PendingSuggestion.State.WITHDRAWN)
        Finding.objects.filter(
            user=user, concept_id=concept_id, relation=relation
        ).update(outcome=Finding.Outcome.IGNORE, reason="deleted_by_person")
    return bool(deleted)


def reopen(user, concept_id: int, relation: str, *, now=None) -> AppliedChange | None:
    """The person reopens something they declined or let fade: their own yes."""
    from apps.knowledge import service
    from apps.knowledge.read import own_edges

    now = now or timezone.now()
    edge = next(
        (
            e
            for e in own_edges(user)
            if e.tier == "conversational"
            and e.concept_id == concept_id
            and e.relation == relation
            and e.status in ("rejected", "faded")
        ),
        None,
    )
    if edge is None:
        return None
    review = timezone.localdate(now) + timedelta(
        days=int(settings.AMBIENT_EXPLORATION_REVIEW_DAYS)
    )
    service.keep(user, concept_id, relation, review_on=review)
    return record(
        user,
        AppliedChange.Kind.EXPLORATION_CONFIRMED,
        edge.surface or edge.label,
        surface="web",
        concept_id=concept_id,
        relation=relation,
    )


# -- settings ------------------------------------------------------------------


def settings_for(user) -> dict:
    from apps.integrations.models import DiscordIdentity, SlackIdentity, TeamsIdentity

    from .eligibility import ambient_enabled, tier_is_paid

    consent = ListeningConsent.objects.filter(
        user=user, platform=Platform.DISCORD
    ).first()
    from django.conf import settings as django_settings

    return {
        "available": ambient_enabled(),
        # Plan 11: whether meeting transcripts can be uploaded here at all.
        "transcripts": ambient_enabled()
        and bool(getattr(django_settings, "AMBIENT_TRANSCRIPTS_ENABLED", False)),
        "paid": tier_is_paid(user),
        "linked": DiscordIdentity.objects.filter(
            user=user, state=DiscordIdentity.State.ACTIVE
        ).exists(),
        # Slack (Plan 11): its own opt-in, like any platform.
        "slack_linked": SlackIdentity.objects.filter(
            user=user, state=SlackIdentity.State.ACTIVE
        ).exists(),
        "teams_linked": TeamsIdentity.objects.filter(
            user=user, state=TeamsIdentity.State.ACTIVE
        ).exists(),
        "listening": {
            "discord": bool(consent and consent.enabled),
            "slack": ListeningConsent.objects.filter(
                user=user, platform=Platform.SLACK, enabled=True
            ).exists(),
            "teams": ListeningConsent.objects.filter(
                user=user, platform=Platform.TEAMS, enabled=True
            ).exists(),
        },
        "questions_muted": bool(consent and consent.questions_muted),
        "quiet_until": consent.questions_quiet_until if consent else None,
        "statement": STORED_STATEMENT,
        "observations": Observation.objects.filter(speaker=user).count(),
    }


def update_settings(user, data: dict, *, now=None) -> dict:
    """Apply the switches the person changed. Free tiers may only turn off."""
    from .dialogue import set_questions
    from .eligibility import tier_is_paid

    now = now or timezone.now()
    consent, _ = ListeningConsent.objects.get_or_create(
        user=user, platform=Platform.DISCORD
    )
    paid = tier_is_paid(user)
    if "listening_discord" in data:
        on = bool(data["listening_discord"]) and paid
        consent.enabled = on
        if on:
            consent.enabled_at = now
        else:
            consent.disabled_at = now
        consent.save(
            update_fields=["enabled", "enabled_at", "disabled_at", "updated_at"]
        )
    for key, platform in (
        ("listening_slack", Platform.SLACK),
        ("listening_teams", Platform.TEAMS),
    ):
        if key not in data:
            continue
        row, _ = ListeningConsent.objects.get_or_create(user=user, platform=platform)
        on = bool(data[key]) and paid
        row.enabled = on
        if on:
            row.enabled_at = now
        else:
            row.disabled_at = now
        row.save(update_fields=["enabled", "enabled_at", "disabled_at", "updated_at"])
    if "questions_muted" in data:
        set_questions(user, on=not bool(data["questions_muted"]), now=now)
    if "quiet_until" in data:
        value = data["quiet_until"] or None
        ListeningConsent.objects.filter(pk=consent.pk).update(
            questions_quiet_until=value, updated_at=now
        )
    return settings_for(user)


def delete_everything(user):
    """ "Delete my observations": every observation and every derived
    influence, now (principle 11)."""
    from .reconcile import forget_person

    return forget_person(user)
