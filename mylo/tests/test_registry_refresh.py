"""``manual_all.py``'s weekly dblp registry refresh and stale-Pivot cleanup.

Both are reachable without a live stack: ``refresh_conference_registry`` only
reads a file's mtime and calls the (stubbed) ``run_manage``, and
``_purge_stale_pivot_json`` only touches a directory of plain JSON files —
neither needs Docker, Postgres, or a running backend. ``test_daily_run_
reporting.py`` stubs ``_purge_stale_pivot_json`` out entirely (its own
comment: "stubbed out so these tests never touch the filesystem regardless
of what happens to be sitting on the machine running them"), which leaves it
completely unexercised anywhere in the suite. These tests run it for real,
against a temp directory substituted for the real ``data/pivot/`` so nothing
on the machine running the suite is ever at risk.

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


class PurgeStalePivotJsonTests(unittest.TestCase):
    """``_purge_stale_pivot_json`` — housekeeping, not a correctness guard
    (its own docstring), but it must still delete exactly the two named
    files and nothing else."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.pivot_dir = Path(self._tmpdir.name)
        patcher = mock.patch.object(manual_all, "PIVOT_DIR", self.pivot_dir)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_removes_both_stale_grant_and_conference_json(self) -> None:
        (self.pivot_dir / "pivot_grants.json").write_text("[]")
        (self.pivot_dir / "pivot_conferences.json").write_text("[]")

        manual_all._purge_stale_pivot_json()

        self.assertFalse((self.pivot_dir / "pivot_grants.json").exists())
        self.assertFalse((self.pivot_dir / "pivot_conferences.json").exists())

    def test_never_touches_the_live_fellowship_file(self) -> None:
        """Only the two named stale files are targeted -- unlike Pivot-RP's
        own ``pivot.py import``, which globbed every ``pivot_*.json`` file
        with no way to scope to one area (module docstring), this must
        leave ``pivot_fellowships.json`` -- the file ``scrape_fellowships.
        py`` still reads and writes every night -- completely untouched."""
        fellowships = self.pivot_dir / "pivot_fellowships.json"
        fellowships.write_text('{"fellowships": []}')
        (self.pivot_dir / "pivot_grants.json").write_text("[]")

        manual_all._purge_stale_pivot_json()

        self.assertTrue(fellowships.exists())
        self.assertEqual(fellowships.read_text(), '{"fellowships": []}')

    def test_is_a_no_op_when_neither_stale_file_exists(self) -> None:
        """Nothing to remove must not raise -- a host that never ran
        Pivot-RP, or already cleaned up, has no stale files to find."""
        manual_all._purge_stale_pivot_json()
        self.assertEqual(list(self.pivot_dir.iterdir()), [])


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
