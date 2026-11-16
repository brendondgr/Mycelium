"""EXP-2026-11-018 Amendment 3: run ``grade.py`` unchanged against the round-three
gold (``data/gold_r3.json``) and runs (``data/runs_r3.jsonl``).

    python3 docs/research/experiments/EXP-2026-11-018-agent-answers-gold/code/grade_r3.py [--first-attempt] [--decline-v2]

``grade.py`` reads ``data/gold.json`` by a fixed path, so this stages a copy of
the experiment's ``data/`` view in a temporary folder (gold_r3 as gold.json,
the r3 runs beside it), points ``grade.EXP`` there, runs ``grade.main`` with an
``_r3`` suffix, and copies its outputs back: ``data/graded_r3*.jsonl``,
``data/metrics_r3*.{json,csv}``, ``tables/summary_r3*.md``. Standard library only.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
sys.path.insert(0, str(HERE))
import grade  # noqa: E402


def main() -> int:
    extra = sys.argv[1:]
    suffix = "_r3" + ("_first_attempt" if "--first-attempt" in extra else "") + \
        ("_amend2" if "--decline-v2" in extra else "")
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp)
        (stage / "data").mkdir()
        (stage / "tables").mkdir()
        shutil.copy(EXP / "data" / "gold_r3.json", stage / "data" / "gold.json")
        shutil.copy(EXP / "data" / "runs_r3.jsonl", stage / "data" / "runs_r3.jsonl")
        grade.EXP = stage
        sys.argv = ["grade.py", "--runs", "data/runs_r3.jsonl", "--suffix", suffix, *extra]
        rc = grade.main()
        for src in [*(stage / "data").glob(f"*{suffix}.*"), *(stage / "tables").glob(f"*{suffix}.*")]:
            shutil.copy(src, EXP / src.parent.name / src.name)
            print("wrote", src.parent.name + "/" + src.name)
    return rc


if __name__ == "__main__":
    sys.exit(main())
