"""Shared LLM-slot selection helpers for the paper and opportunity digests.

Both :mod:`.suggest` (papers) and :mod:`.opportunity_llm` (grants / conferences /
fellowships) run the same two-tier shape each night: of the slate — the top
:func:`~tools.recommendation.top_feed.top_n` fused/ranked candidates, which is what the
daily report shows — only ``llm_limit`` items go to the language model per run, and
carry-forward means an item already written up in a prior run keeps that verdict
instead of being re-sent. These are the small pure pieces both twins share, so the
selection rule (and its tests) live in one place instead of two mirrored copies.

The scarce resource here is model attention, so *which* unwritten item gets it is a
real decision. It goes to items that just entered the slate — the ones the reader is
about to be shown for the first time — never to items that merely arrived recently.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date, timedelta

from tools.recommendation.pinning import DEFAULT_NEW_WINDOW_DAYS, first_seen_date
from tools.retrieval.models import ContentItem


def priority_first[T](
    items: list[T], cid_of: Callable[[T], str], priority_ids: set[str]
) -> list[T]:
    """Stable-partition ``items`` so those in ``priority_ids`` come first.

    Order within each group is preserved (the caller's existing fused/ranked
    order), so this only reorders across the boundary — the rule that this run's
    slate entrants get first crack at its LLM slots, ahead of slate members that
    are still waiting for a write-up.

    This only chooses who is *explained* first. It has no bearing on the feed's
    order, which is the fused ranking and stays that way whether or not the model
    ever reaches an item.
    """
    priority = [it for it in items if cid_of(it) in priority_ids]
    rest = [it for it in items if cid_of(it) not in priority_ids]
    return priority + rest


def new_content_ids(items: Iterable[ContentItem], *, today: str) -> set[str]:
    """Ids of the items among ``items`` first seen within the New window.

    Mirrors :func:`tools.recommendation.pinning.compute_pins`'s own New window, so "new"
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


def renumber(suggestions: list[dict]) -> list[dict]:
    """Re-assign ``rank`` 1..N in list order, returning the same list.

    Ranks are first handed out over the *whole* surfaced set, before
    :func:`split_by_floor` removes the papers the model judged poorly. Left at
    that, the rows that survive carry the numbering of a list they are no longer
    a member of: a feed whose model rejected papers 3-10 renders "1, 2, 11, 12,
    13" and reads as though eight items went missing. Renumbering the visible
    list closes the gaps without reordering anything — position is the only thing
    that changes, and it changes to match what is actually on screen.
    """
    for position, suggestion in enumerate(suggestions, start=1):
        suggestion["rank"] = position
    return suggestions
