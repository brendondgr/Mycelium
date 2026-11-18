"""EXP-2026-11-023 diagnostic: why the slot reader returned no slots for some
seekers. Reads each faculty query once more through apps.collab.slots with the
raw model reply captured; writes the raw replies privately and counts publicly."""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run023

run023.setup_django()
from apps.collab import slots as reader

rows = []
for person in run023.people()["faculty"]:
    raws = []
    def complete(system, user):
        out = reader._settings_complete(system, user)
        raws.append(out)
        return out
    class _Typed:
        pk = None
        metadata = {"title": "", "description": run023.query_text(person)}
    t = time.time()
    outcome = reader.extract(_Typed(), complete=complete, min_words=reader.MIN_NEED_WORDS)
    rows.append({"id": person["id"], "seconds": round(time.time() - t, 1),
                 "slots": outcome.slots if outcome else None,
                 "thin": outcome.thin if outcome else None,
                 "refused": outcome.refused if outcome else None,
                 "attempts": outcome.attempts if outcome else None,
                 "raw": raws})
    print(person["id"], len(outcome.slots) if outcome else None, outcome.thin if outcome else None,
          [len(r or "") for r in raws], (outcome.refused if outcome else None), flush=True)
run023.write_private("diag_slots.json", rows)
