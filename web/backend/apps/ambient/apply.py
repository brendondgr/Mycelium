"""Applying what a person said yes to — to their own profile (Plan 08).

The only writer of ``Profile.interests`` in the ambient feature. It runs
nightly (``deliberate_ambient``) over answered questions whose yes edits the
declared profile — add to my interests, a new theme, a swap, a skill, a
learning goal, a preference, a direction — and writes each as **the person's
own choice**: through the interests contract (``validate_interests``), with
provenance in ``interests["sources"]["ambient"]`` naming the question, the
date and where it was answered. Each edit is an
:class:`~.models.AppliedChange` holding the field's value before and after, so
an undo can put back exactly what was there (:func:`revert`).

Nothing here decides anything. The person's answer is the decision; this only
carries it out, at the next nightly run, as the question said it would. A stated
field is never touched by anything automatic: every write here traces to one
answered question.

Project state is not written here. A confirmed development becomes a
reflection proposal on the project page (``apps/content/ambient_proposals``),
and the project's editors accept it there.
"""

from __future__ import annotations

import copy
import logging
import re
import unicodedata

from django.db import transaction
from django.utils import timezone

from .models import AppliedChange, PendingSuggestion

logger = logging.getLogger(__name__)

#: ``apps.content.clustering.IMPLICIT_CLUSTER_ID`` — the one theme an
#: unclustered profile behaves as. Named here because this app may not import
#: the matching layer (its boundary test).
IMPLICIT_CLUSTER_ID = "c-all"
IMPLICIT_CLUSTER_LABEL = "All interests"

#: Which choices edit the declared profile, and which field each writes.
EDITS = {
    "interests": "areas",
    "theme": "clusters",
    "swap": "clusters",
    "skill": "skills",
    "learning": "learning_goals",
    "preference": "preferences",
    "direction": "trajectory",
}


def _slug(label: str) -> str:
    text = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.casefold()).strip("-") or "theme"


def _cluster_id(label: str, existing) -> str:
    base = f"c-{_slug(label)}"
    candidate, n = base, 2
    while candidate in existing:
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def _has(values, text: str) -> bool:
    return text.casefold() in {str(v).casefold() for v in values or []}


def edit_for(
    interests: dict, choice: str, topic: str, budget: dict
) -> tuple[dict, str] | None:
    """The interests after this yes, and the field it changed — or None when
    there is nothing to do (already there)."""
    new = copy.deepcopy(interests or {})
    areas = list(new.get("areas") or [])
    clusters = list(new.get("clusters") or [])
    if choice == "interests":
        if _has(areas, topic):
            return None
        new["areas"] = areas + [topic]
        if clusters:
            # Into the theme with the fewest areas: room is what makes this
            # choice offered at all (Plan 04's budget).
            target = min(clusters, key=lambda c: len(c.get("areas") or []))
            target["areas"] = list(target.get("areas") or []) + [topic]
            new["clusters"] = clusters
        return new, "areas"
    if choice in ("theme", "swap"):
        if _has(areas, topic):
            return None
        if not clusters and areas:
            clusters = [
                {
                    "id": IMPLICIT_CLUSTER_ID,
                    "label": IMPLICIT_CLUSTER_LABEL,
                    "areas": areas,
                }
            ]
        if choice == "swap":
            stale = (budget or {}).get("swap_candidate") or {}
            gone = next((c for c in clusters if c.get("id") == stale.get("id")), None)
            if gone is None:
                return None  # the theme to swap out is no longer there
            clusters = [c for c in clusters if c is not gone]
            dropped = {a.casefold() for a in gone.get("areas") or []}
            areas = [a for a in areas if a.casefold() not in dropped]
        clusters.append(
            {
                "id": _cluster_id(topic, {c.get("id") for c in clusters}),
                "label": topic[:1].upper() + topic[1:],
                "areas": [topic],
            }
        )
        new["areas"] = areas + [topic]
        new["clusters"] = clusters
        return new, "clusters"
    field = EDITS.get(choice)
    if field in ("skills", "learning_goals", "preferences"):
        values = list(new.get(field) or [])
        if _has(values, topic):
            return None
        new[field] = values + [topic]
        return new, field
    if field == "trajectory":
        if (new.get("trajectory") or {}).get(
            "direction", ""
        ).casefold() == topic.casefold():
            return None
        new["trajectory"] = {**(new.get("trajectory") or {}), "direction": topic}
        return new, "trajectory"
    return None


def _provenance(
    interests: dict, suggestion: PendingSuggestion, field: str, value
) -> dict:
    sources = dict(interests.get("sources") or {})
    trail = list(sources.get("ambient") or [])
    trail.append(
        {
            "field": field,
            "value": value,
            "suggestion": suggestion.pk,
            "confirmed_on": timezone.localdate().isoformat(),
            "surface": suggestion.answered_on,
            "provenance": "stated",
        }
    )
    sources["ambient"] = trail
    return {**interests, "sources": sources}


def apply_answers(*, now=None) -> dict:
    """Carry out tonight every answered yes that edits the declared profile."""
    from apps.accounts.interests import validate_interests
    from apps.accounts.models import Profile

    from .review import record

    now = now or timezone.now()
    counts = {"applied": 0, "nothing_to_do": 0, "refused": 0}
    pending = PendingSuggestion.objects.filter(
        state=PendingSuggestion.State.ANSWERED,
        applied_at__isnull=True,
        verdict__in=[
            PendingSuggestion.Verdict.CONFIRMED,
            PendingSuggestion.Verdict.CORRECTED,
        ],
    ).select_related("user", "finding")
    for suggestion in pending:
        key = suggestion.choice.split(":", 1)[0]
        if key not in EDITS:
            continue
        topic = (suggestion.correction or suggestion.topic).strip()
        with transaction.atomic():
            profile = (
                Profile.objects.select_for_update().filter(user=suggestion.user).first()
            )
            if profile is None:
                continue
            before = copy.deepcopy(profile.interests or {})
            budget = suggestion.finding.budget if suggestion.finding_id else {}
            edited = edit_for(before, key, topic, budget)
            if edited is None:
                counts["nothing_to_do"] += 1
                PendingSuggestion.objects.filter(pk=suggestion.pk).update(
                    applied_at=now
                )
                continue
            after, field = edited
            try:
                after = validate_interests(
                    _provenance(after, suggestion, field, topic), user=suggestion.user
                )
            except Exception as exc:  # noqa: BLE001 - a refused edit is reported
                logger.warning("ambient: could not apply %s (%s)", suggestion.pk, exc)
                counts["refused"] += 1
                continue
            profile.interests = after
            profile.save(update_fields=["interests"])
            record(
                suggestion.user,
                AppliedChange.Kind.PROFILE_EDIT,
                topic,
                surface=suggestion.answered_on,
                suggestion=suggestion,
                finding=suggestion.finding,
                concept_id=suggestion.concept_id,
                relation=suggestion.relation,
                field=f"interests.{field}",
                old_value=_field_state(before, field),
                new_value=_field_state(after, field),
                explanation=suggestion.explanation,
            )
            PendingSuggestion.objects.filter(pk=suggestion.pk).update(applied_at=now)
            counts["applied"] += 1
    return counts


def _field_state(interests: dict, field: str):
    """What an undo needs to put back: the field, and for a theme change the
    areas too (a theme is a partition of them)."""
    if field == "clusters":
        return {
            "areas": interests.get("areas") or [],
            "clusters": interests.get("clusters") or [],
        }
    if field == "areas":
        return {
            "areas": interests.get("areas") or [],
            "clusters": interests.get("clusters") or [],
        }
    return {field: interests.get(field)}


def revert(change: AppliedChange, *, by) -> None:
    """Put a profile edit back exactly as it was — if nobody changed it since.

    Raises ``ValueError`` when the field no longer holds what the edit wrote:
    the person edited it themselves afterwards, and an undo must not quietly
    throw their later edit away.
    """
    from apps.accounts.interests import validate_interests
    from apps.accounts.models import Profile

    if change.kind == AppliedChange.Kind.STATE_EDIT:
        return _revert_state(change)
    with transaction.atomic():
        profile = Profile.objects.select_for_update().get(user=change.user)
        current = profile.interests or {}
        field = change.field.split(".", 1)[1] if "." in change.field else change.field
        if _field_state(current, field) != change.new_value:
            raise ValueError(
                "This was changed again since — edit your profile directly instead."
            )
        restored = dict(current)
        for key, value in (change.old_value or {}).items():
            if value is None:
                # The field did not exist before this edit (EXP-2026-09-016:
                # restoring ``null`` was refused by the contract).
                restored.pop(key, None)
            else:
                restored[key] = value
        sources = dict(restored.get("sources") or {})
        if sources.get("ambient") and change.suggestion_id:
            sources["ambient"] = [
                row
                for row in sources["ambient"]
                if row.get("suggestion") != change.suggestion_id
            ]
            restored["sources"] = sources
        profile.interests = validate_interests(restored, user=change.user)
        profile.save(update_fields=["interests"])


def _revert_state(change: AppliedChange) -> None:
    from apps.research.models import ProjectState

    state = ProjectState.objects.filter(project=change.project).first()
    if state is None:
        raise ValueError("The project has no state to put back.")
    part, _, name = change.field.partition(".")
    holder = state.slow if part == "slow" else state.fast
    if (holder or {}).get(name) != (change.new_value or {}).get(name):
        raise ValueError("The project's state was changed again since.")
    state.apply({part: {name: (change.old_value or {}).get(name)}})
    state.save()
