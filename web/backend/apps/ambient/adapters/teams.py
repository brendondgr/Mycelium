"""The Teams adapter (Plan 11) — the Bot Framework's activities, translated.

A person is their Azure AD object id — a GUID, unique in practice across
tenants, and short enough for the ledger's 64-character speaker key (tenant
and object id together are not) — resolved only through
``integrations.services.teams_resolve``, which refuses if two active
identities ever shared one. A team's channels are one source; a
person's personal chat with Mylo is another, and personal.
"""

from __future__ import annotations

from django.contrib.auth.models import User

from ..models import Platform, Source
from .base import Adapter


def person_key(tenant_id: str, aad_object_id: str) -> str:
    return str(aad_object_id)


class TeamsAdapter(Adapter):
    platform = Platform.TEAMS
    source_kind = Source.Kind.TEAMS_TEAM

    def resolve_speaker(self, author_external_id: str) -> User | None:
        from apps.integrations.services import teams_resolve

        if not author_external_id:
            return None
        return teams_resolve.resolve_by_object_id(str(author_external_id))


class TeamsChatAdapter(TeamsAdapter):
    """A person's personal chat with Mylo: personal, no lab."""

    source_kind = Source.Kind.TEAMS_CHAT
