"""Per-cluster admission: which candidates a theme is allowed to slate.

The deployed test was one absolute cosine threshold applied across a whole
profile. A theme whose vocabulary sits further from the corpus produces
systematically lower cosines, so that single number could exclude a theme
entirely while admitting hundreds of items from its neighbour. The reader then
concluded nothing was found for that strand of their work, when in fact nothing
was *asked* for it.

The replacement is a two-part gate:

* **the absolute floor** — the existing threshold, unchanged, which admits
  anything genuinely close to the profile; or
* **the relative floor** — a candidate reaching ``frac`` of *its own theme's*
  best score, which is scale-free and therefore fair to a distant theme;

with a **hard absolute minimum** underneath both. The hard minimum is not
optional. Without it a theme with nothing genuinely relevant still admits its
ten least-irrelevant candidates, because every set has a best element and half
of that best is still something. The floor is what makes a dead theme admit
nothing rather than noise.

:func:`admit` returns the admitted ids plus a small stats record, because the
diagnostic matters as much as the decision: a theme admitting *only* by the
relative floor for several consecutive days is a retrieval gap, not a ranking
problem, and should be surfaced rather than papered over.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from django.conf import settings

from apps.content.fusion import ClusteredHit

#: Fraction of a theme's own best score a candidate must reach to be admitted by
#: the relative floor. Half is deliberately generous — the hard minimum below is
#: what stops it letting noise in, and a stingy relative floor just reinstates the
#: problem it exists to solve.
DEFAULT_RELATIVE_FRAC = 0.5

#: The absolute cosine no candidate is admitted below, whatever its theme thinks
#: of it. Set under the normal match threshold — it is a floor, not a second
#: threshold — but far enough above zero that an empty theme stays empty.
DEFAULT_HARD_FLOOR = 0.35


def relative_frac() -> float:
    return float(getattr(settings, "CLUSTER_ADMIT_FRAC", DEFAULT_RELATIVE_FRAC))


def hard_floor() -> float:
    return float(getattr(settings, "CLUSTER_ADMIT_HARD_FLOOR", DEFAULT_HARD_FLOOR))


@dataclass
class AdmissionStats:
    """What the gate did, per run and per theme — the line the run log prints."""

    absolute: int = 0
    relative: int = 0
    blocked_by_floor: int = 0
    #: ``{cluster_id: (absolute, relative)}`` — a theme whose absolute count sits
    #: at zero for several runs has a retrieval gap, not a ranking problem.
    per_cluster: dict[str, tuple[int, int]] = field(default_factory=dict)

    @property
    def admitted(self) -> int:
        return self.absolute + self.relative

    def note(self) -> str:
        bits = [f"{self.absolute} cleared the absolute floor"]
        if self.relative:
            bits.append(f"+{self.relative} by a theme's relative floor")
        if self.blocked_by_floor:
            bits.append(f"{self.blocked_by_floor} held back by the hard minimum")
        starved = sorted(
            cid for cid, (absolute, rel) in self.per_cluster.items()
            if absolute == 0 and rel
        )
        if starved:
            bits.append(f"relative-only themes: {', '.join(starved)}")
        return "; ".join(bits)


def admit(
    clustered: Sequence[ClusteredHit],
    best_cosine: Mapping[str, float],
    *,
    threshold: float,
    frac: float | None = None,
    floor: float | None = None,
    relative: bool = True,
) -> tuple[set[str], AdmissionStats]:
    """Ids admitted by either floor, and what each floor contributed.

    ``best_cosine`` is the dense channel's best cosine per candidate — the same
    quantity the single global threshold judged, so the absolute half of the gate
    is literally unchanged behaviour for anything that already cleared it.

    The relative half is judged per theme, on that theme's *own* combined score
    (``per_cluster``), never on the global maximum: the whole point is that a
    theme's scores are only comparable with themselves.

    ``relative=False`` turns that half off, and the single-cluster path passes it.
    A profile with one theme has nothing to be unfair between — the relative floor
    exists to stop a *neighbouring* theme monopolising admission — so applying it
    there would widen a feed for no reason and break the guarantee that a
    single-cluster profile behaves exactly as it did before.
    """
    frac = relative_frac() if frac is None else frac
    minimum = hard_floor() if floor is None else floor
    stats = AdmissionStats()
    if not clustered:
        return set(), stats

    best_per_cluster: dict[str, float] = {}
    for hit in clustered:
        for cluster_id, score in hit.per_cluster.items():
            if score > best_per_cluster.get(cluster_id, float("-inf")):
                best_per_cluster[cluster_id] = score

    admitted: set[str] = set()
    for hit in clustered:
        cid = str(hit.item.id)
        cosine = best_cosine.get(cid, 0.0)
        if cosine >= threshold:
            admitted.add(cid)
            stats.absolute += 1
            for cluster_id in hit.per_cluster:
                counts = stats.per_cluster.setdefault(cluster_id, (0, 0))
                stats.per_cluster[cluster_id] = (counts[0] + 1, counts[1])
            continue
        if not relative:
            continue
        # The relative floor, theme by theme — and the hard minimum under it.
        reaching = [
            cluster_id
            for cluster_id, score in hit.per_cluster.items()
            if score >= frac * best_per_cluster.get(cluster_id, 0.0)
        ]
        if not reaching:
            continue
        if cosine < minimum:
            stats.blocked_by_floor += 1
            continue
        admitted.add(cid)
        stats.relative += 1
        for cluster_id in reaching:
            counts = stats.per_cluster.setdefault(cluster_id, (0, 0))
            stats.per_cluster[cluster_id] = (counts[0], counts[1] + 1)
    return admitted, stats
