"""EXP-2026-11-019 Amendment 10 (2026-11-18): round two's counted run (gate and
baseline arms, S1-S10 and S4o, three repetitions), unchanged, on Qwen 3.8 27B,
in its own copy of the sandbox.

``run019.py``, ``regrade019.py`` and ``recall019.py`` hard-code round two's copy
(``mycelium_sandbox_exp019``) and ``run019.py --setup`` writes round two's
``data/world.json``. This only points them at the copy named by ``SANDBOX_DB``
(which must start ``mycelium_sandbox_exp019``) and writes the setup to
``data/world_<tag>.json``; the world, plan, arms, graders and logs are theirs,
imported unchanged.

    $R/run019_q.py setup --tag mainq           # migrate, overlay, uniqueness, preflight (no model)
    $R/run019_q.py run --arm gate --reps 1 --rep-start 0 --conc 60 --tag mainq [--dry-run]
    $R/run019_q.py regrade --tag mainq         # logs/grades_v2_<arm>_mainq.jsonl
    $R/run019_q.py recall --tag mainq          # logs/recall_<arm>_mainq.jsonl
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

CODE = Path(__file__).resolve().parent
sys.path.insert(0, str(CODE))
DB = os.environ.get("SANDBOX_DB", "")
assert DB.startswith("mycelium_sandbox_exp019") and DB != "mycelium_sandbox_exp019", (
    "SANDBOX_DB must name this run's own copy, never round two's")

import run019  # noqa: E402

run019.EXP_DB = DB


def setup(tag: str) -> int:
    env = run019.setup_django()
    import world019
    from django.core.management import call_command

    call_command("migrate", verbosity=0)
    world = world019.base_world()
    plan = world019.plan(world)
    out = {"env": env, "plan": plan.as_dict(), "apply": world019.apply(world, plan),
           "uniqueness": world019.uniqueness(world), "preflight": world019.preflight(world, plan)}
    (run019.HERE / "data" / f"world_{tag}.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({"env": env, "uniqueness": out["uniqueness"],
                      "preflight_failures": out["preflight"]["failures"]}, indent=1, default=str))
    return 1 if out["preflight"]["failures"] else 0


def main() -> int:
    cmd, rest = (sys.argv[1] if len(sys.argv) > 1 else ""), sys.argv[2:]
    if cmd == "setup":
        tag = rest[rest.index("--tag") + 1]
        return setup(tag)
    if cmd == "run":
        assert "--setup" not in rest
        conc = int(rest[rest.index("--conc") + 1]) if "--conc" in rest else 2
        assert conc <= 64, "at most 64 in flight on the second server"
        sys.argv = ["run019.py", *rest]
        return run019.main()
    if cmd == "regrade":
        import regrade019

        sys.argv = ["regrade019.py", *rest]
        return regrade019.main()
    if cmd == "recall":
        import recall019

        sys.argv = ["recall019.py", *rest]
        return recall019.main()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
