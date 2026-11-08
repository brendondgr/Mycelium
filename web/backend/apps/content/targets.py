"""Generalize the matcher's scoring target from the user to any interest surface.

The daily pipelines were written for one target — the signed-in user. But the
schema (:class:`tools.retrieval.models.RelevanceScore`) already scores against a
user, a project, a lab, or a department. A :class:`MatchTarget` captures
everything the retrieve → fuse → score → persist core needs about *whatever* it is
scoring for, so the same engine personalizes a lab or a lab project without being
duplicated:

- ``interests`` — the areas/keywords/statement contract that becomes the search
  interests (:func:`apps.content.interests_query.search_interests`) and feeds the
  language model.
- ``watch_topics`` — the monitored terms that broaden opportunity matching.
- ``profile_meta`` — career stage / institution; only meaningful for a person.
- ``persist_kwargs`` — the single ``target_*`` FK the score row is written under.
- ``embedding_text`` — canonical text for the single-vector fallback (surfaces
  with no declared ``areas``).

Builders resolve a ``User`` / ``Lab`` / ``Project`` into a target. Fellowships stay
user-only (they gate on individual eligibility), so no fellowship target is built
here. Pure apart from reading already-loaded relations, so it is unit-testable
without a scan or an embedder.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from apps.accounts.embedding import build_canonical_text


@dataclass(frozen=True)
class MatchTarget:
    """Everything the matcher needs about the thing it is scoring for."""

    kind: str  # "user" | "lab" | "project" | "department"
    key: str  # username / slug / project id — for logs, signals, result labels
    interests: dict
    watch_topics: list[str]
    profile_meta: dict
    persist_kwargs: dict
    embedding_text: str
    # A precomputed query vector to use instead of embedding ``embedding_text``.
    # Set for projects with a recomputed team profile (Feature D) — the blend of
    # declared focus + members + engagement stored on ``Project.embedding``.
    stored_vector: list[float] | None = None


def _clean(value: Sequence | None) -> list[str]:
    """Normalize whitespace, drop blanks, dedupe case-insensitively (order-kept)."""
    if not value:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = " ".join(str(item).split())
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            out.append(text)
    return out


def _watch_topics(watch) -> list[str]:
    topics = getattr(watch, "topics", None) or []
    return [str(topic) for topic in topics]


def target_for_user(user) -> MatchTarget:
    """A person: interests + watch from their profile, scored under ``target_user``."""
    profile = getattr(user, "profile", None)
    interests = (getattr(profile, "interests", None) or {}) if profile else {}
    return MatchTarget(
        kind="user",
        key=user.get_username(),
        interests=interests,
        watch_topics=_watch_topics(getattr(user, "watch", None)),
        profile_meta={
            "academic_title": getattr(profile, "academic_title", "") if profile else "",
            "institution": getattr(profile, "institution", "") if profile else "",
        },
        persist_kwargs={"target_user": user},
        # A user Profile embeds only statement + keywords (its research focus /
        # areas drive the weighted re-rank, not the vector) — mirror that here so
        # the single-vector fallback matches the daily pipeline exactly.
        embedding_text=build_canonical_text(
            statement=interests.get("statement", ""),
            keywords=interests.get("keywords", []),
        ),
    )


def target_for_lab(lab) -> MatchTarget:
    """A lab: its curated interest surface, scored under ``target_lab``."""
    interests = _lab_interests(getattr(lab, "profile", None))
    return MatchTarget(
        kind="lab",
        key=lab.slug,
        interests=interests,
        watch_topics=_watch_topics(getattr(lab, "watch", None)),
        profile_meta={},
        persist_kwargs={"target_lab": lab},
        # Institutional surfaces keep ``areas`` in the vector so the lab stays broad.
        embedding_text=build_canonical_text(
            statement=interests.get("statement", ""),
            areas=interests.get("areas", []),
            keywords=interests.get("keywords", []),
        ),
    )


def target_for_department(department) -> MatchTarget:
    """A department: its own interest profile, scored under ``target_department``.

    Opportunities only: a department's slates feed its announcement channel, which
    carries calls only a department can take on (``apps.content.dept_level``).
    """
    interests = _lab_interests(getattr(department, "profile", None))
    return MatchTarget(
        kind="department",
        key=str(department.pk),
        interests=interests,
        watch_topics=[],
        profile_meta={},
        persist_kwargs={"target_department": department},
        embedding_text=build_canonical_text(
            statement=interests.get("statement", ""),
            areas=interests.get("areas", []),
            keywords=interests.get("keywords", []),
        ),
    )


def _merge_team_interests(project, interests: dict) -> dict:
    """Broaden a project's interests with its recomputed team profile (Feature D).

    A project's declared focus leads; its members' aggregated areas/keywords (from
    :class:`~tools.retrieval.models.ProjectProfile`) are appended and deduped, so the
    fusion retrieval reflects the whole team, not just the declared focus. A no-op
    until the team profile has been recomputed.
    """
    from tools.retrieval.models import ProjectProfile

    # An unsaved project can't have a team profile yet — skip the query so building
    # a target stays pure for callers that never touch the DB.
    if getattr(project, "_state", None) is not None and project._state.adding:
        return interests
    team = (
        ProjectProfile.objects.filter(project=project)
        .values_list("interests", flat=True)
        .first()
    )
    if not team:
        return interests
    merged = dict(interests)
    # When the project has organized its areas into clusters, the areas list is a
    # partition — appending team areas outside it would orphan them from every
    # cluster and silently drop them from cluster-scoped scoring. So keep the
    # declared area partition authoritative and only broaden keywords; a flat
    # (clusterless) project still broadens both as before.
    if not interests.get("clusters"):
        merged["areas"] = _clean(
            [*(interests.get("areas") or []), *(team.get("areas") or [])]
        )[:12]
    merged["keywords"] = _clean(
        [*(interests.get("keywords") or []), *(team.get("keywords") or [])]
    )[:32]
    return merged


def target_for_project(project) -> MatchTarget:
    """A project: focus in ``goals`` + its team signal, under ``target_project``."""
    interests = _merge_team_interests(project, project_interests(project))
    return MatchTarget(
        kind="project",
        key=str(project.id),
        interests=interests,
        watch_topics=project_watch_topics(project),
        profile_meta={},
        persist_kwargs={"target_project": project},
        embedding_text=build_canonical_text(
            statement=interests.get("statement", ""),
            areas=interests.get("areas", []),
            keywords=interests.get("keywords", []),
        ),
        # If the project's team profile has been recomputed (Feature D), its blended
        # vector lives on Project.embedding — prefer it over embedding the focus text.
        stored_vector=(
            list(project.embedding) if project.embedding is not None else None
        ),
    )


def _lab_interests(profile) -> dict:
    """A lab's interests contract from its curated columns, falling back to the JSON.

    ``LabProfile`` carries curated ``statement`` / ``areas`` columns alongside a
    free-form ``interests`` contract; prefer the curated columns and fall back to
    the contract so a lab that filled *either* surface still matches.
    """
    if profile is None:
        return {"areas": [], "keywords": [], "statement": ""}
    contract = dict(getattr(profile, "interests", None) or {})
    clusters = contract.get("clusters") or []
    # When the lab organised its focus into clusters, the partition is defined over
    # the contract's ``areas`` — use those so cluster scoping lines up; otherwise
    # prefer the curated ``areas`` column as before.
    if clusters:
        areas = _clean(contract.get("areas")) or _clean(getattr(profile, "areas", None))
    else:
        areas = _clean(getattr(profile, "areas", None)) or _clean(contract.get("areas"))
    statement = (
        getattr(profile, "statement", "") or contract.get("statement", "") or ""
    ).strip()
    interests = {
        "areas": areas,
        "keywords": _clean(contract.get("keywords")),
        "statement": statement,
    }
    if clusters:
        interests["clusters"] = clusters
    return interests


def project_interests(project) -> dict:
    """The project's interests contract, read from its free-form ``goals`` JSON.

    A project author sets ``goals.interests`` = ``{areas, keywords, statement,
    clusters?}`` explicitly (the focus surface); failing that we derive a contract
    from the legacy goals fields so an older project still matches — ``topics`` /
    ``areas`` become the areas and ``description`` / ``goal`` becomes the
    statement. When the project has organized its areas into v2 ``clusters`` the
    partition is carried through so cluster-scoped scoring lights up exactly as it
    does for a user or lab profile (:mod:`apps.content.clustering`).
    """
    goals = project.goals if isinstance(project.goals, dict) else {}
    explicit = goals.get("interests")
    if isinstance(explicit, dict):
        interests = {
            "areas": _clean(explicit.get("areas")),
            "keywords": _clean(explicit.get("keywords")),
            "statement": str(explicit.get("statement") or "").strip(),
        }
        clusters = explicit.get("clusters")
        if clusters:
            interests["clusters"] = clusters
        return interests
    statement = (
        goals.get("description") or goals.get("goal") or goals.get("statement") or ""
    )
    return {
        "areas": _clean(goals.get("areas") or goals.get("topics")),
        "keywords": _clean(goals.get("keywords")),
        "statement": str(statement).strip(),
    }


def project_watch_topics(project) -> list[str]:
    """The project's monitored terms: explicit ``goals.watch_topics`` else its areas."""
    goals = project.goals if isinstance(project.goals, dict) else {}
    explicit = _clean(goals.get("watch_topics"))
    return explicit or project_interests(project)["areas"]


#: Every recommendation area a project can run, in report order.
PROJECT_CATEGORIES: tuple[str, ...] = ("papers", "grants", "fellowships", "conferences")


def project_watch_categories(project) -> list[str]:
    """Which recommendation areas a project runs (``goals.watch_categories``).

    Defaults to all four when unset, so an existing project keeps its full feed.
    An author narrows the feed (e.g. papers + grants only) and every scoring path
    — daily fan-out, seeding, refit — reads through here to skip the rest.
    """
    goals = project.goals if isinstance(project.goals, dict) else {}
    stored = goals.get("watch_categories")
    if not isinstance(stored, list):
        return list(PROJECT_CATEGORIES)
    chosen = {str(c).strip().lower() for c in stored}
    picked = [c for c in PROJECT_CATEGORIES if c in chosen]
    return picked or list(PROJECT_CATEGORIES)
