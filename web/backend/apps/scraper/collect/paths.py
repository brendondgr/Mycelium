"""Where the collector keeps its data, decided once.

The collector was vendored from a standalone CLI where every default path was
relative to the working directory. That is the right default for a tool you run
from your project directory and the wrong one inside Django, where there is no
single working directory: the nightly runs in the backend container at ``/app``
(compose ``working_dir``), while a host operator may run ``manage.py`` from the
repository root or from ``web/backend``.

A relative default does not merely point somewhere unexpected -- it points
somewhere *empty*, and every consumer here treats "empty" as "first run":

* a missing store means no record has ever been seen, so the run re-fetches
  every venue page across ~1,500 third-party hosts and re-bills the model for
  the whole corpus;
* a missing extraction checkpoint means no verdict has ever been settled, so an
  interrupted backfill starts over;
* and both then report a completely ordinary success.

Deriving from ``__file__`` makes the answer a property of the checkout instead,
identical in the container and on the host. This module deliberately imports
nothing but :mod:`pathlib`, so anything in ``collect/`` can import it without
risking a cycle.
"""

from __future__ import annotations

from pathlib import Path

#: The repository root. ``collect/ -> scraper/ -> apps/ -> backend/ -> web/``
#: and one more to clear ``web/`` -- the same technique ``config.settings`` uses
#: to derive ``BASE_DIR``.
REPO_ROOT = Path(__file__).resolve().parents[5]

#: Everything the collector persists: the two SQLite stores, the HTTP cache of
#: fetched venue pages, the per-run raw payloads ``--skip-fetch`` replays, and
#: the extraction checkpoint. Gitignored (``data/collect/``) and regenerable,
#: but expensive to regenerate, which is the entire point of pinning it.
DEFAULT_ROOT = REPO_ROOT / "data" / "collect"
