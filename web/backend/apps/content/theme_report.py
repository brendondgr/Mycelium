"""Organise a target's day by research theme — the gather the report renders from.

The document's organising principle changed. It used to be
**part → category → items**, with the theme buried at the fourth heading level
as a pill and the written briefing sitting apart from the listings it described,
repeating them. It is now **theme → what is new → what is standing**, with prose
adjacent to the items it discusses.

This module is the read half of that. It takes a target's stored rows — the ones
the per-cluster run wrote — and shapes them into :class:`ThemeSection`\\ s. It
decides nothing about relevance: the slates were computed at run time and are
read back verbatim, which is what keeps the report, the PDF, the Discord message,
and the app from ever disagreeing about what a theme currently holds.

Three rules the shape enforces, all of them things the old report got wrong:

* **A theme with no matches produces nothing** — no heading, no row, no
  placeholder. Padding a quiet theme is how a daily report teaches its reader to
  stop opening it.
* **A theme with a slate but no entrants is one line**, in the quiet list at the
  end, naming what it still holds. That is a real answer and it is short.
* **Standing items get no commentary.** The document's job is to report change;
  the reference block exists for the reader who skipped three days, not to let
  settled items dominate.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from .clustering import (
    IMPLICIT_CLUSTER_ID,
    IMPLICIT_CLUSTER_LABEL,
    Cluster,
    cluster_interests,
)
from .models import RelevanceScore
from .slates import (
    cluster_entries,
    cluster_rank,
    entered_cluster_on,
    standing_render_depth,
)
from .top_feed import in_slate, is_entrant, slate_key

#: What the reader's own themes are called when a profile declares none. A single
#: implicit grouping is not a theme, so the section is named for the reader's work
#: as a whole rather than inventing a label they never wrote.
IMPLICIT_SECTION_LABEL = "Your research"


@dataclass
class ThemeSection:
    """One research theme's day: what entered, what is standing, and Mylo's read.

    ``entrants`` and ``standing`` are keyed by category. An entrant is an item
    that entered *this theme's* slate on this run — a separate event per theme, so
    the same paper entering a second theme later is news again, correctly.
    """

    cluster_id: str
    label: str
    entrants: dict[str, list] = field(default_factory=dict)
    standing: dict[str, list] = field(default_factory=dict)
    #: Mylo's two-to-four sentences on what this theme's news amounts to.
    read: str = ""
    read_origin: str = ""

    @property
    def entrant_count(self) -> int:
        return sum(len(items) for items in self.entrants.values())

    @property
    def standing_count(self) -> int:
        return sum(len(items) for items in self.standing.values())

    @property
    def has_news(self) -> bool:
        """Whether this theme earns a section. Everything else is one quiet line."""
        return self.entrant_count > 0

    @property
    def is_alive(self) -> bool:
        """Whether the theme holds anything at all. A dead theme is absent entirely."""
        return self.entrant_count > 0 or self.standing_count > 0

    def counts(self, categories: Sequence[str]) -> dict[str, int]:
        """Entrant counts per category — the cover table's row for this theme."""
        return {c: len(self.entrants.get(c) or []) for c in categories}


def declared_clusters(interests: dict | None) -> list[Cluster]:
    """The target's themes, in declaration order — the report's section order.

    A profile with no declared areas at all still gets one section: the implicit
    grouping. It carries no theme name (see :func:`section_label`) and it is the
    only grouping there is, so the document keeps one shape for every reader
    rather than a second, flat layout for the unclustered.
    """
    return cluster_interests(interests or {}) or [
        Cluster(id=IMPLICIT_CLUSTER_ID, label=IMPLICIT_CLUSTER_LABEL, areas=[])
    ]


def section_label(cluster: Cluster, part_label: str = "") -> str:
    """The heading one theme's section carries.

    A real theme carries its own name. The implicit grouping is not a theme, so it
    borrows the part's name instead — a lab's report says the lab's name, and a
    person's says "Your research" rather than the internal word "Personal".
    """
    if not cluster.is_implicit:
        return cluster.label
    if part_label and part_label != "Personal":
        return part_label
    return IMPLICIT_SECTION_LABEL


def split_by_theme(
    scores: Sequence[RelevanceScore],
    clusters: Sequence[Cluster],
    today: str,
    *,
    content_type: str,
    build,
    standing_limit: int | None = None,
) -> dict[str, tuple[list, list]]:
    """``{cluster_id: (entrants, standing)}`` for one category's stored rows.

    ``build`` turns a :class:`~apps.content.models.RelevanceScore` and a cluster id
    into whatever the caller renders — the PDF's item, the API's dict — so this
    stays about the *arrangement* and knows nothing about presentation.

    Ordering inside a theme is that theme's own slate position, and it is never
    re-sorted afterwards. Re-sorting globally after a per-cluster step is the
    single failure that made the previous rescue mechanism do nothing at all, so
    it is worth being explicit: the order this returns is the order that renders.

    ``standing_limit`` caps only the settled tail (:func:`standing_render_depth`
    by default); entrants are never capped, because the whole document is about
    them.
    """
    limit = (
        standing_render_depth(content_type)
        if standing_limit is None
        else standing_limit
    )
    # A profile with one implicit grouping has no per-theme keys to match on, and
    # neither do rows written before per-cluster slates existed. In both cases the
    # global slate *is* that grouping's slate, so read it as such rather than
    # reporting nothing on a day that had news. Only ever taken when not a single
    # row carries a theme key — a clustered profile is never read this way.
    unkeyed = not any(cluster_entries(score.signals or {}) for score in scores)

    out: dict[str, tuple[list, list]] = {}
    for cluster in clusters:
        flat = unkeyed and cluster.is_implicit
        if flat:
            members = sorted(
                (score for score in scores if in_slate(score.signals or {})),
                key=slate_key,
            )
        else:
            members = sorted(
                (
                    score
                    for score in scores
                    if cluster.id in cluster_entries(score.signals or {})
                ),
                key=lambda score: cluster_rank(score.signals, cluster.id),
            )
        entrants: list = []
        standing: list = []
        for score in members:
            new_here = (
                is_entrant(score.signals or {}, today)
                if flat
                else entered_cluster_on(score.signals, cluster.id, today)
            )
            (entrants if new_here else standing).append(build(score, cluster.id))
        if entrants or standing:
            out[cluster.id] = (entrants, standing[:limit])
    return out


def quiet_lines(sections: Sequence[ThemeSection]) -> list[tuple[str, int]]:
    """``[(label, standing count)]`` for themes holding a slate but no news.

    Not sections — one line at the end of the theme sequence. A theme with no
    matches at all does not appear here either; it is absent from the document
    entirely, which is the honest rendering of "nothing was found for this".
    """
    return [
        (section.label, section.standing_count)
        for section in sections
        if not section.has_news and section.standing_count
    ]


def is_implicit(cluster_id: str) -> bool:
    return cluster_id == IMPLICIT_CLUSTER_ID
