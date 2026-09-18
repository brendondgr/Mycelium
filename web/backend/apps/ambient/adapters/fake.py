"""A fake adapter, for tests and for exercising the ledger without a platform.

It exists for the same reason the interface does: so the contract can be
verified before Discord is written against it, and so a later platform has
something to copy that is not Discord-shaped.

It is not registered by default — a test registers it when it wants it, so the
registry of a running deployment only ever holds real platforms.
"""

from __future__ import annotations

from django.contrib.auth.models import User

from ..models import Platform, Source
from .base import Adapter


class FakeAdapter(Adapter):
    """An adapter whose identity map is a dict you hand it.

    ``identities`` maps a platform id to a Mycelium user. An id that is not in
    it resolves to None, which is exactly what an unlinked server member looks
    like to a real adapter.
    """

    platform = Platform.DISCORD
    source_kind = Source.Kind.DISCORD_GUILD

    def __init__(self, identities: dict[str, User] | None = None):
        self.identities = dict(identities or {})

    def link(self, author_external_id: str, user: User) -> None:
        self.identities[author_external_id] = user

    def resolve_speaker(self, author_external_id: str) -> User | None:
        return self.identities.get(author_external_id)
