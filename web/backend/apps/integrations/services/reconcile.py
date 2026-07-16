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
