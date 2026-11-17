"""EXP-2026-11-018 Amendment 6 (2026-11-17, after the overnight fixes): round
three's gold builder, grader and partial-list measure, run **unchanged** under
the tag ``r4``.

    <container> python …/code/r4.py gold                  # needs the database
    python3 …/code/r4.py grade [--first-attempt]          # host, standard library
    python3 …/code/r4.py partial                          # host, standard library
    python3 …/code/r4.py jobs                             # prints the --only list

Each of round three's scripts reads and writes fixed ``_r3`` paths under the
experiment folder. This stages a temporary copy of the folder's ``data/`` view
(the r4 files under the names the script expects), points the script's ``EXP``
at it, runs its ``main`` and copies the outputs back under ``_r4`` names — the
way ``grade_r3.py`` already runs ``grade.py``. No grading or gold code is
copied or changed.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
#: The gold is tonight's (``gold_r4.json``) for every run graded here; ``R4_TAG``
#: names the run (``r4``: Qwen 3.8 27B, Amendment 6; ``r4g``: Gemma 4 31B,
#: Amendment 7).
GOLD = "r4"
TAG = os.environ.get("R4_TAG", "r4")
sys.path.insert(0, str(HERE))


def _stage():
    tmp = Path(tempfile.mkdtemp())
    (tmp / "data").mkdir()
    (tmp / "tables").mkdir()
    return tmp


def _runs() -> Path:
    runs = EXP / "data" / f"runs_{TAG}.jsonl"
    return runs if runs.exists() else runs.with_name(runs.name + ".gz")


def gold() -> int:
    import build_gold_r3 as B  # the frozen-question builder, unchanged

    stage = _stage()
    B.EXP = stage
    rc = B.main()
    out = EXP / "data" / f"gold_{GOLD}.json"
    shutil.copy(stage / "data" / "gold_r3.json", out)
    doc = json.loads(out.read_text())
    print(json.dumps({"wrote": str(out.relative_to(EXP)), "kept": len(doc["questions"]),
                      "dropped": doc.get("dropped"), "today": doc.get("today")}))
    return rc


def jobs() -> int:
    doc = json.loads((EXP / "data" / f"gold_{GOLD}.json").read_text())
    kept = doc["questions"]
    ids = [q["id"] for q in kept] if isinstance(kept, list) else list(kept)
    order = [q["id"] for q in json.loads((HERE / "questions.json").read_text())["questions"]]
    ids = [i for i in order if i in set(ids)]
    print(",".join(f"{arm}:{rep}:{qid}" for rep in (1, 2, 3) for arm in "abc" for qid in ids))
    return 0


def grade_(extra: list[str]) -> int:
    import grade  # unchanged

    suffix = f"_{TAG}" + ("_first_attempt" if "--first-attempt" in extra else "")
    stage = _stage()
    shutil.copy(EXP / "data" / f"gold_{GOLD}.json", stage / "data" / "gold.json")
    runs = _runs()
    shutil.copy(runs, stage / "data" / runs.name)
    grade.EXP = stage
    sys.argv = ["grade.py", "--runs", f"data/runs_{TAG}.jsonl", "--suffix", suffix, *extra]
    rc = grade.main()
    for src in [*(stage / "data").glob(f"*{suffix}.*"), *(stage / "tables").glob(f"*{suffix}.*")]:
        shutil.copy(src, EXP / src.parent.name / src.name)
        print("wrote", src.parent.name + "/" + src.name)
    return rc


def partial() -> int:
    import partial_r3 as P  # unchanged: the registered patterns and classes

    stage = _stage()
    runs = _runs()
    shutil.copy(runs, stage / "data" / runs.name.replace(f"_{TAG}", "_r3"))
    P.EXP = stage
    rc = P.main()
    for src in [*(stage / "data").glob("*partial_r3*"), *(stage / "tables").glob("*_r3.md")]:
        dst = EXP / src.parent.name / src.name.replace("_r3", f"_{TAG}")
        shutil.copy(src, dst)
        print("wrote", dst.parent.name + "/" + dst.name)
    return rc


if __name__ == "__main__":
    cmd, rest = (sys.argv[1] if len(sys.argv) > 1 else ""), sys.argv[2:]
    sys.exit({"gold": gold, "jobs": jobs, "partial": partial}.get(cmd, lambda: grade_(rest))()
             if cmd in ("gold", "jobs", "partial", "grade") else 2)
