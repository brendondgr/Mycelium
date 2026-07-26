"""Nightly reconciliation sweep — the HTTP-only tradeoff.

Without a gateway ``GUILD_DELETE``/deauthorize event, we reconcile state on a
schedule instead:

* Guild presence: ask the bot which guilds it is in; any non-KICKED
  ``DiscordGuildLink`` whose guild is absent → KICKED. Guarded: if the guild-list
  call fails we skip the sweep entirely rather than mark everyone kicked on a blip.
* Token health: OAuth identities with soon-expiring tokens are refreshed;
  ``invalid_grant`` (the user deauthorized us) → REVOKED.

Reports the delta to ERROR_CHANNEL (informational).
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from . import discord_api, errors, oauth, resolve

# Refresh tokens that will lapse within this window.
_REFRESH_HORIZON = timedelta(days=2)


def reconcile() -> dict:
    summary = {"kicked": 0, "refreshed": 0, "revoked": 0, "guild_sweep": "ok"}

    # --- Guild presence -------------------------------------------------- #
    try:
        present = {str(g.get("id")) for g in discord_api.get_bot_guilds()}
    except discord_api.DiscordHTTPError as exc:
        summary["guild_sweep"] = "skipped"
        errors.note_incident(
            "reconcile", exc.status or "guilds", detail="could not list bot guilds"
        )
        present = None

    if present is not None:
        for guild_id in resolve.active_guild_ids():
            if guild_id not in present:
                resolve.mark_guild_kicked(guild_id)
                summary["kicked"] += 1

    # --- Token health ---------------------------------------------------- #
    horizon = timezone.now() + _REFRESH_HORIZON
    for identity in resolve.identities_with_tokens_expiring_before(horizon):
        if not identity.refresh_token:
            continue
        try:
            ok = oauth.refresh_identity(identity)
        except discord_api.DiscordHTTPError:
            continue  # transient; try again next sweep
        if ok:
            summary["refreshed"] += 1
        else:
            summary["revoked"] += 1

    # --- Channel liveness + entitlement ----------------------------------- #
    # Events are lost across restarts, deploys and gateway disconnects, so this
    # sweep is the safety net rather than the optimisation. It re-verifies what
    # `/setup` proved once, because "it worked when we bound it" stops being true
    # the moment someone deletes a channel or edits its permissions.
    summary.update(_reconcile_guild_health())

    if summary["kicked"] or summary["refreshed"] or summary["revoked"]:
        errors.post_embed(
            "Discord reconciliation",
            (
                f"kicked={summary['kicked']} refreshed={summary['refreshed']} "
                f"revoked={summary['revoked']} guild_sweep={summary['guild_sweep']}"
            ),
            severity="info",
        )
    return summary


def _reconcile_guild_health() -> dict:
    """Re-verify each active link's channels and its lab's Mylo add-on.

    Channel existence is checked with the guild's channel list rather than by
    posting: ``preflight_channel`` proves postability by sending a real message,
    which is right at bind time (an admin is watching and wants proof) and wrong
    nightly (it would spam every lab's channel). Existence catches the common case —
    a deleted channel — without that cost.

    The add-on check is the hole the brief named: it was verified once, when the bot
    was first added, and never again. A lab that stopped paying kept receiving
    delivery indefinitely.
    """
    from apps.billing.entitlements import Feature, lab_has_feature

    summary = {"channels_checked": 0, "channels_lost": 0, "addons_lapsed": 0}
    for link in resolve.active_guild_links():
        bound = {
            "deadlines": link.announcement_channel_id,
            "updates": link.updates_channel_id,
        }
        if any(bound.values()):
            try:
                channels = discord_api.get_guild_channels(link.guild_id)
                present = {str(c.get("id")) for c in channels}
            except discord_api.DiscordHTTPError:
                # Same guard as the guild sweep: a blip must not mark every lab's
                # channels dead. Leave the last known state and try again tomorrow.
                present = None
            if present is not None:
                for kind, channel_id in bound.items():
                    if not channel_id:
                        continue
                    summary["channels_checked"] += 1
                    alive = channel_id in present
                    resolve.set_channel_health(
                        link.guild_id, kind=kind, ok=alive
                    )
                    if not alive:
                        summary["channels_lost"] += 1

        entitled = lab_has_feature(link.lab, Feature.BOT_SERVER)
        if link.addon_ok is not entitled:
            resolve.set_addon_ok(link.lab, ok=entitled)
            if not entitled:
                summary["addons_lapsed"] += 1
    return summary
