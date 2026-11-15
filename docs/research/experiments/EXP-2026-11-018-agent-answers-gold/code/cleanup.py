"""Delete the demo threads this round's harnesses created (EXP-2026-11-018,
EXP-2026-11-020, and EXP-2026-11-013 Amendment 5), and nothing else.

    docker compose run … python docs/research/experiments/EXP-2026-11-018-agent-answers-gold/code/cleanup.py [--dry-run]

Threads are matched by ``demo_visitor`` exactly (the harnesses set it); the
demo's own 24-hour sweep would remove them anyway. Prints counts.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "EXP-2026-11-013-agent-answers-human-judged" / "code"))
import mylo_turn  # noqa: E402

VISITORS = ("EXP-2026-11-018", "EXP-2026-11-020", "EXP-2026-11-013")

mylo_turn.setup()
from tools.agent.models import AgentThread  # noqa: E402

rows = AgentThread.objects.filter(demo_visitor__in=VISITORS)
counts = {v: rows.filter(demo_visitor=v).count() for v in VISITORS}
if "--dry-run" not in sys.argv:
    deleted, by_model = rows.delete()
    counts["deleted_rows"] = by_model
print(json.dumps(counts))
