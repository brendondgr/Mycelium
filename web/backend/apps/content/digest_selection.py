"""Shared LLM-slot selection helpers for the paper and opportunity digests.

Both :mod:`.suggest` (papers) and :mod:`.opportunity_llm` (grants / conferences /
fellowships) run the same two-tier shape each night: only the top ``llm_limit`` of
the fused/ranked candidates are sent to the language model, and carry-forward means
an item already scored in a prior run keeps that verdict instead of being re-sent.
These are the small pure pieces both twins share, so the selection rule (and its
tests) live in one place instead of two mirrored copies.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date, timedelta

from .models import ContentItem
from .pinning import DEFAULT_NEW_WINDOW_DAYS, first_seen_date


def new_first[T](
    items: list[T], cid_of: Callable[[T], str], new_ids: set[str]
) -> list[T]:
    """Stable-partition ``items`` so those in ``new_ids`` come first.

    Order within each group is preserved (the caller's existing fused/ranked
    order), so this only reorders across the new/old boundary — the rule that
    freshly-seen items get first crack at this run's LLM slots.
    """
    new = [it for it in items if cid_of(it) in new_ids]
    old = [it for it in items if cid_of(it) not in new_ids]
    return new + old


def new_content_ids(items: Iterable[ContentItem], *, today: str) -> set[str]:
    """Ids of the items among ``items`` first seen within the New window.

    Mirrors :func:`apps.content.pinning.compute_pins`'s own New window, so "new"
    means the same thing for LLM-slot priority as it does for the pinned "New"
    badge.
    """
    window_start = date.fromisoformat(today) - timedelta(days=DEFAULT_NEW_WINDOW_DAYS)
    out: set[str] = set()
    for item in items:
        seen = first_seen_date(item)
        if seen is not None and seen >= window_start:
            out.add(str(item.id))
    return out


def split_by_floor(
    suggestions: list[dict], floor: int
) -> tuple[list[dict], list[dict]]:
    """Partition scored suggestions into ``(visible, hidden)`` by the match floor.

    A suggestion the *language model* scored (``source == "llm"``) below ``floor``
    is hidden — still persisted (so the carry-forward store remembers the verdict
    and never re-sends it to the model) but excluded from what the run surfaces.
    Fallback suggestions (``match_percent is None``) are never hidden — the floor
    only judges verdicts the model actually gave. Rules-sourced suggestions
    (``source == "rules"``, e.g. a fellowship whose ``match_percent`` is an
    embedding-cosine percent rather than a model verdict) are likewise exempt —
    the LLM match-percent floor has no business gating a percent the model never
    produced; that relevance gating is a job for the area's own embedding
    threshold instead.
    """
    visible: list[dict] = []
    hidden: list[dict] = []
    for suggestion in suggestions:
        match_percent = suggestion.get("match_percent")
        is_llm = suggestion.get("source") == "llm"
        if is_llm and match_percent is not None and match_percent < floor:
            hidden.append(suggestion)
        else:
            visible.append(suggestion)
    return visible, hidden
