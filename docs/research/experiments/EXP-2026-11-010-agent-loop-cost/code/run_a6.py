"""EXP-2026-11-010 Amendment 6 (round three, Phase 3): arm A6.

``run_a2.py`` unchanged, with one addition: every turn's model port is wrapped
in EXP-2026-11-019's ``r3turns.Recorder`` (outside ``mylo_turn.TimedPort``), so
each row also carries, per model call, the finish reason, completion and
reasoning tokens, and two counts:

* ``cap_hits`` — calls that ended at the reply cap (``finish_reason`` ``length``
  or completion tokens >= ``tools.agent.max_output_tokens``);
* ``thinking_budget_hits`` — calls whose reasoning tokens reached
  ``tools.agent.thinking_budget`` (``None`` when the server reports no
  reasoning tokens).

Same arguments as ``run_a2.py`` (``--reps``, ``--tag``, ``--rotate``, …).
"""

from __future__ import annotations

import sys
from pathlib import Path

CODE = Path(__file__).resolve().parent
sys.path[:0] = [str(CODE), str(CODE.parents[1] / "EXP-2026-11-019-agent-collab-scenarios" / "code")]
import mylo_turn  # noqa: E402
import run_a2  # noqa: E402

_original = mylo_turn.run_question


def run_question(ctx, q, *, visitor, deadline_s=900.0, port=None):
    import r3turns

    from tools.agent import config
    from tools.agent.llmcall import default_port

    cap = int(config.get("max_output_tokens") or 0)
    budget = int(config.get("thinking_budget") or 0)
    r3turns.begin()
    row = _original(ctx, q, visitor=visitor, deadline_s=deadline_s,
                    port=r3turns.Recorder(port or default_port()))
    calls = r3turns.calls()
    row["model_call_log"] = calls
    row["max_output_tokens"] = cap
    row["thinking_budget"] = budget
    row["cap_hits"] = sum(1 for c in calls if c.get("finish_reason") == "length"
                          or (cap and (c.get("completion_tokens") or 0) >= cap))
    reported = [c.get("reasoning_tokens") for c in calls if c.get("reasoning_tokens") is not None]
    row["thinking_budget_hits"] = (sum(1 for r in reported if budget and r >= budget)
                                   if reported else None)
    row["empty_calls"] = sum(1 for c in calls if c.get("empty"))
    return row


mylo_turn.run_question = run_question

if __name__ == "__main__":
    sys.exit(run_a2.main())
