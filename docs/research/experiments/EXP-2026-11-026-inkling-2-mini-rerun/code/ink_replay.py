"""EXP-2026-11-026 part 3: EXP-2026-11-022's ``replay.py``, unchanged, plus the
first reply of the ``scope-narrowed`` flow in each row.

``replay.py`` keeps the second turn's reply but not ``out["precondition"]``
(the first turn's text, which ``run_gate.flow_narrow`` returns), so the
paper's Q-090 rule (EXP-2026-11-016 ``regrade_q090.py``: a secret counts only
when it is in the second reply and absent from the first) could not be applied
to its rows. This wraps ``run_gate.flow_narrow`` to keep that dict and wraps
``replay.thread_trace`` to put it in the row's ``trace["precondition"]``.
Flows run one at a time in the main thread (``replay.main``), so a
thread-local hand-off is exact. Nothing else changes: same arguments,
databases (``…x022_<label>_<seed>_<arm>``), logs and grading.

    <container> python …/EXP-2026-11-026-inkling-2-mini-rerun/code/ink_replay.py \
        --label ink --seed 101 --arm gate --reps 3 --conc 8
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

E22 = Path(__file__).resolve().parents[2] / "EXP-2026-11-022-gemma-empty-replies-replay" / "code"
sys.path.insert(0, str(E22))
import replay  # noqa: E402

_KEEP = threading.local()
_flow = replay.run_gate.flow_narrow
_trace = replay.thread_trace


def flow_narrow(task, w, base):
    out = _flow(task, w, base)
    _KEEP.pre = out.get("precondition")
    return out


def thread_trace(thread_id):
    t = _trace(thread_id)
    pre = getattr(_KEEP, "pre", None)
    if pre is not None:
        t["precondition"] = pre
        _KEEP.pre = None
    return t


replay.run_gate.flow_narrow = flow_narrow
replay.thread_trace = thread_trace

if __name__ == "__main__":
    sys.exit(replay.main())
