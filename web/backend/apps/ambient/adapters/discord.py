"""The Discord adapter — the first platform, and deliberately not the design.

It does exactly what the contract in :mod:`.base` allows: it turns a snowflake
into a Mycelium user through the one identity boundary
(``integrations.services.resolve``), and it names which
:class:`~apps.ambient.models.Source` kind a guild is. Everything else — whether
the message is worth keeping, whether this person may be listened to at all,
what the message means — happens elsewhere, on purpose.

A snowflake with no ACTIVE identity resolves to ``None``. That is the ordinary
case for most people in a server, and it is the whole of what happens to them:
nothing is recorded, and nothing is counted against their name.
"""

from __future__ import annotations

from django.contrib.auth.models import User

from ..models import Platform, Source
from .base import Adapter


class DiscordAdapter(Adapter):
    """Guild conversation. DMs use :class:`DiscordDirectMessageAdapter`."""

    platform = Platform.DISCORD
    source_kind = Source.Kind.DISCORD_GUILD

    def resolve_speaker(self, author_external_id: str) -> User | None:
        # Imported here rather than at module scope so the ambient app does not
        # pull the integrations service graph in at import time.
        from apps.integrations.services import resolve

        return resolve.resolve_user(str(author_external_id))


class DiscordDirectMessageAdapter(DiscordAdapter):
    """A conversation with Mylo itself.

    A DM's surface is the person, not a server, so the source is keyed on the
    speaker's snowflake and belongs to no lab. Everything a DM produces is
    ``personal`` — which is why it must never be a guild source with the lab
    attached.
    """

    source_kind = Source.Kind.DISCORD_DM
