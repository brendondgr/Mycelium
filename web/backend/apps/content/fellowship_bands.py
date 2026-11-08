"""Split eligible fellowships into the two bands a reader actually needs.

A fellowship list that is not topically relevant is not a recommendation, it is
a directory. But cluster-scoping the whole list naively produces six copies of
the same award: a university-wide dissertation completion grant matches every
theme about equally and would appear under all of them.

So there are two layers, not one list (plan §12):

**Eligibility is a hard gate.** Career stage, citizenship, institution type,
degree timing. An award the reader cannot apply for is noise no matter how well
it matches their topic, and no amount of research fit promotes it. That gate is
the existing rule engine (:mod:`.fellowships`) and this module never touches it —
everything here happens *inside* what the gate already admitted.

**Research fit ranks within the gate**, and its *shape* decides the band:

* **Matched to your themes** — the award's fit **spikes** on one or two themes.
  Filed under those themes, attributed, ranked among that theme's other awards.
  This is the band the reader came for, so it leads.
* **Open to you** — the award's fit is **flat** across every theme, which is what
  topic-agnostic looks like in the data. Listed once, in its own band, honest
  about what it is.

The discriminator is computable from signal the pipeline already has, and it is
deliberately a **tuning parameter, not a curated tag**. Building a taxonomy of
"topical" versus "general" fellowships would mean a label whose meaning differs
by source and rots as sources change; the variance of an award's own fit scores
across the reader's own themes does not.

Depth is five per theme rather than ten: the eligible pool is small, and a
topic-matched fellowship list padded to depth is exactly the directory problem
again.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from django.conf import settings

from apps.content.slates import OPEN_BAND_DEPTH

#: How much an award's fit must vary across the reader's themes before it counts
#: as topic-matched. Expressed as a fraction of its own best theme score, so it
#: is scale-free: an award scoring 0.8/0.2 spikes, one scoring 0.5/0.48 does not,
#: and neither judgement depends on where the corpus happens to sit.
DEFAULT_SPIKE_FRAC = 0.25

#: Themes an award may be filed under before it stops being "matched to a theme"
#: and starts being a list of everything. Two, per the plan.
MAX_MATCHED_THEMES = 2

#: Matched-band depth per theme. Deliberately shallower than grants (10): the
#: eligible pool is small and padding it to depth reinstates the directory.
DEFAULT_MATCHED_DEPTH = 5

MATCHED = "matched"
OPEN = "open"


def spike_frac() -> float:
    return float(getattr(settings, "FELLOWSHIP_SPIKE_FRAC", DEFAULT_SPIKE_FRAC))


def matched_depth() -> int:
    return int(getattr(settings, "FELLOWSHIP_MATCHED_DEPTH", DEFAULT_MATCHED_DEPTH))


def open_depth() -> int:
    return int(getattr(settings, "FELLOWSHIP_OPEN_DEPTH", OPEN_BAND_DEPTH))


@dataclass
class Banded:
    """One award's band and, when it is matched, the themes it is matched to."""

    content_id: str
    band: str  # MATCHED | OPEN
    #: Cluster ids the award spikes on, strongest first. Empty in the open band.
    cluster_ids: list[str] = field(default_factory=list)
    #: The spread that decided it, as a fraction of the award's best theme score.
    spread: float = 0.0


def classify(
    content_id: str,
    per_cluster: Mapping[str, float],
    *,
    frac: float | None = None,
    max_themes: int = MAX_MATCHED_THEMES,
) -> Banded:
    """Decide one award's band from its per-theme fit scores.

    With fewer than two themes there is nothing to vary across, so the award
    lands in the open band: calling it "matched to your themes" when the reader
    has one theme says nothing they did not already know.

    An award with no fit scores at all cleared eligibility without being
    retrieved for any theme. That is genuinely topic-agnostic as far as this
    reader is concerned, and the open band is where it belongs.
    """
    frac = spike_frac() if frac is None else frac
    scores = {cid: float(v) for cid, v in (per_cluster or {}).items()}
    if len(scores) < 2:
        return Banded(content_id=content_id, band=OPEN)

    best = max(scores.values())
    worst = min(scores.values())
    if best <= 0:
        return Banded(content_id=content_id, band=OPEN)
    spread = (best - worst) / best
    if spread < frac:
        # Flat across every theme — a topic-agnostic award, listed once.
        return Banded(content_id=content_id, band=OPEN, spread=spread)

    # Spiking: file it under the themes it actually reaches, not every theme it
    # scored on. The cut is relative to its own best, so a two-theme award keeps
    # both and a one-theme award keeps one.
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    keep = [cid for cid, score in ranked if score >= (1.0 - frac) * best]
    return Banded(
        content_id=content_id,
        band=MATCHED,
        cluster_ids=keep[:max_themes] or [ranked[0][0]],
        spread=spread,
    )


def split(
    ordered_ids: Sequence[str],
    per_cluster_by_id: Mapping[str, Mapping[str, float]],
    *,
    frac: float | None = None,
    depth: int | None = None,
    flat_depth: int | None = None,
) -> tuple[dict[str, list[str]], list[str], dict[str, Banded]]:
    """Split an eligibility-ordered list into ``(matched slates, open band, bands)``.

    ``ordered_ids`` is the rule engine's order — eligibility first, always. The
    matched slates preserve **each theme's own** fit order within that gate, and
    the open band preserves the incoming order, because a topic-agnostic award
    has no research-fit ordering worth imposing.

    Nothing here re-sorts across bands and nothing crosses the gate: an award
    absent from ``ordered_ids`` is ineligible and simply never appears.
    """
    depth = matched_depth() if depth is None else depth
    flat_depth = open_depth() if flat_depth is None else flat_depth

    bands = {
        cid: classify(cid, per_cluster_by_id.get(cid) or {}, frac=frac)
        for cid in ordered_ids
    }
    matched: dict[str, list[str]] = {}
    for cid in ordered_ids:
        entry = bands[cid]
        if entry.band != MATCHED:
            continue
        for cluster_id in entry.cluster_ids:
            matched.setdefault(cluster_id, []).append(cid)
    for cluster_id, ids in matched.items():
        scores = per_cluster_by_id
        ids.sort(key=lambda cid: -(scores.get(cid, {}).get(cluster_id, 0.0)))
        matched[cluster_id] = ids[:depth]

    kept = {cid for ids in matched.values() for cid in ids}
    # An award that spiked but fell past every theme's depth is not silently
    # dropped: it is still eligible and the reader can still apply for it, so it
    # falls back to the open band rather than out of the feed.
    open_band = [cid for cid in ordered_ids if cid not in kept][:flat_depth]
    return matched, open_band, bands
