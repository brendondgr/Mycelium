"""``manual_all.py``'s weekly dblp registry refresh and scrape-directory tidy-up.

Both are reachable without a live stack: ``refresh_conference_registry`` only
reads a file's mtime and calls the (stubbed) ``run_manage``, and
``_tidy_scrape_dir`` only touches directories of plain JSON files — neither
needs Docker, Postgres, or a running backend. ``test_daily_run_reporting.py``
stubs ``_tidy_scrape_dir`` out entirely, which leaves it unexercised anywhere
else in the suite. These tests run it for real, against temp directories
substituted for the real ones so nothing on the machine running the suite is
ever at risk.

    uv run python -m unittest discover -s mylo -p 'test_*.py'
"""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import manual_all

#: A stand-in for the Compose base command (``ensure_ready()``'s return
#: value). Never actually invoked -- every test below stubs ``run_manage``.
_BASE = ["docker", "compose"]


class TidyScrapeDirTests(unittest.TestCase):
    """``_tidy_scrape_dir`` — housekeeping, not a correctness guard: a one-off
    rename of the old directory, and deleting exactly the named stale files."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        root = Path(self._tmpdir.name)
        self.current = root / "fellowships"
        self.legacy = root / "legacy"
        for name, value in (
            ("FELLOWSHIPS_DIR", self.current),
            ("LEGACY_SCRAPE_DIR", self.legacy),
        ):
            patcher = mock.patch.object(manual_all, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_moves_the_old_directory_once(self) -> None:
        self.legacy.mkdir()
        (self.legacy / "keep.txt").write_text("x")

        manual_all._tidy_scrape_dir()

        self.assertFalse(self.legacy.exists())
        self.assertEqual((self.current / "keep.txt").read_text(), "x")

    def test_removes_the_stale_files_and_keeps_the_live_one(self) -> None:
        self.current.mkdir()
        for stale in manual_all.STALE_SCRAPE_FILES:
            (self.current / stale).write_text("[]")
        live = self.current / "fellowships.json"
        live.write_text('{"fellowships": []}')

        manual_all._tidy_scrape_dir()

        for stale in manual_all.STALE_SCRAPE_FILES:
            self.assertFalse((self.current / stale).exists())
        self.assertEqual(live.read_text(), '{"fellowships": []}')

    def test_is_a_no_op_when_nothing_is_there(self) -> None:
        manual_all._tidy_scrape_dir()
        self.assertFalse(self.current.exists())
        self.assertFalse(self.legacy.exists())


class RefreshConferenceRegistryTests(unittest.TestCase):
    """``refresh_conference_registry`` — the plain file-mtime self-throttle
    (plan D5a: "weekly is ample") ahead of the actual command."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.cache_path = Path(self._tmpdir.name) / "dblp_venues.json"
        cache_patcher = mock.patch.object(
            manual_all, "REGISTRY_CACHE_PATH", self.cache_path
        )
        cache_patcher.start()
        self.addCleanup(cache_patcher.stop)

        self.calls: list[tuple[str, str]] = []
        notify_patcher = mock.patch.object(
            manual_all,
            "_notify",
            lambda kind, title, body="", **kw: self.calls.append((kind, title)),
        )
        notify_patcher.start()
        self.addCleanup(notify_patcher.stop)

    def _age_cache(self, days: float) -> None:
        self.cache_path.write_text("{}")
        stamp = time.time() - days * 86400
        os.utime(self.cache_path, (stamp, stamp))

    def test_missing_cache_triggers_a_refresh(self) -> None:
        """Never fetched (or unreadable) reads as ``age_days = None`` in the
        real function, which is treated as due -- see its own ``except
        OSError`` comment."""
        self.assertFalse(self.cache_path.exists())
        with mock.patch.object(manual_all, "run_manage", return_value=0) as rm:
            manual_all.refresh_conference_registry(_BASE)
        rm.assert_called_once_with("refresh_dblp_registry", [], intro=None, base=_BASE)

    def test_a_fresh_cache_skips_the_refresh(self) -> None:
        """Plan D5a: venue longevity does not move night to night, so a
        cache younger than ``REGISTRY_REFRESH_INTERVAL_DAYS`` must not pay
        for another ~8 MB SPARQL POST -- ``run_manage`` is never called."""
        self._age_cache(1)
        with mock.patch.object(manual_all, "run_manage") as rm:
            manual_all.refresh_conference_registry(_BASE)
        rm.assert_not_called()
        self.assertEqual(self.calls, [])  # nothing worth reporting either

    def test_a_stale_cache_triggers_a_refresh(self) -> None:
        self._age_cache(manual_all.REGISTRY_REFRESH_INTERVAL_DAYS + 1)
        with mock.patch.object(manual_all, "run_manage", return_value=0) as rm:
            manual_all.refresh_conference_registry(_BASE)
        rm.assert_called_once_with("refresh_dblp_registry", [], intro=None, base=_BASE)

    def test_a_failed_refresh_warns_but_never_raises(self) -> None:
        """'Never fatal to the run either way' (module docstring): a bad
        exit code from the command is reported as a warning, not an
        exception that would take the rest of ``manual_all.py``'s stages
        down with it."""
        with mock.patch.object(manual_all, "run_manage", return_value=1):
            manual_all.refresh_conference_registry(_BASE)  # must not raise
        self.assertEqual([kind for kind, _title in self.calls], ["warn"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class FacetAuthorWorksTests(unittest.TestCase):
    """The nightly knowledge step reads people's papers and never fails the run."""

    def test_it_runs_the_command_once(self) -> None:
        with mock.patch.object(manual_all, "run_manage", return_value=0) as run:
            with mock.patch.object(manual_all, "_notify") as notify:
                manual_all.facet_author_works(_BASE)
        run.assert_called_once_with("facet_author_works", [], intro=None, base=_BASE)
        notify.assert_not_called()

    def test_a_failure_is_a_warning_not_a_failed_run(self) -> None:
        with mock.patch.object(manual_all, "run_manage", return_value=3):
            with mock.patch.object(manual_all, "_notify") as notify:
                self.assertIsNone(manual_all.facet_author_works(_BASE))
        kind, title = notify.call_args.args[:2]
        self.assertEqual(kind, "warn")
        self.assertIn("papers", title)


class ExtractRequirementSlotsTests(unittest.TestCase):
    """Reading call requirements never fails the run."""

    def test_a_failure_is_a_warning(self) -> None:
        with mock.patch.object(manual_all, "run_manage", return_value=2) as run:
            with mock.patch.object(manual_all, "_notify") as notify:
                manual_all.extract_requirement_slots(_BASE)
        run.assert_called_once_with(
            "extract_requirement_slots", [], intro=None, base=_BASE
        )
        self.assertEqual(notify.call_args.args[0], "warn")
