"""Bridge from the Mylo gateway process into Mycelium's Django ORM.

The plan's constraint is "Mylo owns no data": every Discord-originated database
touch goes through ``apps.integrations.services.resolve``. The gateway runs in the
root env (which mirrors the backend's runtime deps — see the root ``pyproject.toml``),
so it can configure Django in-process and call ``resolve`` directly, sharing one
database, one schema, one migration history. No second database, no HTTP hop.

``db(fn, ...)`` runs a synchronous ORM call off the event loop via ``sync_to_async``
so the async bot never blocks on the database. Import ``resolve`` *inside* the
callable you pass, so it is imported only after Django is configured.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_READY = False


def setup_django() -> None:
    """Configure Django once for this process (idempotent)."""
    global _READY
    if _READY:
        return
    backend = Path(__file__).resolve().parent.parent / "web" / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    _READY = True


async def db(fn, /, *args, **kwargs):
    """Run a synchronous ORM callable off the event loop, Django configured."""
    setup_django()
    from asgiref.sync import sync_to_async

    return await sync_to_async(fn, thread_sensitive=True)(*args, **kwargs)


def portal_url() -> str:
    """The portal profile URL to point users at (from Django settings)."""
    setup_django()
    from django.conf import settings

    return getattr(settings, "DISCORD_PORTAL_RETURN_URL", "the Mycelium portal")


def activation_channel_id() -> str:
    setup_django()
    from django.conf import settings

    return str(getattr(settings, "DISCORD_ACTIVATION_CHANNEL_ID", "") or "")
