"""Opportunity announcement buttons: ``ann:<post>:<action>``.

The buttons live on threads Mylo posted (and on the details DM), so they must
work after a restart: they are handled by an ``on_interaction`` listener keyed on
the custom id rather than by a view object. Every press is answered ephemerally,
and every decision is the backend's (:mod:`mylo.linking` →
``tools.delivery.announcement_actions``, which starts at the authorization gate).

* **Interested** → a reply only the presser sees; the details go by DM.
* **Remind me** → a picker only the presser sees (several times, DM or thread).
* **Not for us** → a short form asking why (managers only; the backend checks).
* **Stop following** (DM) → done.
* **Stop reminding me** (a reminder DM) → done; works without a Mycelium account,
  like **Remind me** itself.
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from ... import linking

log = logging.getLogger(__name__)


class RemindPicker(discord.ui.View):
    """The ephemeral Remind-me picker."""

    def __init__(self, user_id: int, post_id: str, guild_id: str, options: list[dict]):
        super().__init__(timeout=300)
        self.user_id, self.post_id, self.guild_id = user_id, post_id, guild_id
        self.when = discord.ui.Select(
            placeholder="How far ahead?",
            min_values=1,
            max_values=min(5, len(options)),
            options=[
                discord.SelectOption(
                    label=o["label"][:100], value=o["value"], default=o["default"]
                )
                for o in options
            ],
            row=0,
        )
        self.where = discord.ui.Select(
            placeholder="Where?",
            options=[
                discord.SelectOption(
                    label="DM me", value="dm", emoji="✉️", default=True
                ),
                discord.SelectOption(
                    label="Tag me in the thread", value="thread", emoji="🧵"
                ),
            ],
            row=1,
        )
        for select in (self.when, self.where):
            select.callback = self._noop  # type: ignore[method-assign]
            self.add_item(select)

    async def _noop(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()

    @discord.ui.button(label="Set reminder", style=discord.ButtonStyle.primary, row=2)
    async def confirm(self, interaction: discord.Interaction, _b: discord.ui.Button):
        offsets = list(self.when.values) or [
            o.value for o in self.when.options if o.default
        ]
        where = (self.where.values or ["dm"])[0]
        await interaction.response.defer()
        _status, payload = await linking.announcement_action(
            str(self.user_id),
            self.post_id,
            "remind_set",
            guild_id=self.guild_id,
            offsets=offsets,
            where=where,
        )
        await interaction.edit_original_response(content=payload["message"], view=None)


class NotForUsForm(discord.ui.Modal, title="Not for us"):
    reason = discord.ui.TextInput(
        label="Why not? (kept so Mylo chooses better)",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500,
    )

    def __init__(self, post_id: str, guild_id: str) -> None:
        super().__init__()
        self.post_id, self.guild_id = post_id, guild_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        _status, payload = await linking.announcement_action(
            str(interaction.user.id),
            self.post_id,
            "notforus",
            guild_id=self.guild_id,
            reason=str(self.reason.value or ""),
        )
        await interaction.followup.send(payload["message"], ephemeral=True)


class AnnouncementsCog(commands.Cog, name="Announcements"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        try:
            if interaction.type != discord.InteractionType.component:
                return
            custom_id = str((interaction.data or {}).get("custom_id") or "")
            if custom_id.startswith("annx:"):
                await self._manual(interaction, custom_id)
                return
            if not custom_id.startswith("ann:"):
                return
            _, post_id, action = custom_id.split(":", 2)
            guild_id = str(interaction.guild_id or "")
            if action == "notforus":
                await interaction.response.send_modal(NotForUsForm(post_id, guild_id))
                return
            await interaction.response.defer(ephemeral=True, thinking=True)
            status, payload = await linking.announcement_action(
                str(interaction.user.id), post_id, action, guild_id=guild_id
            )
            if action == "remind" and status == "ok":
                view = RemindPicker(
                    interaction.user.id, post_id, guild_id, payload["options"]
                )
                await interaction.followup.send(
                    payload["message"], view=view, ephemeral=True
                )
                return
            await interaction.followup.send(payload["message"], ephemeral=True)
        except Exception:  # noqa: BLE001 — a listener never kills the gateway
            log.exception("could not handle an announcement button")


    async def _manual(self, interaction: discord.Interaction, custom_id: str) -> None:
        """"Announce to #…" from a search result: post once, then drop the button."""
        _, binding_id, content_id = custom_id.split(":", 2)
        # A deferred *update*: the original response stays the search message, so
        # the pressed button can be removed from it below.
        await interaction.response.defer()
        _status, payload = await linking.announcement_manual(
            str(interaction.user.id),
            str(interaction.guild_id or ""),
            binding_id,
            content_id,
        )
        await interaction.followup.send(payload["message"], ephemeral=True)
        message = getattr(interaction, "message", None)
        if message is None:
            return
        try:
            view = discord.ui.View.from_message(message)
            for item in list(view.children):
                if getattr(item, "custom_id", None) == custom_id:
                    view.remove_item(item)
            await interaction.edit_original_response(view=view)
        except (discord.HTTPException, ValueError):
            pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AnnouncementsCog(bot))
