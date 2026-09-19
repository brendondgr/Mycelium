"""Which Mycelium user a Slack user is — the one identity boundary for Slack.

The same rule as :mod:`.resolve` for Discord: an ACTIVE identity resolves, and
nothing else does. Most people in a workspace have no Mycelium account, and
``None`` is the whole of what happens to them.
"""

from __future__ import annotations

from django.contrib.auth.models import User

from ..models import SlackIdentity


def resolve_user(team_id: str, slack_user_id: str) -> User | None:
    identity = (
        SlackIdentity.objects.filter(
            team_id=str(team_id),
            slack_user_id=str(slack_user_id),
            state=SlackIdentity.State.ACTIVE,
        )
        .select_related("user")
        .first()
    )
    if identity is None or not identity.user.is_active:
        return None
    return identity.user


def identity_for(user) -> SlackIdentity | None:
    """A person's active Slack identity (the most recent, if several)."""
    return (
        SlackIdentity.objects.filter(user=user, state=SlackIdentity.State.ACTIVE)
        .order_by("-linked_at")
        .first()
    )


def unlink(user, team_id: str) -> int:
    from django.utils import timezone

    return SlackIdentity.objects.filter(
        user=user, team_id=str(team_id), state=SlackIdentity.State.ACTIVE
    ).update(state=SlackIdentity.State.REVOKED, revoked_at=timezone.now())
