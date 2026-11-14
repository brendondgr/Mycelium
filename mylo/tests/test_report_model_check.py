"""The daily run checks the model again right before writing reports.

On 2026-11-14 the pre-flight passed, the model dropped out mid-run, and every
report came out as a template with nothing said about it.
"""

from __future__ import annotations

import unittest
from unittest import mock

import manual_all


class ReportModelCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.notes: list[tuple[str, str]] = []
        self.slept: list[int] = []
        def note(kind, title, body="", **kw):
            self.notes.append((kind, title))

        for name, value in (
            ("_notify", note),
            ("model_off_on_purpose", lambda: False),
        ):
            patcher = mock.patch.object(manual_all, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _check(self, codes: list[int], wait: int = 6 * 60) -> tuple[bool, int]:
        calls = iter(codes)
        with mock.patch.object(manual_all, "run_manage", lambda *a, **k: next(calls)):
            ok = manual_all.model_ready_for_reports(
                ["docker"], wait=wait, every=120, sleep=self.slept.append
            )
        return ok, len(self.slept)

    def test_a_model_that_is_up_is_not_waited_for(self) -> None:
        self.assertEqual(self._check([0]), (True, 0))
        self.assertEqual(self.notes, [])

    def test_the_run_waits_for_the_model_to_come_back(self) -> None:
        self.assertEqual(self._check([1, 1, 0]), (True, 2))
        self.assertEqual(
            self.notes, [("warn", "LLM endpoint was down before the reports")]
        )

    def test_a_model_that_stays_down_is_reported(self) -> None:
        ok, sleeps = self._check([1, 1, 1, 1, 1])
        self.assertFalse(ok)
        self.assertEqual(sleeps, 3)  # 0, 2, 4, 6 minutes checked
        self.assertEqual(
            self.notes, [("warn", "LLM endpoint unreachable before the reports")]
        )

    def test_only_the_report_stage_is_gated(self) -> None:
        self.assertEqual(manual_all.report_commands(), {"generate_daily_briefing"})


if __name__ == "__main__":
    unittest.main()
