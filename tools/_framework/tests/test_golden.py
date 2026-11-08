"""Nothing the platform exposes moved by accident: the golden snapshots.

Runs ``tools/_framework/golden.py check`` in a subprocess so the snapshot is
taken from a plain process, not from inside the test settings.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_golden_snapshots_are_unchanged():
    env = {k: v for k, v in os.environ.items() if k != "MYCELIUM_TOOLS_STRICT"}
    env["MYCELIUM_TOOLS_STRICT"] = "1"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "_framework" / "golden.py"), "check"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
        timeout=600,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
