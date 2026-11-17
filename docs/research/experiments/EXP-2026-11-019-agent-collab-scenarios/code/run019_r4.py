"""EXP-2026-11-019 Amendment 7 (2026-11-17): Amendment 4's run, unchanged, on
Gemma 4 31B — on its own two copies of the sandbox, so round three's copies
stay as that round left them.

    $R/run019_r4.py --mode <mode> --setup
    $R/run019_r4.py --mode <repeated|fresh> --rep R --conc 8 --tag r4

Everything is ``run019_r3.py``; this only names the copies. The log is
``logs/runs_r3_<mode>_instance_r4.jsonl`` (the ``runs_r3_`` prefix is that
script's; the tag is ``r4``).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run019_r3 as R  # noqa: E402

#: ``EXP019_COPY`` names the pair of copies (``r4`` for Amendment 7's run, ``r5``
#: for the run after the lost-call fix), so a later run never asks in a copy an
#: earlier run already asked in.
COPY = os.environ.get("EXP019_COPY", "r4")
R.DBS = {"repeated": f"mycelium_sandbox_exp019{COPY}rep", "fresh": f"mycelium_sandbox_exp019{COPY}fresh"}

if __name__ == "__main__":
    sys.exit(R.main())
