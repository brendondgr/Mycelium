"""The collector's data root is a property of the repository, not of the shell.

``DEFAULT_ROOT`` used to be ``Path("data/collect")``, which was correct when the
collector was a standalone CLI and wrong the moment it moved inside Django. The
nightly runs in the backend container whose compose ``working_dir`` is ``/app``;
a host operator runs ``manage.py`` from the repository root or from
``web/backend``. Each of those resolves a relative default to a *different*
directory.

What makes that worth a test rather than a comment is the failure mode. A
missing store is not an error -- ``ConferenceStore`` creates it -- so the run
does not fail. It finds an empty store, concludes every record is new, re-fetches
every venue page from ~1,500 third-party hosts, re-bills the model for the entire
corpus, and reports success. It also floods every reader's report with thousands
of "new" items that are not new. That is expensive, rude to those hosts, and
invisible, which is the worst combination available.

This is the same class of bug as ``test_collect_empty_run_guard`` covers from the
other side: there, nothing collected; here, nothing *remembered*.
"""

from __future__ import annotations

import os
from pathlib import Path

from apps.scraper.collect.runner import DEFAULT_ROOT


def test_the_default_root_is_absolute():
    """The whole point: no CWD can change where the corpus lives."""
    assert DEFAULT_ROOT.is_absolute(), (
        f"DEFAULT_ROOT is {DEFAULT_ROOT!r}, which is relative -- the nightly "
        "(cwd /app) and a host shell (cwd web/backend) would use two different "
        "stores, and the empty one re-collects everything while reporting success."
    )


def test_the_default_root_does_not_move_with_the_working_directory(tmp_path):
    """Resolved at import from ``__file__``, so chdir cannot move it."""
    from apps.scraper.collect import runner

    before = runner.DEFAULT_ROOT
    cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        assert runner.DEFAULT_ROOT == before
    finally:
        os.chdir(cwd)


def test_the_default_root_sits_at_the_repository_root():
    """``<repo>/data/collect`` -- what the container's ``/app`` resolves to.

    Pinned against the repository layout rather than a hardcoded string so
    that moving the app inside the tree fails here rather than in production.
    """
    # tests/ -> scraper/ -> apps/ -> backend/ -> web/ -> the repository root.
    repo_root = Path(__file__).resolve().parents[5]
    assert DEFAULT_ROOT == repo_root / "data" / "collect"
    # The sibling that proves we walked far enough up: web/ is a directory of
    # the repository root, not of web/backend.
    assert (repo_root / "web" / "backend" / "manage.py").exists()
