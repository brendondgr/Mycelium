"""Regenerate this experiment's figure from `../data/lists.json`.

    python make_figures.py

The chart itself lives in `../code/timing_chart.py` so the booklet builder and
this runner share one implementation. No number is written here.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

from timing_chart import build

if __name__ == "__main__":
    build()
    print("  wrote fig-timing.svg + fig-timing.pdf + fig-timing.png")
