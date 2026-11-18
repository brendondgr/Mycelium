"""EXP-2026-11-019 Amendment 10: ``analyse.py`` unchanged on a tagged rerun of
round two's counted run (default ``mainq``, Qwen 3.8 27B).

    python3 docs/research/experiments/EXP-2026-11-019-agent-collab-scenarios/code/analyse_q.py [tag]

``analyse.py`` writes round two's ``data/metrics.json``, ``data/metrics.csv``
and ``tables/summary.md``. This stages the tag's logs in a temporary folder,
points the script at it, runs it, and copies its outputs back as
``data/metrics_<tag>.json``, ``data/metrics_<tag>.csv`` and
``tables/summary_<tag>.md``, so round two's files are never touched.
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
    tag = sys.argv[1] if len(sys.argv) > 1 else "mainq"
    stage = Path(tempfile.mkdtemp())
    (stage / "logs").mkdir()
    for kind in ("runs", "grades_v2", "recall"):
        for arm in ("gate", "baseline"):
            src = HERE / "logs" / f"{kind}_{arm}_{tag}.jsonl"
            if src.exists():
                shutil.copy(src, stage / "logs" / src.name)
    A.HERE = stage
    sys.argv = ["analyse.py", "--tag", tag]
    rc = A.main()
    shutil.copy(stage / "data" / "metrics.json", HERE / "data" / f"metrics_{tag}.json")
    shutil.copy(stage / "data" / "metrics.csv", HERE / "data" / f"metrics_{tag}.csv")
    shutil.copy(stage / "tables" / "summary.md", HERE / "tables" / f"summary_{tag}.md")
    print(f"wrote data/metrics_{tag}.json, data/metrics_{tag}.csv, tables/summary_{tag}.md")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
