"""EXP-2026-09-019: the drift weight sweep (persona-level). Writes
/app/data/sandbox/exp019.json.

    DATABASE_URL=.../mycelium_sandbox_ambdrift manage.py shell < .../code/run.py
"""

import json
import sys
import time

from django.db import connection

sys.path.insert(0, "/app/web/backend")
from sandbox.ambient import nights  # noqa: E402
from sandbox.ambient import world as world_mod  # noqa: E402

assert connection.settings_dict["NAME"] == "mycelium_sandbox_ambdrift", connection.settings_dict["NAME"]
started = time.time()
corpus = nights.seed_corpus(world_mod.POOL)
seeded = round(time.time() - started, 1)
started = time.time()
result = nights.drift(None, weights=(0.05, 0.15, 0.30, 1.0))
out = {"corpus_items": corpus, "timings": {"seed_s": seeded, "drift_s": round(time.time() - started, 1)}, "drift": result}
with open("/app/data/sandbox/exp019.json", "w") as handle:
    json.dump(out, handle, indent=1, default=str)
print("RESULT " + json.dumps(out, default=str))
