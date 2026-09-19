"""Point Django at the sandbox database, and prove it did, before anything runs.

The harness writes hundreds of fake people. That must never reach the
development database, and nothing it saves may queue a Celery task — the live
worker would receive sandbox ids and act on them against the real database. So:
the database name is rewritten before Django reads its settings, both knowledge
hooks are switched off in the environment, and :func:`assert_sandboxed` checks
all of it after setup and stops the run if any of it did not take.
"""

from __future__ import annotations

import os
import re

#: ``SANDBOX_DB`` may name a copy (``mycelium_sandbox_<tag>``) so that two
#: experiments can run side by side, each on its own database.
SANDBOX_DB = os.environ.get("SANDBOX_DB", "mycelium_sandbox")
if not re.fullmatch(r"mycelium_sandbox(_[a-z0-9]+)?", SANDBOX_DB):
    raise RuntimeError(f"SANDBOX_DB must be mycelium_sandbox[_tag], not {SANDBOX_DB!r}")

#: Environment the harness forces, whatever the deployment says.
FORCED = {
    "KNOWLEDGE_PROJECT_ON_SAVE": "false",
    "KNOWLEDGE_FACET_ON_IMPORT": "false",
    "AMBIENT_ENABLED": "false",
}


class NotSandboxed(RuntimeError):
    """The harness is not pointed where it must be; nothing was written."""


def sandbox_url(url: str) -> str:
    """The same server and credentials, the sandbox database."""
    if not re.search(r"/[^/?]+(\?.*)?$", url or ""):
        raise NotSandboxed(f"cannot read a database name from {url!r}")
    return re.sub(r"/[^/?]+(\?.*)?$", lambda m: f"/{SANDBOX_DB}{m.group(1) or ''}", url)


def prepare() -> None:
    """Rewrite the environment. Call before ``django.setup()``."""
    os.environ["DATABASE_URL"] = sandbox_url(os.environ.get("DATABASE_URL", ""))
    os.environ.update(FORCED)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


def assert_sandboxed() -> None:
    """Stop unless Django really is on the sandbox database with hooks off."""
    from django.conf import settings
    from django.db import connection

    name = connection.settings_dict.get("NAME", "")
    if name != SANDBOX_DB:
        raise NotSandboxed(f"connected to {name!r}, not {SANDBOX_DB!r}")
    for flag in ("KNOWLEDGE_PROJECT_ON_SAVE", "KNOWLEDGE_FACET_ON_IMPORT"):
        if getattr(settings, flag):
            raise NotSandboxed(f"{flag} is on; a save would queue a live task")


def setup() -> None:
    prepare()
    import django

    django.setup()
    assert_sandboxed()
