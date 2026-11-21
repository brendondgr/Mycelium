"""EXP-2026-11-026: EXP-2026-11-017's registered lifecycle probes, unchanged,
on Inkling 2 Mini, in their own database.

The same thin wrapper as EXP-2026-11-017's ``lifecycle_q.py`` (Amendment 3,
the Qwen 3.8 27B rerun), with the database renamed: ``LIFECYCLE_DB`` must end
in ``_ink``, so neither round two's database nor the Qwen rerun's is touched.
Everything else is ``lifecycle.py`` as registered.

    $R/lifecycle_ink.py --fresh-db --probes "" --tag ink_setup     # create, migrate, seed; no run
    $R/lifecycle_ink.py --probes delete_thread --conc 12 --tag ink_a --seed …
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

E17 = Path(__file__).resolve().parents[2] / "EXP-2026-11-017-agent-memory-lifecycle" / "code"
sys.path.insert(0, str(E17))
import lifecycle  # noqa: E402

DB = os.environ.get("LIFECYCLE_DB", "mycelium_agent_eval_r2_lifecycle_ink")
assert DB.endswith("_ink") and DB != "mycelium_agent_eval_r2_lifecycle", DB
lifecycle.DB = DB

if __name__ == "__main__":
    conc = int(sys.argv[sys.argv.index("--conc") + 1]) if "--conc" in sys.argv else 3
    assert conc <= 16, "at most 16 runs per process"
    sys.exit(lifecycle.main())
