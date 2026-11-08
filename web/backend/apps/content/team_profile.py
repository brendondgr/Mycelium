"""Project team-relevance signal — Feature D recompute.

Blends a project's declared focus, its members' interest vectors, and their recent
weighted engagement into one team vector, written to ``research.Project.embedding``
so the recommendation pipeline reads it as the project's query vector. Interest terms
are aggregated onto :class:`~tools.retrieval.models.ProjectProfile`.

Hard principles: **normalize every vector before fusing** (never after), and **never
mutate an individual** :class:`~apps.accounts.models.Profile` — the team signal updates
the project, not the member. All vector math is pure-Python (no numpy dependency); the
only model call is :func:`~tools.retrieval.embeddings.embed_text`, which returns
``None`` when no embedder is installed, so recompute degrades gracefully.
"""

from __future__ import annotations

import math
from collections import Counter

from django.conf import settings
from django.utils import timezone
from tools.retrieval import embeddings
from tools.retrieval.models import ProjectProfile, RelevanceEvent

from apps.accounts.embedding import canonical_text


def _unit(vec) -> list[float] | None:
    """Return ``vec`` scaled to unit length, or ``None`` if empty/zero."""
    if not vec:
        return None
    norm = math.sqrt(sum(float(x) * float(x) for x in vec))
    if norm == 0:
        return None
    return [float(x) / norm for x in vec]


def _scale(vec, k: float) -> list[float]:
    return [float(x) * k for x in vec]


def _add(acc, vec):
    if acc is None:
        return [float(x) for x in vec]
    return [a + float(b) for a, b in zip(acc, vec, strict=False)]


def _member_users(project) -> list:
    """The project's members (+ the personal owner), deduped, as User rows."""
    users = list(project.members.all())
    ids = {u.id for u in users}
    if project.scope_user_id and project.scope_user_id not in ids:
        users.append(project.scope_user)
    return users


def _member_vector(user, *, embed_missing: bool) -> list[float] | None:
    """A member's interest vector: stored ``Profile.embedding`` or embed on demand."""
    profile = getattr(user, "profile", None)
    if profile is None:
        return None
    if profile.embedding is not None:
        return list(profile.embedding)
    if not embed_missing:
        return None
    text = canonical_text(profile)
    if not text.strip():
        return None
    return embeddings.embed_text(text)


def _decay(age_days: float, halflife: float) -> float:
    if halflife <= 0:
        return 1.0
    return 0.5 ** (age_days / halflife)


def _focus_component(project) -> list[float] | None:
    """The declared-focus unit vector, from the project's interest text."""
    from apps.content.targets import target_for_project

    text = target_for_project(project).embedding_text
    if not text.strip():
        return None
    return _unit(embeddings.embed_text(text))


def _members_component(users, *, embed_missing: bool) -> list[float] | None:
    """Mean of members' unit interest vectors, re-normalized."""
    vectors = []
    for user in users:
        unit = _unit(_member_vector(user, embed_missing=embed_missing))
        if unit:
            vectors.append(unit)
    if not vectors:
        return None
    dim = len(vectors[0])
    mean = [sum(v[i] for v in vectors) / len(vectors) for i in range(dim)]
    return _unit(mean)


def _engagement_component(project, *, halflife: float, now) -> list[float] | None:
    """Net direction of members' weighted, time-decayed engagement.

    Each engaged item's unit vector is added scaled by ``event.weight × decay`` —
    positive actions pull toward a topic, ``dismiss`` / ``thumbs_down`` push away —
    then the summed direction is re-normalized.
    """
    agg = None
    events = RelevanceEvent.objects.filter(project=project).select_related("content")
    for event in events.iterator():
        item = event.content
        if item.embedding is None:
            continue
        unit = _unit(list(item.embedding))
        if not unit:
            continue
        age_days = (now - event.created_at).total_seconds() / 86400.0
        weight = float(event.weight) * _decay(age_days, halflife)
        if weight == 0:
            continue
        agg = _add(agg, _scale(unit, weight))
    return _unit(agg) if agg else None


def _aggregate_interests(project, users) -> dict:
    """Union of the focus + members' interest terms, most-common first."""
    from apps.content.targets import target_for_project

    areas: Counter = Counter()
    keywords: Counter = Counter()
    focus = target_for_project(project).interests or {}
    for area in focus.get("areas", []) or []:
        areas[area] += 1
    for keyword in focus.get("keywords", []) or []:
        keywords[keyword] += 1
    for user in users:
        interests = getattr(getattr(user, "profile", None), "interests", None) or {}
        for area in interests.get("areas", []) or []:
            areas[area] += 1
        for keyword in interests.get("keywords", []) or []:
            keywords[keyword] += 1
    return {
        "areas": [a for a, _ in areas.most_common(12)],
        "keywords": [k for k, _ in keywords.most_common(24)],
    }


def recompute_project_profile(
    project,
    *,
    reason: str = ProjectProfile.Reason.MANUAL,
    embed_missing: bool = False,
    now=None,
) -> dict:
    """Recompute a project's team vector + aggregated interests. Returns a summary.

    ``embed_missing`` controls whether members without a stored ``Profile.embedding``
    are embedded on demand — off for the inline (membership-change) path to bound
    request latency, on for the batch task/command.
    """
    now = now or timezone.now()
    users = _member_users(project)

    components: list[tuple[str, float, list[float]]] = []
    focus = _focus_component(project)
    if focus:
        components.append(("focus", settings.PROJECT_PROFILE_FOCUS_WEIGHT, focus))
    members = _members_component(users, embed_missing=embed_missing)
    if members:
        components.append(("members", settings.PROJECT_PROFILE_MEMBER_WEIGHT, members))
    engagement = _engagement_component(
        project, halflife=settings.PROJECT_PROFILE_HALFLIFE_DAYS, now=now
    )
    if engagement:
        components.append(
            ("engagement", settings.PROJECT_PROFILE_ENGAGEMENT_WEIGHT, engagement)
        )

    combined = None
    for _name, weight, unit in components:
        combined = _add(combined, _scale(unit, weight))
    team_vector = _unit(combined) if combined else None

    if team_vector is not None:
        project.embedding = team_vector
        project.save(update_fields=["embedding"])

    ProjectProfile.objects.update_or_create(
        project=project,
        defaults={
            "interests": _aggregate_interests(project, users),
            "last_recomputed": now,
            "recompute_reason": reason,
        },
    )
    return {
        "project_id": str(project.id),
        "components": [name for name, _weight, _unit in components],
        "wrote_vector": team_vector is not None,
        "members": len(users),
    }
