"""EXP-2026-11-017 Amendment 3 (2026-11-18): the registered probes, unchanged,
on Qwen 3.8 27B, in their own database.

``lifecycle.py`` hard-codes round two's database
(``mycelium_agent_eval_r2_lifecycle``) and ``--fresh-db`` drops it. This only
renames the database (``LIFECYCLE_DB``, default
``mycelium_agent_eval_r2_lifecycle_qwen``; it must end in ``_qwen``) and runs
``lifecycle.main`` with the arguments given, so round two's database is never
touched. Everything else is ``lifecycle.py`` as registered.

    $R/lifecycle_q.py --fresh-db --probes "" --tag qwen_setup     # create, migrate, seed; no run
    $R/lifecycle_q.py --probes delete_thread,delete_obs,optout,excluded --conc 12 --tag qwen_a --seed …
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lifecycle  # noqa: E402

DB = os.environ.get("LIFECYCLE_DB", "mycelium_agent_eval_r2_lifecycle_qwen")
assert DB.endswith("_qwen") and DB != "mycelium_agent_eval_r2_lifecycle", DB
lifecycle.DB = DB

if __name__ == "__main__":
    conc = int(sys.argv[sys.argv.index("--conc") + 1]) if "--conc" in sys.argv else 3
    assert conc <= 16, "Amendment 3: at most 16 runs per process (64 model requests across all)"
    sys.exit(lifecycle.main())
