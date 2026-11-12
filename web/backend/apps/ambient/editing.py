"""What a project editor can see and change about attribution.

The rules for *who may see what* live here rather than in the views, so they
are one readable place and the views stay thin:

* **A lab project** shows lab-channel messages from that lab's own server that
  were attributed to it — never a DM, never another lab's server.
* **A personal project** shows only its owner's own messages, and only to them.
* **Nothing shows any message text**, because none is kept. What an editor sees
  is when, where, who, how confident, and which of the *project's* terms
  matched — enough to judge an attribution without it becoming a transcript.

A correction is the person's answer and it outranks the scorer's: the reference
is fixed, any observation resting on it is fixed and labelled, and an
append-only :class:`~apps.ambient.models.AttributionCorrection` records the
disagreement with every signal's score so the floor and margin can be set from
evidence (OD-03b).
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from django.db.models import Max

from .models import (
    AttributionCorrection,
    ChannelHint,
    Observation,
    ObservationFeedback,
    PlaceKind,
    RawMessageRef,
    Source,
)

#: How many recent attributions the editor's list shows.
RECENT_LIMIT = 50


class Refused(Exception):
    """The caller may not do this. The message is safe to show them."""


def can_edit(user, project) -> bool:
    """The same authority that edits a project's fundamentals."""
    from apps.accounts.permissions import user_can_edit_lab_profile

    if project.scope_user_id is not None:
        return project.scope_user_id == user.id
    if project.scope_lab_id is not None:
        return user_can_edit_lab_profile(user, project.scope_lab)
    return False


def lab_source(project) -> Source | None:
    """The listening server belonging to a lab project's lab, if there is one."""
    if project.scope_lab_id is None:
        return None
    return (
        Source.objects.filter(
            lab_id=project.scope_lab_id, kind=Source.Kind.DISCORD_GUILD
        )
        .order_by("-consent_state", "-pk")
        .first()
    )


def visible_refs(project, viewer):
    """The attributed messages an editor of ``project`` may see."""
    rows = RawMessageRef.objects.filter(
        project=project, deleted_at__isnull=True, speaker__isnull=False
    ).exclude(place_kind=PlaceKind.DM)
    if project.scope_user_id is not None:
        # A personal project is its owner's alone, DMs included.
        return RawMessageRef.objects.filter(
            project=project, deleted_at__isnull=True, speaker=viewer
        )
    if project.scope_lab_id is not None:
        return rows.filter(source__lab_id=project.scope_lab_id)
    return rows.none()


def heard_channels(source: Source) -> list[dict]:
    """Channels Mylo has heard in a server, newest first, minus excluded ones.

    Drawn from message references — the only record of which channels exist
    that the backend has — so a channel appears once somebody opted in has
    spoken in it.
    """
    excluded = {str(one) for one in (source.excluded_place_ids or [])}
    rows = (
        RawMessageRef.objects.filter(source=source, place_kind=PlaceKind.CHANNEL)
        .exclude(place_id="")
        .values("place_id", "place_label")
        .annotate(last=Max("sent_at"))
        .order_by("-last")
    )
    seen: dict[str, dict] = {}
    for row in rows:
        if row["place_id"] in excluded or row["place_id"] in seen:
            continue
        seen[row["place_id"]] = {
            "place_id": row["place_id"],
            "label": row["place_label"] or "",
        }
    hints = {
        hint.place_id: hint
        for hint in ChannelHint.objects.filter(source=source).select_related(
            "project"
        )
    }
    out = []
    for channel in seen.values():
        hint = hints.get(channel["place_id"])
        out.append(
            {
                **channel,
                "hinted_project": (
                    {"id": str(hint.project_id), "name": hint.project.name}
                    if hint
                    else None
                ),
            }
        )
    return out


def alternatives(project, viewer) -> list[dict]:
    """Where an attribution to ``project`` could be corrected to: only
    projects the editor can see, so the list never names an invite-only
    project to someone outside it."""
    from apps.research import visibility
    from apps.research.models import Project

    if project.scope_lab_id is not None:
        rows = visibility.visible_in_lab(viewer, project.scope_lab).filter(
            is_archived=False
        )
    else:
        rows = Project.objects.filter(scope_user=viewer, is_archived=False)
    return [
        {"id": str(other.pk), "name": other.name}
        for other in rows.exclude(pk=project.pk).order_by("name")
    ]


def _entry(ref) -> dict:
    from apps.core.people import display_name

    attribution = ref.attribution or {}
    matched = (attribution.get("matched") or {}).get(str(ref.project_id), [])
    return {
        "id": ref.pk,
        "sent_at": ref.sent_at.isoformat(),
        "place_kind": ref.place_kind,
        "place_label": ref.place_label,
        "speaker": {"id": ref.speaker_id, "name": display_name(ref.speaker)},
        "confidence": ref.project_confidence,
        "decided_by": attribution.get("decided_by", ""),
        "matched": matched,
        "corrected": bool(attribution.get("corrected")),
    }


def conversation(project, viewer) -> dict:
    """Everything the project page's Conversation card shows."""
    source = lab_source(project)
    refs = (
        visible_refs(project, viewer)
        .select_related("speaker")
        .order_by("-sent_at", "-pk")[:RECENT_LIMIT]
    )
    channels = heard_channels(source) if source is not None else []
    return {
        "scope": project.scope,
        "listening": bool(source and source.listening),
        "channels": channels,
        "hinted_channels": [
            channel["place_id"]
            for channel in channels
            if (channel["hinted_project"] or {}).get("id") == str(project.pk)
        ],
        "attributions": [_entry(ref) for ref in refs],
        "alternatives": alternatives(project, viewer),
    }


def set_hint(project, viewer, place_id: str, *, on: bool) -> dict:
    """Make ``place_id`` a hint for ``project``, or stop it being one.

    A channel hints at most one project, so pointing a channel at this project
    moves it from whichever project it pointed at before — within the same lab,
    which the editor already has authority over.
    """
    source = lab_source(project)
    if source is None:
        raise Refused("Channel hints need the lab's Discord server to be listening.")
    known = {channel["place_id"]: channel for channel in heard_channels(source)}
    place_id = str(place_id)
    if place_id not in known:
        raise Refused("Mylo has not heard that channel in this lab's server.")
    if on:
        ChannelHint.objects.update_or_create(
            source=source,
            place_id=place_id,
            defaults={
                "project": project,
                "place_label": known[place_id]["label"],
                "set_by": viewer,
            },
        )
    else:
        ChannelHint.objects.filter(
            source=source, place_id=place_id, project=project
        ).delete()
    return conversation(project, viewer)


@dataclass(frozen=True)
class Corrected:
    ref: RawMessageRef
    observations: int


def _may_correct(ref, viewer) -> bool:
    """Its speaker, or somebody who may edit the project it is filed under."""
    if ref.speaker_id == viewer.id:
        return True
    if ref.project is None or ref.place_kind == PlaceKind.DM:
        return False
    if ref.project.scope_user_id is not None:
        return False  # somebody else's personal project
    return can_edit(viewer, ref.project) and ref.project.scope_lab_id == getattr(
        ref.source, "lab_id", None
    )


def _may_target(ref, viewer, target) -> bool:
    if target is None:
        return True
    if target.is_archived:
        return False
    if target.scope_user_id is not None:
        # A personal project, and only the speaker's own, and only by them.
        return target.scope_user_id == ref.speaker_id == viewer.id
    if target.scope_lab_id is None:
        return False
    if target.scope_lab_id == getattr(ref.source, "lab_id", None):
        return True
    # A DM, or a server of a different lab: only the speaker, and only onto a
    # project they are on — the same hard filter attribution itself applies.
    return (
        ref.speaker_id == viewer.id
        and target.memberships.filter(user_id=viewer.id).exists()
    )


@transaction.atomic
def correct(ref_id: int, viewer, target) -> Corrected:
    """A person says which project this message was really about."""
    ref = (
        RawMessageRef.objects.select_related("project", "source", "speaker")
        .filter(pk=ref_id, deleted_at__isnull=True)
        .first()
    )
    if ref is None or not _may_correct(ref, viewer):
        raise Refused("You can't correct that attribution.")
    if not _may_target(ref, viewer, target):
        raise Refused("That message can't be filed under that project.")

    attribution = dict(ref.attribution or {})
    AttributionCorrection.objects.create(
        ref=ref,
        source=ref.source,
        from_project=ref.project,
        to_project=target,
        from_confidence=ref.project_confidence,
        scores=attribution.get("scores") or {},
        corrected_by=viewer,
    )
    attribution["corrected"] = True
    attribution["decided_by"] = "corrected"
    ref.project = target
    ref.project_confidence = 1.0 if target is not None else 0.0
    ref.attribution = attribution
    ref.save(update_fields=["project", "project_confidence", "attribution"])

    touched = 0
    for observation in Observation.objects.filter(source=ref.source):
        if ref.external_id not in (observation.external_message_ids or []):
            continue
        observation.project = target
        observation.project_confidence = 1.0 if target is not None else None
        observation.save(update_fields=["project", "project_confidence"])
        ObservationFeedback.objects.create(
            observation=observation,
            user=viewer,
            verdict=ObservationFeedback.Verdict.CORRECTED,
            corrected_text=(
                f"About {target.name}."
                if target is not None
                else "Not about a project."
            ),
            channel=ObservationFeedback.Channel.WEB_REVIEW,
        )
        touched += 1
    return Corrected(ref=ref, observations=touched)
