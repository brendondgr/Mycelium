"""The resolver behind the ``announcement`` reference kind (``agent.py``).

An announcement is the lab's or department's: it resolves for a member of its
target, or for any caller whose place belongs to it (someone asking in the
target's own Discord server, a guest included). Its card is the opening post
as it was posted, so it says nothing that place has not already read."""

from __future__ import annotations

import uuid

from tools._framework.agentspec import RefInfo


def _place_owns(caller, ann) -> bool:
    """Whether the caller's place (the thread's scope) is the target's own."""
    scope = getattr(caller, "scope", None)
    obj = getattr(scope, "obj", None)
    if obj is None:
        return False
    kind = scope.kind
    if ann.target_lab_id:
        return kind == "lab" and obj.pk == ann.target_lab_id
    if ann.target_department_id:
        if kind == "department":
            return obj.pk == ann.target_department_id
        if kind == "lab":
            return obj.department_id == ann.target_department_id
    return False


def _member(user, ann) -> bool:
    from apps.accounts.models import LabMembership
    from apps.accounts.permissions import user_has_department_access

    if user is None:
        return False
    if ann.target_lab_id:
        return LabMembership.objects.filter(
            user=user, lab_id=ann.target_lab_id
        ).exists()
    if ann.target_department_id:
        return user_has_department_access(user, ann.target_department)
    return False


def card_text(ann) -> str:
    """The opening post in plain text: title, facts, write-up, as posted."""
    from tools.delivery.discord_announcements import build_embed

    embed = build_embed(ann)
    lines = []
    if embed.get("author", {}).get("name"):
        lines.append(embed["author"]["name"])
    if embed.get("description"):
        lines.append(embed["description"])
    for field in embed.get("fields") or []:
        lines.append(f"{field['name']}: {field['value']}")
    facts = ann.facts or {}
    for key in ("deadline", "opens", "award", "eligibility"):
        if facts.get(key) and key not in " ".join(lines).lower():
            lines.append(f"{key.title()}: {facts[key]}")
    if embed.get("url"):
        lines.append(f"Link: {embed['url']}")
    if ann.content_id:
        lines.append(
            f"In the corpus as item:{ann.content_id} (read it with corpus_item)"
        )
    return "\n   ".join(lines)


def resolve_announcement(caller, key):
    from tools.delivery.models import Announcement

    ann = (
        Announcement.objects.select_related(
            "target_lab", "target_department", "content"
        )
        .filter(pk=uuid.UUID(str(key)))
        .first()
    )
    if ann is None:
        return None
    if not (_place_owns(caller, ann) or _member(getattr(caller, "user", None), ann)):
        return None
    title = (ann.snapshot or {}).get("title") or "Opportunity"
    return RefInfo(
        kind="announcement",
        key=str(ann.pk),
        title=f"[{ann.category}] {title}"[:200],
        card=card_text(ann),
        output="lab" if ann.target_lab_id else "department",
        read_with=f"corpus_item(item='item:{ann.content_id}')"
        if ann.content_id
        else "",
        untrusted=True,
    )
