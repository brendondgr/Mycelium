"""The Slack adapter — Plan 11's second platform, over the same contract.

A Slack user id is unique only within a workspace, so the external id the
ledger sees is ``"<team_id>:<user_id>"``, and a message id is
``"<channel_id>:<ts>"``. Resolution goes through
``integrations.services.slack_resolve`` and nothing else. As with Discord,
most people in a workspace resolve to ``None`` and nothing is recorded about
them.
"""

from __future__ import annotations

from django.contrib.auth.models import User

from ..models import Platform, Source
from .base import Adapter


def person_key(team_id: str, slack_user_id: str) -> str:
    return f"{team_id}:{slack_user_id}"


class SlackAdapter(Adapter):
    """Workspace channels the app was added to.

    DMs are :class:`SlackDirectMessageAdapter`.
    """

    platform = Platform.SLACK
    source_kind = Source.Kind.SLACK_WORKSPACE

    def resolve_speaker(self, author_external_id: str) -> User | None:
        from apps.integrations.services import slack_resolve

        team_id, _, slack_user_id = str(author_external_id).partition(":")
        if not team_id or not slack_user_id:
            return None
        return slack_resolve.resolve_user(team_id, slack_user_id)


class SlackDirectMessageAdapter(SlackAdapter):
    """A person's DMs with Mylo in one workspace: personal, no lab."""

    source_kind = Source.Kind.SLACK_DM
