"""The daily run routes its notable conditions to the Discord reporter.

Exercises ``manual_all.scrape_opportunities`` with the host runner stubbed, so no
``uv``/``docker``/Pivot subprocess is touched — we only assert that the right
severity and an actionable message reach the reporter.

    uv run python -m unittest discover -s mylo -p 'test_*.py'
"""

from __future__ import annotations

import unittest
from unittest import mock

import manual_all


class ScrapeReportingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []
        patcher = mock.patch.object(
            manual_all,
            "_notify",
            lambda kind, title, body="", **kw: self.calls.append((kind, title, kw)),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _kinds(self) -> list[str]:
        return [kind for kind, _title, _kw in self.calls]

    def test_missing_uv_warns_and_skips(self) -> None:
        with mock.patch.object(manual_all, "have_uv", return_value=False):
            ran = manual_all.scrape_opportunities()
        self.assertFalse(ran)
        self.assertEqual(self._kinds(), ["warn"])

    def test_no_session_unattended_reports_actionable_error(self) -> None:
        with (
            mock.patch.object(manual_all, "have_uv", return_value=True),
            mock.patch.object(manual_all, "pivot_session_exists", return_value=False),
            mock.patch("sys.stdin") as stdin,
        ):
            stdin.isatty.return_value = False
            ran = manual_all.scrape_opportunities()
        self.assertFalse(ran)
        self.assertIn("error", self._kinds())
        error = next(c for c in self.calls if c[0] == "error")
        # The alert must tell a human exactly what to do.
        self.assertIn("login", error[2].get("action", "").lower())
        self.assertEqual(error[2].get("stage"), "scrape")


class RunStateTests(unittest.TestCase):
    def test_write_run_state_is_json_and_tolerates_bad_path(self) -> None:
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(
                manual_all, "RUN_STATE_PATH", Path(tmp) / "sub" / "state.json"
            ):
                manual_all._write_run_state(
                    ok=True, scrape_ran=False, stages_run=["run_daily_suggestions"]
                )
                data = json.loads((Path(tmp) / "sub" / "state.json").read_text())
        self.assertTrue(data["ok"])
        self.assertFalse(data["scrape_ran"])
        self.assertEqual(data["stages_run"], ["run_daily_suggestions"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
