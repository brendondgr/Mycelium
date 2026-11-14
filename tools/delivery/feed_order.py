"""Where fit puts an item in a feed, before its rank does.

Every feed (papers, grants, conferences, fellowships; personal, lab, project)
and the report's reading of it order rows by one band first, then by their own
rank. The band is what keeps a poor fit off the top:

0. **New and worth reading.** A row inside its one-week "New" pin
   (:mod:`tools.recommendation.pinning`) whose verdict is ``read`` or ``skim``.
1. **Everything else**, in rank order — including a new row that was never
   judged (it fell outside the slate head the run wrote up) or was filed.
2. **Judged not worth the time** (verdict ``skip``). The report already drops
   these to its reference block; the feed now agrees and lists them last.

Before this a pin lifted *any* new row, so on 2026-11-14 the demo's conference
feed opened with five unrelated conferences ranked 52nd to 95th, and a grant the
model called "too speculative" for its reader sat third.
"""

from __future__ import annotations

from tools.recommendation.verdicts import READ, SKIM, SKIP

#: Verdicts a "New" pin may lift to the top of a feed.
LIFTED = frozenset({READ, SKIM})


def is_pinned(signals: dict, today: str) -> bool:
    pinned_until = signals.get("pinned_until")
    return bool(pinned_until and pinned_until >= today)


def fit_band(signals: dict, today: str) -> int:
    """0 = new and worth reading, 1 = the rest, 2 = judged a skip."""
    verdict = signals.get("verdict")
    if verdict == SKIP:
        return 2
    if verdict in LIFTED and is_pinned(signals, today):
        return 0
    return 1
