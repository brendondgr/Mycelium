"""The daily run finds its reporter when systemd starts it.

systemd runs ``ops/nightly/manual_all.py`` by path, so only the script's own
folder is importable at first. After the script moved there (2026-11-06) the
``mylo`` import failed, the guard swallowed it, and the run posted nothing to
Discord and wrote no run state, with every stage still green.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PROBE = """
import importlib.util, sys
spec = importlib.util.spec_from_file_location("manual_all", sys.argv[1])
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
print(m.reporting is not None, m.write_run_state is not None)
"""


class NightlyImportTests(unittest.TestCase):
    def test_the_reporter_loads_from_outside_the_repository(self) -> None:
        out = subprocess.run(
            [sys.executable, "-I", "-c", PROBE, str(ROOT / "ops/nightly/manual_all.py")],
            cwd="/",
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(out.returncode, 0, out.stderr[-2000:])
        self.assertEqual(out.stdout.split(), ["True", "True"])


if __name__ == "__main__":
    unittest.main()
