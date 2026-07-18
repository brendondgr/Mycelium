"""Read a profile's interest **clusters** out of the interests contract.

Interests are organised into named clusters (e.g. *Medical AI Agents*,
*Oceanography & Data Assimilation*). A cluster is a label over a subset of the
profile's ``areas``; every area belongs to exactly one cluster (the contract
validates the partition — see :mod:`apps.accounts.interests`). The cluster layer
*wraps* the existing fusion math (``fuse_interest`` / ``combine_interests``); it
does not rewrite it.

This module is the single place that turns the raw contract blob into
:class:`Cluster` objects, with the one fallback the whole feature hangs on:

    **A profile with no ``clusters`` behaves as one implicit cluster containing
    all its areas** — so a v1 (pre-clusters) profile scores byte-identically to
    today's pipeline, and a single-cluster user is indistinguishable from an
    unclustered one.

Pure and DB-free (like :mod:`apps.content.interests_query`) so it is trivially
unit-testable. ``cluster_id`` slugs are **stable**: generated once at creation
and never regenerated on relabel/edit, which is what lets badges, filters, and
attribution survive profile edits (:func:`make_cluster_id` is only for *new*
clusters — the organiser UI and the LLM proposer keep prior ids).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

#: The reserved id/label for the single implicit cluster a profile falls back to
#: when it declares no ``clusters``. Callers that render attribution should treat
#: this id as "no meaningful cluster" (a lone, unnamed grouping) and omit the
#: badge — a single-cluster user gets no cluster attribution, exactly as today.
IMPLICIT_CLUSTER_ID = "c-all"
IMPLICIT_CLUSTER_LABEL = "All interests"

#: UI/validation sanity cap on clusters per profile (Open Decision D-C3).
MAX_CLUSTERS = 6


@dataclass(frozen=True)
class Cluster:
    """One named grouping of a profile's research areas.

    ``id`` is the stable slug (never regenerated on edit); ``label`` is the
    human name shown on badges; ``areas`` are this cluster's subset of the
    profile's declared areas (the per-interest scoring vocabulary).
    """

    id: str
    label: str
    areas: list[str]

    @property
    def is_implicit(self) -> bool:
        """Whether this is the fallback single cluster (no real attribution)."""
        return self.id == IMPLICIT_CLUSTER_ID


def _implicit(areas: list[str]) -> Cluster:
    """The single fallback cluster over ``areas`` (no real attribution)."""
    return Cluster(id=IMPLICIT_CLUSTER_ID, label=IMPLICIT_CLUSTER_LABEL, areas=areas)


def cluster_interests(interests: dict | None) -> list[Cluster]:
    """Return the profile's clusters, with the single-implicit-cluster fallback.

    ``interests`` is a ``Profile.interests`` / ``LabProfile.interests`` blob.
    When it carries a non-empty ``clusters`` list, each entry becomes a
    :class:`Cluster` (its ``areas`` intersected with — and ordered by — the
    profile's declared ``areas``, so a stale cluster referencing a removed area
    is self-healing). When it declares no clusters, all areas collapse into one
    implicit cluster; with no areas at all, returns ``[]`` (the caller's signal
    to fall back to the single-vector path, same as today).
    """
    interests = interests or {}
    areas = _clean_list(interests.get("areas"))
    if not areas:
        return []

    raw = interests.get("clusters")
    if not raw:
        return [_implicit(areas)]

    # Index the canonical area strings by their casefold so cluster entries map
    # back to the exact declared spelling regardless of minor case/space drift.
    canonical = {area.casefold(): area for area in areas}
    assigned: set[str] = set()
    clusters: list[Cluster] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        cid = str(entry.get("id") or "").strip()
        label = " ".join(str(entry.get("label") or "").split())
        members: list[str] = []
        for candidate in _clean_list(entry.get("areas")):
            area = canonical.get(candidate.casefold())
            if area is not None and area not in assigned:
                assigned.add(area)
                members.append(area)
        if cid and label and members:
            clusters.append(Cluster(id=cid, label=label, areas=members))

    # Defensive: any area not claimed by a (valid) cluster lands in the implicit
    # cluster so no area is silently dropped from scoring. Validated payloads
    # never hit this, but a hand-edited/legacy blob might.
    orphans = [area for area in areas if area not in assigned]
    if orphans:
        clusters.append(_implicit(orphans))
    if not clusters:
        return [_implicit(areas)]
    return clusters


def cluster_labels(interests: dict | None) -> dict[str, str]:
    """Map ``cluster_id -> label`` for every cluster the profile declares.

    Used to resolve a persisted ``cluster_id`` (in a ``RelevanceScore``) back to
    a display label at read time, so a renamed cluster shows its new name without
    a re-score. The implicit cluster is included but callers usually skip it.
    """
    return {c.id: c.label for c in cluster_interests(interests)}


#: Cap on seeded watch topics — matches the historical seeding migration.
DEFAULT_TOPIC_CAP = 12


def seed_watch_topics(
    interests: dict | None, *, cap: int = DEFAULT_TOPIC_CAP
) -> list[str]:
    """Derive watch topics **per cluster** — the grouped scan-term seed.

    Each real cluster contributes its label followed by its areas ("Medical AI
    Agents", "agentic AI in healthcare", …); shared keywords come last. Deduped
    case-insensitively, order-preserving, capped at ``cap``. For a v1 / single
    implicit cluster the label is skipped, so the seed is areas + keywords —
    byte-identical to the historical `areas + keywords` seeding. This is what lets
    "what Mylo watches" render grouped by cluster, and it keeps a Medical+Ocean
    user's ingestion issuing per-cluster queries, never one blended across clusters.
    """
    clusters = cluster_interests(interests)
    keywords = _clean_list((interests or {}).get("keywords"))
    out: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        text = " ".join(str(value).split())
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            out.append(text)

    for cluster in clusters:
        if not cluster.is_implicit:
            add(cluster.label)
        for area in cluster.areas:
            add(area)
    for keyword in keywords:
        add(keyword)
    return out[:cap]


def make_cluster_id(label: str, existing: Sequence[str] = ()) -> str:
    """Generate a stable, collision-free slug for a **new** cluster.

    Only for clusters the user/LLM is creating for the first time — an existing
    cluster keeps its id forever. Produces ``c-<slug-of-label>`` (ASCII, kebab),
    disambiguated with a numeric suffix against ``existing`` ids.
    """
    base = _slugify(label) or "cluster"
    candidate = f"c-{base}"
    if candidate not in existing:
        return candidate
    n = 2
    while f"{candidate}-{n}" in existing:
        n += 1
    return f"{candidate}-{n}"


def _slugify(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9]+", "-", text.casefold()).strip("-")
    return text[:48]


def _clean_list(value: Sequence[str] | None) -> list[str]:
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
