"""The shared daily-run state file: write + read roundtrip, tolerant of failure."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mylo import runstate


class RunStateTests(unittest.TestCase):
    def test_write_then_read_roundtrips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sub" / "state.json"  # parent created on write
            with mock.patch.object(runstate, "RUN_STATE_PATH", path):
                runstate.write_run_state(
                    ok=True,
                    scrape_ran=False,
                    stages_run=["run_daily_suggestions", "generate_daily_briefing"],
                )
                state = runstate.read_run_state()
        self.assertTrue(state["ok"])
        self.assertFalse(state["scrape_ran"])
        self.assertEqual(state["stages_run"][-1], "generate_daily_briefing")
        self.assertIn("finished_at", state)
        self.assertIn("host", state)

    def test_read_missing_returns_none(self) -> None:
        with mock.patch.object(
            runstate, "RUN_STATE_PATH", Path("/no/such/mylo-last-run.json")
        ):
            self.assertIsNone(runstate.read_run_state())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
