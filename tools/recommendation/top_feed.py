"""The Top-25 slate: what a target's report is about, and what is new in it.

Every category a target is scored for keeps a **slate** — the top
:data:`TOP_N` items of that category's feed, in the feed's own ranked order
(BM25 + embedding fusion; see :mod:`.fusion`). The slate is the unit of the daily
report: the report shows it, and "new" means *entered the slate since the last
run* — not "was ingested recently".

That distinction is the whole point of this module. Anchoring newness to the
ingest calendar meant a bulk import of grants that had nothing to do with anyone's
research was announced to everyone as "a new opportunity you haven't seen yet",
purely because it had arrived. Anchoring it to the slate inverts the test: an item
is worth announcing when it is good enough to displace something the reader was
already being shown. It also makes the report react to the *reader* — change a
research focus, a cluster, or a watch term and the slate re-ranks, so whatever
that change promotes is correctly reported as new, with no separate machinery.

Three signals carry the slate on each
:class:`~tools.recommendation.models.RelevanceScore`:

``top_rank``
    1-based position in the slate, or absent when the item is outside it. Presence
    of an integer here *is* slate membership; there is no separate table.
``entered_top_on``
    The run date the item most recently entered the slate. Cleared when it drops
    out, so a re-entry later is reported as new again — it is news to a reader who
    stopped seeing it.
``is_new_top``
    True only on the run the item entered. This is what the report flags and what
    the LLM write-up budget is spent on.

The mapping is computed by :func:`compute_top` *before* a run's rows are written
(it needs the previous run's slate, which the write is about to overwrite) and
merged into the signals each pipeline's ``_persist`` stores.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from django.conf import settings
from django.utils import timezone

from tools.recommendation.models import RelevanceScore

#: How many items make up a category's slate. The daily report's "Top 25".
TOP_N = 25


def top_n() -> int:
    """The slate size, overridable by ``settings.REPORT_TOP_N``."""
    return int(getattr(settings, "REPORT_TOP_N", TOP_N) or TOP_N)


def _slate_rows(persist_kwargs: dict, content_type: str):
    return RelevanceScore.objects.filter(
        **persist_kwargs, content__type=content_type
    ).only("content_id", "signals")


def _prior_slate(persist_kwargs: dict, content_type: str) -> dict[str, str]:
    """``{content_id: entered_top_on}`` for the slate as of the last run.

    One read of the target's rows for this category. Membership is the presence of
    an integer ``top_rank``; the value is the date that membership started, which a
    staying member carries forward unchanged.
    """
    out: dict[str, str] = {}
    for row in _slate_rows(persist_kwargs, content_type):
        signals = row.signals or {}
        if isinstance(signals.get("top_rank"), int):
            out[str(row.content_id)] = str(signals.get("entered_top_on") or "")
    return out


def prior_top_ids(persist_kwargs: dict, content_type: str) -> set[str]:
    """Content ids that were in this target's slate as of the last run.

    Read before a run persists, so the caller can tell an entrant from an item that
    was already being shown. An empty set (a target's first run) makes the whole
    slate new, which is correct: none of it has been reported yet.
    """
    return set(_prior_slate(persist_kwargs, content_type))


def compute_top(
    persist_kwargs: dict,
    content_type: str,
    ordered_ids: Sequence[str],
    *,
    today: str | None = None,
) -> dict[str, dict]:
    """Slate signals for every id this run is about to write, in ranked order.

    ``ordered_ids`` is the run's surfaced list, best first — the fused ranking, not
    a model verdict order. The first :func:`top_n` of them form the new slate.

    Must be called *before* the run's rows are written: writing them is what replaces
    the previous slate this diffs against.

    Returns ``{content_id: {"top_rank", "entered_top_on", "is_new_top"}}`` covering
    *all* of ``ordered_ids``: those outside the slate get ``top_rank=None`` and a
    cleared ``entered_top_on``, so dropping out and coming back later counts as
    entering again. A member that stays keeps the date it originally entered, so the
    signal answers "when did this first appear in your report" rather than being
    reset by every run that re-confirms it. Callers merge this into the signals they
    persist with :func:`merge_top_signals`.
    """
    today = today or timezone.now().date().isoformat()
    was = _prior_slate(persist_kwargs, content_type)
    limit = top_n()

    out: dict[str, dict] = {}
    for position, cid in enumerate(ordered_ids, start=1):
        cid = str(cid)
        if position > limit:
            out[cid] = {"top_rank": None, "entered_top_on": "", "is_new_top": False}
            continue
        entered = cid not in was
        out[cid] = {
            "top_rank": position,
            "entered_top_on": today if entered else (was[cid] or today),
            "is_new_top": entered,
        }
    return out


def merge_top_signals(signals: dict, slate: dict, cid: str) -> dict:
    """Apply one item's slate entry to the signals about to be persisted.

    An id the run did not surface at all (``slate`` has no entry) is cleared out of
    the slate — that is how a row keeps its verdict for carry-forward while no longer
    counting as something the reader is being shown.
    """
    entry = slate.get(cid)
    if entry is None or entry["top_rank"] is None:
        signals.pop("top_rank", None)
        signals["entered_top_on"] = ""
        signals["is_new_top"] = False
        return signals

    signals["top_rank"] = entry["top_rank"]
    signals["entered_top_on"] = entry["entered_top_on"]
    signals["is_new_top"] = entry["is_new_top"]
    return signals


def entrant_ids(slate: dict) -> set[str]:
    """The ids that entered the slate this run — where the LLM budget goes."""
    return {cid for cid, entry in slate.items() if entry["is_new_top"]}


def is_entrant(signals: dict, today: str) -> bool:
    """True when this row entered its slate on ``today``'s run.

    The report's definition of new. ``entered_top_on`` is a bare ISO date, but
    compare the first ten characters anyway so a datetime written by an older
    build still reads correctly.
    """
    entered = (signals or {}).get("entered_top_on")
    return bool(entered) and str(entered)[:10] == today


def in_slate(signals: dict) -> bool:
    """True when the row is currently in its category's slate."""
    return isinstance((signals or {}).get("top_rank"), int)


def slate_key(score: RelevanceScore) -> int:
    """Sort key for slate order — ranked position, unranked rows last."""
    rank = (score.signals or {}).get("top_rank")
    return rank if isinstance(rank, int) else 10**6


def order_by_slate(scores: Iterable[RelevanceScore]) -> list[RelevanceScore]:
    """The slate, in rank order, for rows already read from the database."""
    return sorted(
        (s for s in scores if in_slate(s.signals or {})), key=slate_key
    )
