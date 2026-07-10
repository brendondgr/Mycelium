"""Generalize the matcher's scoring target from the user to any interest surface.

The daily pipelines were written for one target — the signed-in user. But the
schema (:class:`apps.content.models.RelevanceScore`) already scores against a
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

    kind: str  # "user" | "lab" | "project"
    key: str  # username / slug / project id — for logs, signals, result labels
    interests: dict
    watch_topics: list[str]
    profile_meta: dict
    persist_kwargs: dict
    embedding_text: str


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


def target_for_project(project) -> MatchTarget:
    """A project: the focus in its ``goals``, scored under ``target_project``."""
    interests = project_interests(project)
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
    areas = _clean(getattr(profile, "areas", None)) or _clean(contract.get("areas"))
    statement = (
        getattr(profile, "statement", "") or contract.get("statement", "") or ""
    ).strip()
    return {
        "areas": areas,
        "keywords": _clean(contract.get("keywords")),
        "statement": statement,
    }


def project_interests(project) -> dict:
    """The project's interests contract, read from its free-form ``goals`` JSON.

    A project author sets ``goals.interests`` = ``{areas, keywords, statement}``
    explicitly (the focus surface); failing that we derive a contract from the
    legacy goals fields so an older project still matches — ``topics`` / ``areas``
    become the areas and ``description`` / ``goal`` becomes the statement.
    """
    goals = project.goals if isinstance(project.goals, dict) else {}
    explicit = goals.get("interests")
    if isinstance(explicit, dict):
        return {
            "areas": _clean(explicit.get("areas")),
            "keywords": _clean(explicit.get("keywords")),
            "statement": str(explicit.get("statement") or "").strip(),
        }
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
