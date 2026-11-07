"""Tests for the Mylo host package (run with ``python -m unittest``).

The daily run (``ops/nightly/manual_all.py``) is a script, not a package, so
put its folder on the import path for the tests that exercise it.
"""

import sys
from pathlib import Path

_NIGHTLY = Path(__file__).resolve().parents[2] / "ops" / "nightly"
if str(_NIGHTLY) not in sys.path:
    sys.path.insert(0, str(_NIGHTLY))
