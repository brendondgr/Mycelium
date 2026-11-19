"""EXP-2026-11-025: EXP-2026-11-024's harness, two arms (prev, multi), outputs
redirected to this folder and ``<private>/exp025/``. See PROTOCOL.md.

    PRIVATE_DIR=<dir> FROZEN=<git archive of a commit> code/drive.sh \
        identity | search --arm prev|multi
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(
    0, str(HERE.parent / "EXP-2026-11-024-collab-typed-question-rerun" / "code")
)
import run024  # noqa: E402  (puts run023 on the path)
import run023  # noqa: E402

run023.HERE = HERE
run024.PRIVATE_OUT = run023.PRIVATE / "exp025"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("cmd", choices=["identity", "search"])
    parser.add_argument("--only", default="")
    parser.add_argument("--arm", choices=["prev", "multi"], default="multi")
    args = parser.parse_args()
    {"identity": run024.cmd_identity, "search": run024.cmd_search}[args.cmd](args)


if __name__ == "__main__":
    main()
