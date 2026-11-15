"""EXP-2026-11-010 A5: mark the 8-process rows as run 8 at a time.

    python code/stamp_process_arm.py a5p8 8

``run_a2.py`` writes ``conc`` only for the thread arm (``--conc``). The process
arm runs eight one-off containers with ``--conc 1``, so its rows carry no
``conc`` and ``analyse.py`` would sum their 96 turn times as if one at a time.
Round one's ``a3p8``/``a3p8b`` rows carry ``conc: 8`` (how it was added is not
recorded); this adds the same field, and nothing else, to the named run.
"""

import json
import sys
from pathlib import Path

tag, conc = sys.argv[1], int(sys.argv[2])
path = Path(__file__).resolve().parent.parent / "data" / f"a2_{tag}.jsonl"
rows = [json.loads(line) for line in path.open()]
for r in rows:
    r["conc"] = conc
path.write_text("".join(json.dumps(r) + "\n" for r in rows))
print(f"{len(rows)} rows of {tag} marked conc={conc}")
