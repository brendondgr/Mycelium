"""Test helpers for the server / binding / route model.

Tests used to build one ``DiscordGuildLink(lab=..., announcement_channel_id=...)``;
a server is now a guild row plus one binding per lab or department, and channels
are routes on a binding. These helpers build the same real rows the code reads, so
a test proving "the reminder posted" still proves the whole path.

Not named ``test_*`` so pytest treats it as a helper module, not a suite.
"""

from __future__ import annotations

from django.utils import timezone

from .models import DiscordChannelRoute, DiscordGuildLink, DiscordTargetBinding

_next_snowflake = iter(range(710_000_000, 710_999_999))


def bind(
    *,
    lab=None,
    department=None,
    guild_id: str = "",
    guild_name: str = "",
    state: str = DiscordTargetBinding.State.ACTIVE,
    guild_state: str | None = None,
    deadlines: str = "",
    updates: str = "",
    verified: bool = False,
    **route_health,
) -> DiscordTargetBinding:
    """A binding of ``lab`` (or ``department``) in a server, with optional routes.

    ``guild_state`` defaults to ACTIVE for an active binding and PENDING_SETUP
    otherwise, which is what activation and OAuth install leave behind.
    """
    guild_id = guild_id or str(next(_next_snowflake))
    if guild_state is None:
        guild_state = (
            DiscordGuildLink.State.ACTIVE
            if state == DiscordTargetBinding.State.ACTIVE
            else DiscordGuildLink.State.PENDING_SETUP
        )
    guild, _ = DiscordGuildLink.objects.get_or_create(
        guild_id=str(guild_id),
        defaults={"guild_name_cache": guild_name, "verified_via_code_grant": verified},
    )
    guild.state = guild_state
    guild.save(update_fields=["state"])
    binding, _ = DiscordTargetBinding.objects.get_or_create(
        guild=guild, lab=lab, department=department
    )
    binding.state = state
    if state == DiscordTargetBinding.State.ACTIVE and binding.activated_at is None:
        binding.activated_at = timezone.now()
    binding.save()
    if deadlines:
        add_route(binding, "deadlines", deadlines, ok=route_health.get("deadlines_ok"))
    if updates:
        add_route(binding, "updates", updates, ok=route_health.get("updates_ok"))
    return binding


def add_route(binding, purpose: str, channel_id: str, *, ok=None, **extra):
    route, _ = DiscordChannelRoute.objects.update_or_create(
        binding=binding,
        purpose=purpose,
        defaults={"channel_id": str(channel_id), "ok": ok, **extra},
    )
    return route


def route(binding_or_lab, purpose: str) -> DiscordChannelRoute | None:
    """The route for ``purpose`` on a binding, or on a lab's first binding."""
    if isinstance(binding_or_lab, DiscordTargetBinding):
        binding = binding_or_lab
    else:
        binding = DiscordTargetBinding.objects.filter(lab=binding_or_lab).first()
        if binding is None:
            return None
    return DiscordChannelRoute.objects.filter(binding=binding, purpose=purpose).first()


def lab_binding(lab) -> DiscordTargetBinding | None:
    return (
        DiscordTargetBinding.objects.filter(lab=lab)
        .select_related("guild")
        .order_by("activated_at", "id")
        .first()
    )
