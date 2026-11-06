"""Test helpers that put a user or lab on the paid side of the reminder gate.

Reminders require a paid plan **and** synced Discord (see
:mod:`apps.content.reminder_access`), enforced both when a subscription is created
and again when Mylo tries to deliver it. Every reminder test that is about something
*else* — mention escaping, outbox retries, tick sealing — therefore needs its actors
entitled, or it would be asserting the gate instead of its own subject.

These are deliberately the real objects (a ``Subscription`` row, a
``DiscordIdentity``, a server binding) rather than a monkeypatched access
function, so a test proving "the DM went out" still proves the whole path.

Not named ``test_*`` so pytest treats this as a helper module, not a suite.
"""

from __future__ import annotations

from apps.billing.models import Subscription, Tier
from apps.integrations.models import DiscordIdentity, DiscordTargetBinding
from apps.integrations.testing import bind

_next_snowflake = iter(range(700_000_000, 700_999_999))


def paid_plan(user, tier: str = Tier.SPORE) -> Subscription:
    """Give ``user`` their own active paid subscription."""
    return Subscription.objects.create(tier=tier, scope_user=user)


def link_discord(user, *, discord_user_id: str = "", dm_ok: bool = True):
    """Give ``user`` an ACTIVE Discord identity (idempotent per user)."""
    existing = DiscordIdentity.objects.filter(user=user).first()
    if existing is not None:
        return existing
    return DiscordIdentity.objects.create(
        user=user,
        discord_user_id=discord_user_id or str(next(_next_snowflake)),
        link_method=DiscordIdentity.LinkMethod.OAUTH,
        state=DiscordIdentity.State.ACTIVE,
        dm_ok=dm_ok,
    )


def entitle_user(user, *, tier: str = Tier.SPORE, discord_user_id: str = ""):
    """Satisfy both halves of the personal reminder gate for ``user``."""
    paid_plan(user, tier)
    link_discord(user, discord_user_id=discord_user_id)
    return user


def entitle_lab(lab, *, tier: str = Tier.LAB, guild_id: str = "", channel: str = ""):
    """Satisfy both halves of the lab reminder gate: a paid plan + a live guild link.

    Reuses an existing binding when the test already made one (the usual case —
    lab tests bind a channel themselves), only promoting it to ACTIVE.
    """
    Subscription.objects.create(
        tier=tier, scope_lab=lab, status=Subscription.Status.ACTIVE
    )
    binding = DiscordTargetBinding.objects.filter(lab=lab).first()
    if binding is None:
        bind(lab=lab, guild_id=guild_id, deadlines=channel)
    else:
        bind(lab=lab, guild_id=binding.guild.guild_id)
    return lab
