"""The daily run routes its notable conditions to the Discord reporter.

Exercises ``manual_all.scrape_opportunities`` with the host/container runners
stubbed, so no ``uv``/``docker``/subprocess is ever actually touched — we only
assert that the right severity and an actionable message reach the reporter.

    uv run python -m unittest discover -s mylo -p 'test_*.py'
"""

from __future__ import annotations

import unittest
from unittest import mock

import manual_all

#: A stand-in for the Compose base command (``ensure_ready()``'s return value).
#: Never actually invoked — every test below stubs ``run_manage``/``run_host``.
_BASE = ["docker", "compose"]


class ScrapeReportingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []
        notify_patcher = mock.patch.object(
            manual_all,
            "_notify",
            lambda kind, title, body="", **kw: self.calls.append((kind, title, kw)),
        )
        notify_patcher.start()
        self.addCleanup(notify_patcher.stop)
        # ``_scrape_fellowships`` purges stale pivot_grants.json/pivot_conferences.json
        # from the real ``data/pivot/`` directory as a side effect of a successful
        # scrape; stubbed out so these tests never touch the filesystem regardless
        # of what happens to be sitting on the machine running them.
        purge_patcher = mock.patch.object(manual_all, "_purge_stale_pivot_json")
        purge_patcher.start()
        self.addCleanup(purge_patcher.stop)

    def _kinds(self) -> list[str]:
        return [kind for kind, _title, _kw in self.calls]

    def test_missing_uv_skips_the_fellowship_scrape_but_not_the_collector(self) -> None:
        """No ``uv`` on PATH only takes out the host half of stage 1."""
        with (
            mock.patch.object(manual_all, "have_uv", return_value=False),
            mock.patch.object(manual_all, "run_manage", return_value=0),
        ):
            ran = manual_all.scrape_opportunities(_BASE)
        # The in-container collector still succeeded, so the combined result
        # is True — one missing host tool must never blank the whole stage.
        self.assertTrue(ran)
        self.assertEqual(self._kinds(), ["warn"])

    def test_a_failed_fellowship_scrape_reports_an_actionable_warning(self) -> None:
        with (
            mock.patch.object(manual_all, "have_uv", return_value=True),
            mock.patch.object(manual_all, "run_host", return_value=1),
            mock.patch.object(manual_all, "run_manage", return_value=0),
        ):
            ran = manual_all.scrape_opportunities(_BASE)
        self.assertTrue(ran)  # the collector half still succeeded
        self.assertIn("warn", self._kinds())
        warning = next(c for c in self.calls if c[0] == "warn")
        self.assertEqual(warning[2].get("stage"), "scrape")

    def test_a_failed_collector_run_reports_an_actionable_error(self) -> None:
        with (
            mock.patch.object(manual_all, "have_uv", return_value=True),
            mock.patch.object(manual_all, "run_host", return_value=0),
            mock.patch.object(manual_all, "run_manage", return_value=1),
        ):
            ran = manual_all.scrape_opportunities(_BASE)
        # The fellowship half still succeeded, so the combined result is
        # True — exactly the "non-fatal" contract: one bad source never
        # blanks the whole stage.
        self.assertTrue(ran)
        self.assertIn("error", self._kinds())
        error = next(c for c in self.calls if c[0] == "error")
        self.assertIn("logs", error[2].get("action", "").lower())
        self.assertEqual(error[2].get("stage"), "scrape")

    def test_both_halves_failing_reports_both_and_returns_false(self) -> None:
        with (
            mock.patch.object(manual_all, "have_uv", return_value=True),
            mock.patch.object(manual_all, "run_host", return_value=1),
            mock.patch.object(manual_all, "run_manage", return_value=1),
        ):
            ran = manual_all.scrape_opportunities(_BASE)
        self.assertFalse(ran)
        self.assertEqual(set(self._kinds()), {"warn", "error"})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
