"""What a person confirmed about themselves, as lines for the model's prompts.

Ambient Plan 05, steps 11 and 12. Three optional interests fields hold
**confirmed** understanding only (``accounts/interests.py``): ``preferences``
(how they like to work), ``trajectory`` (where they want to go), and
``learning_goals`` (what they want to learn — explicitly not skills). They reach
the prompts that explain and judge, never the retrieval query or the budget.

Each line is added only when its field has something in it, so a profile
without them produces byte-identical prompts to before. None of these lines is
part of any write-up's reuse key: a preference confirmed today shapes the next
write-up the model is asked for anyway, and never causes one to be re-billed.
"""

from __future__ import annotations


def _clean(value) -> str:
    return " ".join(str(value).split()) if value else ""


def _values(value) -> list[str]:
    if not isinstance(value, list):
        return []
    out, seen = [], set()
    for item in value:
        text = _clean(item)
        if text and text.casefold() not in seen:
            seen.add(text.casefold())
            out.append(text)
    return out


def trajectory_line(interests: dict) -> str:
    trajectory = (interests or {}).get("trajectory")
    if not isinstance(trajectory, dict):
        return ""
    direction = _clean(trajectory.get("direction"))
    if not direction:
        return ""
    extra = " · ".join(
        p
        for p in (
            _clean(trajectory.get("target_stage")),
            _clean(trajectory.get("horizon")),
        )
        if p
    )
    return f"Career direction: {direction}" + (f" ({extra})" if extra else "")


def lines(interests: dict) -> list[str]:
    """Prompt lines for the confirmed-understanding fields that are set."""
    interests = interests or {}
    out: list[str] = []
    preferences = _values(interests.get("preferences"))
    if preferences:
        out.append(
            "Work preferences: "
            + "; ".join(preferences)
            + " (when an item plainly meets one, you may say so)"
        )
    direction = trajectory_line(interests)
    if direction:
        out.append(direction)
    goals = _values(interests.get("learning_goals"))
    if goals:
        out.append("Wants to learn (not yet a skill): " + ", ".join(goals))
    return out


def context_version(user=None, lab=None, projects=()) -> str:
    """A digest of the picture of the reader a report was written against.

    Over the declared interests (without their provenance bookkeeping), the
    person's confirmed conversational understanding, and the project
    developments in effect that this reader may see. Ids and wordings only —
    nothing here is the person's words from conversation.
    """
    import hashlib
    import json

    from apps.ambient.read import developments_in_effect

    parts: dict = {}
    if user is not None:
        from apps.knowledge.read import ranking_edges

        profile = getattr(user, "profile", None)
        interests = dict(getattr(profile, "interests", None) or {})
        interests.pop("sources", None)
        parts["declared"] = interests
        parts["understood"] = sorted(
            (edge.concept_id, edge.relation, edge.qualifier, edge.surface)
            for edge in ranking_edges(user)
            if edge.tier == "conversational"
        )
    elif lab is not None:
        profile = getattr(lab, "profile", None)
        interests = dict(getattr(profile, "interests", None) or {})
        interests.pop("sources", None)
        parts["declared"] = interests
    parts["developments"] = sorted(
        (str(row.project_id), row.pk, row.status)
        for project in projects
        for row in developments_in_effect(project, reader=user)
    )
    blob = json.dumps(parts, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:16]
