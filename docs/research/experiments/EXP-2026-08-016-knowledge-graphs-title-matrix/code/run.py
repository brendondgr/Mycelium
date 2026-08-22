"""The same four arms on a second research area: `knowledge graphs`.

    docker compose up -d postgres
    uv run --project eval python .../code/run.py

`EXP-2026-08-015` gave a clean per-category winner on `Agentic AI in healthcare`.
This asks whether that was a property of the **arms** or of that **corner of the
corpus**, by repeating the identical measurement on a different declared research
cluster and a third blinding.

The retrieval itself is `EXP-2026-08-015`'s runner, imported and re-pointed —
**not copied**. That experiment's `main()` reads its query, its blinding and its
output directory from module globals, so overriding those three and calling it is
the whole of this file. A second copy of the arm code would be a second chance for
the two areas to be scored by subtly different pipelines, which would destroy the
only comparison this experiment exists to make.

Writes `data/lists.json`. No LLM, no network.
"""

from __future__ import annotations

import sys
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent.parent
PRIOR = EXP_DIR.parent / "EXP-2026-08-015-four-arm-title-matrix" / "code"
sys.path.insert(0, str(PRIOR))

QUERY = "knowledge graphs"

#: A **third** permutation, and letters used by neither previous booklet. Reusing
#: W-Z would carry the healthcare verdicts into this read; A-J would carry the
#: first booklet's. M/N/P/R share no letter with either (and skip O, which reads
#: as a zero in a rank column).
BLIND_ORDER = {
    "M": "fusion_union_pool",
    "N": "fusion_dense_pool",
    "P": "fusion_dense_pool+xenc",
    "R": "fusion_union_splade",
}


def main() -> int:
    import run as base

    base.QUERY = QUERY
    base.BLIND_ORDER = BLIND_ORDER
    base.EXP_DIR = EXP_DIR
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
