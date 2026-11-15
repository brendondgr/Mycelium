"""EXP-2026-11-016: agreement between the string grader, the model reader and
(when filled) the person, on the adjudication sheet. The numbers are computed
in ``analyse.py`` (one source for every figure); this prints that section.

    python code/score_adjudication.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
subprocess.run([sys.executable, str(HERE / "analyse.py")], check=True, capture_output=True)
metrics = json.loads((HERE.parent / "data" / "metrics.json").read_text())
print(json.dumps({"adjudication": metrics["adjudication"], "claim_a": metrics["claim_a"]},
                 indent=2))
