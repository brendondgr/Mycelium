"""EXP-2026-11-017 Amendment 3: ``analyse.py`` unchanged on the Qwen 3.8 27B
rerun's logs (``logs/lifecycle_<prefix>_*.jsonl``, default prefix ``qwen``).

    python3 docs/research/experiments/EXP-2026-11-017-agent-memory-lifecycle/code/analyse_q.py [prefix]

``analyse.py`` reads ``logs/lifecycle_main*.jsonl`` and writes round two's
``data/metrics.json``, ``data/metrics.csv`` and ``tables/summary.md``. This
stages the rerun's logs under the names it reads in a temporary folder, sets
its count of hung attempts to this run's (none known; a hung process is
recorded in ISSUES.md and added here by hand only with that note), runs it,
and copies the outputs back as ``data/metrics_<prefix>.json``,
``data/metrics_<prefix>.csv`` and ``tables/summary_<prefix>.md``.
Standard library only.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyse as A  # noqa: E402


def main() -> int:
    prefix = sys.argv[1] if len(sys.argv) > 1 else "qwen"
    stage = Path(tempfile.mkdtemp())
    (stage / "logs").mkdir()
    srcs = sorted((HERE / "logs").glob(f"lifecycle_{prefix}_*.jsonl"))
    srcs = [s for s in srcs if not s.name.endswith("_dry.jsonl")]
    if not srcs:
        print("no logs for", prefix)
        return 1
    for s in srcs:
        shutil.copy(s, stage / "logs" / s.name.replace(f"lifecycle_{prefix}_", "lifecycle_main_"))
    A.HERE = stage
    A.HUNG = {}
    rc = A.main()
    shutil.copy(stage / "data" / "metrics.json", HERE / "data" / f"metrics_{prefix}.json")
    shutil.copy(stage / "data" / "metrics.csv", HERE / "data" / f"metrics_{prefix}.csv")
    shutil.copy(stage / "tables" / "summary.md", HERE / "tables" / f"summary_{prefix}.md")
    print(f"read {[s.name for s in srcs]}; wrote data/metrics_{prefix}.json, "
          f"data/metrics_{prefix}.csv, tables/summary_{prefix}.md")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
