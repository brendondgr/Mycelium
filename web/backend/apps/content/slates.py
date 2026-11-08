"""Per-cluster slates — one ranked shortlist per research theme.

This replaces the single global Top-25 (:mod:`.top_feed`) for any profile that
declares more than one interest cluster. The reasoning, in one paragraph:

Ranking globally takes the **maximum** of a candidate's per-cluster scores, and
those scores are not comparable across clusters — a theme whose vocabulary sits
closer to the corpus wins the whole feed, and a niche theme's genuinely best
paper never registers. Scoring each theme against *itself* is scale-free, so a
theme whose absolute scores run low still gets its own shortlist. After this
module there is **no global ordering anywhere in the deployed path**: each
cluster keeps its own slate, and nothing re-sorts across them.

Three properties this module exists to preserve:

1. **Ranking is deterministic.** Retrieval and fusion decide order; the language
   model only ever annotates (see :mod:`.cluster_fit`).
2. **Nothing is re-sorted after a per-cluster step.** Re-sorting globally is
   exactly what made the older per-cluster rescue provably inert.
3. **A theme with nothing to show produces nothing** — no slate, no heading, no
   placeholder.

Storage
-------

There is one :class:`~tools.retrieval.models.RelevanceScore` per (item, target), so
the per-cluster slate lives inside ``signals``::

    signals["cluster_slates"] = {
        "<cluster_id>": {
            "label": "Medical AI Agents",
            "rank": 3,                     # 1-based, within this theme
            "of": 25,                      # how long this theme's slate ran
            "entered_on": "2026-08-23",    # when it entered *this* theme's slate
            "is_new": True,                # entered on this run
        },
        ...
    }

The legacy flat signals (``top_rank`` / ``top_rank_of`` / ``entered_top_on`` /
``is_new_top``) are still written, derived from the item's *best* position across
its themes — ``top_rank_of`` is that same theme's slate length, so a card can say
"3rd of 25" without a second query — so every
existing feed reader, serializer, and API filter keeps working unchanged. For a
single-cluster (or implicit-cluster) profile the derived values are byte-identical
to what :func:`apps.content.top_feed.compute_top` produced, which is what makes
"a single-cluster profile behaves exactly as before" checkable rather than
asserted.

Slate depth vs render depth
---------------------------

Two different numbers, deliberately decoupled (plan D10): :func:`slate_depth`
decides what counts as *new*, :func:`standing_render_depth` decides how much of
the settled list a document prints. Tuning one must not force the other.

Papers are a **flow** — hundreds arrive daily and the slate is a rolling window
over recent literature, so it is deep (25) and only its head is printed.
Grants, conferences, and fellowships are a **stock** of currently-open calls: a
grant posted three months ago with a deadline in two is exactly as relevant
today as the day it posted. Their slate is a live shortlist that barely moves,
so it is shallow (10) and printed whole.

Pruning
-------

:func:`prune_cluster_slates` clears slate keys for clusters the profile no longer
declares — on **every** run, whether or not that cluster produced candidates.
This is not change detection: the current profile is the only source of truth,
and stored state that does not correspond to it is not state, it is residue. If
pruning were driven by the clusters present in a run's candidate set, a deleted
cluster would never be visited and its rows would carry stale positions forever.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from django.conf import settings
from django.utils import timezone
from tools.retrieval.models import ContentItem, RelevanceScore

#: How deep each category's per-cluster slate runs — the definition of "new".
#: Papers are a flow (rolling window over arrivals); opportunities are a stock of
#: open calls (a live shortlist). See the module docstring.
SLATE_DEPTH: dict[str, int] = {
    ContentItem.Type.PAPER: 25,
    ContentItem.Type.GRANT: 10,
    ContentItem.Type.CONFERENCE: 10,
    ContentItem.Type.FELLOWSHIP: 5,
}

#: How many *standing* (already-seen) rows each category prints in the reference
#: block. Entrants are always printed in full; this caps only the settled tail.
STANDING_RENDER_DEPTH: dict[str, int] = {
    ContentItem.Type.PAPER: 5,
    ContentItem.Type.GRANT: 10,
    ContentItem.Type.CONFERENCE: 10,
    ContentItem.Type.FELLOWSHIP: 5,
}

#: The flat "Open to you" fellowship band — eligibility-qualified but topically
#: flat across every theme, so it is listed once rather than repeated per theme.
OPEN_BAND_DEPTH = 10


def slate_depth(content_type: str) -> int:
    """Per-cluster slate depth for a category, overridable per deployment.

    ``settings.CLUSTER_SLATE_DEPTH`` is a ``{content_type: int}`` override; a
    category it does not name keeps the built-in default.
    """
    override = getattr(settings, "CLUSTER_SLATE_DEPTH", None) or {}
    value = override.get(content_type, SLATE_DEPTH.get(content_type, 10))
    return max(1, int(value))


def standing_render_depth(content_type: str) -> int:
    """How many settled rows a report prints for a category's reference block."""
    override = getattr(settings, "CLUSTER_STANDING_DEPTH", None) or {}
    value = override.get(
        content_type, STANDING_RENDER_DEPTH.get(content_type, 10)
    )
    return max(0, int(value))


# --------------------------------------------------------------------------- #
# Reading the previous run's slates
# --------------------------------------------------------------------------- #


def _rows(persist_kwargs: dict, content_type: str):
    return RelevanceScore.objects.filter(
        **persist_kwargs, content__type=content_type
    ).only("content_id", "signals")


def cluster_entries(signals: Mapping | None) -> dict[str, dict]:
    """The ``{cluster_id: entry}`` slate map on one row (empty when absent)."""
    entries = (signals or {}).get("cluster_slates")
    return entries if isinstance(entries, dict) else {}


def prior_cluster_slates(
    persist_kwargs: dict, content_type: str
) -> dict[str, dict[str, str]]:
    """``{cluster_id: {content_id: entered_on}}`` as of the previous run.

    One read of the target's rows for this category. Membership is the presence
    of an entry under a cluster id; the value is the date that membership
    started, which a staying member carries forward unchanged.

    Must be read *before* the run persists — writing the new rows is what
    replaces the slates this diffs against.
    """
    out: dict[str, dict[str, str]] = {}
    for row in _rows(persist_kwargs, content_type):
        for cluster_id, entry in cluster_entries(row.signals).items():
            if isinstance(entry, dict) and isinstance(entry.get("rank"), int):
                out.setdefault(cluster_id, {})[str(row.content_id)] = str(
                    entry.get("entered_on") or ""
                )
    return out


# --------------------------------------------------------------------------- #
# Computing this run's slates
# --------------------------------------------------------------------------- #


def compute_cluster_slates(
    prior: Mapping[str, Mapping[str, str]],
    groups: Mapping[str, Sequence[str]],
    labels: Mapping[str, str],
    *,
    content_type: str,
    today: str | None = None,
    depth: int | None = None,
) -> dict[str, dict[str, dict]]:
    """Slate entries for a run, keyed ``{content_id: {cluster_id: entry}}``.

    ``groups`` is ``{cluster_id: [content_id, ...]}`` in **that cluster's own**
    ranked order — the fused per-cluster ranking, never a model verdict order.
    Only the first ``depth`` of each group make the slate.

    An item entering a cluster's slate for the first time is an entrant *for that
    cluster*; the same item entering a second cluster's slate later is a separate
    entry event with its own date. That per-pair keying is the whole point: a
    niche theme's third-best paper entering is genuine news, and under a single
    global slate it would never register.

    ``depth`` defaults to :func:`slate_depth` for ``content_type``.
    """
    today = today or timezone.now().date().isoformat()
    limit = slate_depth(content_type) if depth is None else max(1, int(depth))

    out: dict[str, dict[str, dict]] = {}
    for cluster_id, ordered in groups.items():
        was = prior.get(cluster_id) or {}
        for position, content_id in enumerate(ordered[:limit], start=1):
            cid = str(content_id)
            entered = cid not in was
            out.setdefault(cid, {})[cluster_id] = {
                "label": labels.get(cluster_id, ""),
                "rank": position,
                # How long this theme's slate actually is, so a card can say
                # "3rd of 7" rather than implying a depth the theme never
                # reached. It is the realised length, not ``limit``.
                "of": len(ordered[:limit]),
                "entered_on": today if entered else (was[cid] or today),
                "is_new": entered,
            }
    return out


def _set_rank_denominator(signals: dict, best: Mapping) -> None:
    """Write ``top_rank_of`` — the slate length ``top_rank`` is a position in.

    A row written before slates recorded their own length carries no ``of``, so
    the key is removed rather than guessed at. A card renders the bare ordinal in
    that case; inventing a depth the run never reached would make "3rd of 25"
    read as a measurement when the theme only ever produced seven candidates.
    """
    of = best.get("of")
    if isinstance(of, int) and of > 0:
        signals["top_rank_of"] = of
    else:
        signals.pop("top_rank_of", None)


def merge_cluster_signals(
    signals: dict, slates: Mapping[str, Mapping[str, dict]], cid: str
) -> dict:
    """Write one item's per-cluster slate entries onto the signals being persisted.

    Also derives the flat legacy signals every existing reader still uses —
    ``top_rank`` is the item's *best* position across its themes, ``is_new_top``
    is true when it entered any of them on this run, and ``entered_top_on`` is
    the earliest of those dates. An item in no slate at all is cleared out of
    both shapes, which is how a row keeps its stored write-up for reuse while no
    longer counting as something the reader is being shown.
    """
    entries = dict(slates.get(cid) or {})
    if not entries:
        signals.pop("cluster_slates", None)
        signals.pop("top_rank", None)
        signals.pop("top_rank_of", None)
        signals["entered_top_on"] = ""
        signals["is_new_top"] = False
        return signals

    signals["cluster_slates"] = entries
    best = min(entries.values(), key=lambda entry: entry["rank"])
    signals["top_rank"] = best["rank"]
    _set_rank_denominator(signals, best)
    signals["is_new_top"] = any(entry["is_new"] for entry in entries.values())
    dates = [entry["entered_on"] for entry in entries.values() if entry["entered_on"]]
    signals["entered_top_on"] = min(dates) if dates else ""
    return signals


def entrant_pairs(
    slates: Mapping[str, Mapping[str, dict]],
) -> list[tuple[str, str]]:
    """``[(cluster_id, content_id)]`` for everything that entered on this run.

    This is where the model budget goes — a write-up is keyed on the pair, so an
    item entering a second theme earns one new call for that theme only and
    leaves the first theme's stored reasoning untouched.
    """
    return [
        (cluster_id, cid)
        for cid, entries in slates.items()
        for cluster_id, entry in entries.items()
        if entry["is_new"]
    ]


def bridge_cluster_ids(signals: Mapping | None) -> list[str]:
    """Cluster ids whose slate this row is currently in, best position first.

    A bridge is *derived*, never stored and never scored: an item in more than
    one theme's slate simply appears in both, badged. Deriving it at read time
    keeps it symmetric for free — if A is in themes X and Y, both themes see it —
    and means an item that starts bridging tomorrow needs no re-run to say so.
    """
    entries = cluster_entries(signals)
    return [
        cluster_id
        for cluster_id, _entry in sorted(
            entries.items(), key=lambda pair: pair[1].get("rank", 10**6)
        )
    ]


def in_cluster_slate(signals: Mapping | None, cluster_id: str) -> bool:
    """True when this row currently holds a place in ``cluster_id``'s slate."""
    return isinstance(cluster_entries(signals).get(cluster_id, {}).get("rank"), int)


def cluster_rank(signals: Mapping | None, cluster_id: str) -> int:
    """This row's position in one theme's slate; a large sentinel when absent."""
    entry = cluster_entries(signals).get(cluster_id) or {}
    rank = entry.get("rank")
    return rank if isinstance(rank, int) else 10**6


def entered_cluster_on(
    signals: Mapping | None, cluster_id: str, today: str
) -> bool:
    """True when this row entered ``cluster_id``'s slate on ``today``'s run."""
    entry = cluster_entries(signals).get(cluster_id) or {}
    entered = entry.get("entered_on")
    return bool(entered) and str(entered)[:10] == today


# --------------------------------------------------------------------------- #
# Pruning
# --------------------------------------------------------------------------- #


def prune_cluster_slates(
    persist_kwargs: dict,
    content_type: str,
    declared_cluster_ids: Iterable[str],
) -> int:
    """Clear slate keys and write-ups for clusters the profile no longer declares.

    Returns how many rows were changed. Runs on **every** run over **every** row
    of the target's category, not only over clusters that produced candidates —
    a deleted cluster produces nothing by definition, so a candidate-driven prune
    would never reach it.

    Write-ups go too, and unlike a slate key that is a genuine delete: the
    judgement was written about a theme that no longer exists, so there is
    nothing left for it to be an answer to. A write-up for a *surviving* cluster
    is never touched here — an item losing its place in a live theme's slate keeps
    its reasoning, so re-entry costs no model call.
    """
    declared = set(declared_cluster_ids)
    changed: list[RelevanceScore] = []
    for row in _rows(persist_kwargs, content_type):
        signals = row.signals or {}
        entries = cluster_entries(signals)
        writeups = signals.get("writeups")
        writeups = writeups if isinstance(writeups, dict) else {}
        stale_slates = set(entries) - declared
        stale_writeups = set(writeups) - declared
        if not stale_slates and not stale_writeups:
            continue
        for cluster_id in stale_slates:
            entries.pop(cluster_id, None)
        for cluster_id in stale_writeups:
            writeups.pop(cluster_id, None)
        if entries:
            signals["cluster_slates"] = entries
            best = min(entries.values(), key=lambda entry: entry["rank"])
            signals["top_rank"] = best["rank"]
            _set_rank_denominator(signals, best)
        else:
            signals.pop("cluster_slates", None)
            signals.pop("top_rank", None)
            signals.pop("top_rank_of", None)
            signals["entered_top_on"] = ""
            signals["is_new_top"] = False
        if writeups:
            signals["writeups"] = writeups
        else:
            signals.pop("writeups", None)
        row.signals = signals
        changed.append(row)
    if changed:
        RelevanceScore.objects.bulk_update(changed, ["signals"], batch_size=200)
    return len(changed)
