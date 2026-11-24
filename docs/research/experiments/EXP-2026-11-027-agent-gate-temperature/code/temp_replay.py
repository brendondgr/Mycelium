"""EXP-2026-11-027: EXP-2026-11-026's ``ink_replay.py`` (EXP-2026-11-022's
``replay.py`` plus the first reply of the ``scope-narrowed`` flow), with one
addition: the temperature in effect is written down and checked before the
first turn.

``--expect T`` is required. Just before the first model call (when
``replay.RawLog`` is built, after Django is set up, in a dry run too) this
reads three values:

* ``settings.LLM_TEMPERATURE`` (the environment variable decides it);
* the agent client's configured temperature (``build_llm_client("agent")``);
* the ``temperature`` field of a request body built exactly as the agent's
  port builds one (no temperature passed, so the client's default applies).

It appends them to ``logs/temperature.jsonl`` in this experiment's folder and
stops with exit code 3 if any differs from ``--expect``. Nothing else
changes: same arguments, databases (``…x022_<label>_<seed>_<arm>``), logs
(in EXP-2026-11-022's folder) and grading.

    <container, -e LLM_TEMPERATURE=0> python …/code/temp_replay.py \
        --label t0 --expect 0 --seed 101 --arm gate --reps 3 --conc 8
"""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
E22 = HERE.parent / "EXP-2026-11-022-gemma-empty-replies-replay" / "code"
sys.path.insert(0, str(E22))


def take(flag: str) -> str | None:
    """Read ``flag value`` from the arguments; ``--expect`` is removed, since
    ``replay.main`` does not know it."""
    if flag not in sys.argv:
        return None
    i = sys.argv.index(flag)
    value = sys.argv[i + 1]
    if flag == "--expect":
        del sys.argv[i:i + 2]
    return value


EXPECT = take("--expect")
if EXPECT is None:
    sys.exit("temp_replay.py: --expect <temperature> is required")
EXPECT = float(EXPECT)
ARGS = {f: take(f"--{f}") for f in ("label", "seed", "arm", "reps")}
DRY = "--dry-run" in sys.argv

import replay  # noqa: E402

# -- EXP-2026-11-026 ink_replay.py: keep the first reply of scope-narrowed -------
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


# -- the temperature check -------------------------------------------------------
class CheckedLog(replay.RawLog):
    def __init__(self, inner, path, model, probe):
        from django.conf import settings

        from apps.core.llm import build_llm_client

        client = build_llm_client(component="agent")
        body = client._payload([{"role": "user", "content": "x"}], model=model, reasoning=None,
                               temperature=None, max_tokens=0, tools=None, tool_choice=None,
                               extra_body=None)
        rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **ARGS, "dry_run": DRY,
               "model": model, "expect": EXPECT,
               "settings_LLM_TEMPERATURE": float(settings.LLM_TEMPERATURE),
               "client_config_temperature": float(client.config.temperature),
               "request_body_temperature": body.get("temperature"),
               "request_body_seed": body.get("seed")}
        got = [rec["settings_LLM_TEMPERATURE"], rec["client_config_temperature"],
               rec["request_body_temperature"]]
        rec["ok"] = all(g is not None and abs(float(g) - EXPECT) < 1e-9 for g in got)
        logs = HERE / "logs"
        logs.mkdir(exist_ok=True)
        with (logs / "temperature.jsonl").open("a") as fh:
            fh.write(json.dumps(rec) + "\n")
        print("temperature", json.dumps(rec), flush=True)
        if not rec["ok"]:
            sys.exit(3)
        super().__init__(inner, path, model, probe)


replay.RawLog = CheckedLog

if __name__ == "__main__":
    sys.exit(replay.main())
