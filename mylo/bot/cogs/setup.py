"""``/setup`` — the interactive, after-activation channel picker.

Renders an ephemeral menu with two independent, optional channels:

* **Deadline announcements** — where the lab's deadline reminders post.
* **Daily/weekly updates** — where recurring lab updates post.

Each is a native channel picker (so no channel enumeration is needed) plus a
**Turn off** button (opt-out). Selecting a channel proves postability by posting a
real confirmation there before binding (the gateway has no ``app_permissions`` to
read overwrites from). Nothing is mandatory; a lab can leave either — or both — off.

Authority: the server must already be activated (``/activate-lab``) and the caller a
**linked** lab admin/PI — config actions still terminate in ``user_can_manage_lab``.
All policy + ORM work lives in :mod:`mylo.linking`; this cog is the adapter.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ... import linking


def _render_status(state: dict) -> str:
    lab = state.get("lab_name") or "this lab"
    dead = state.get("deadlines_channel_id") or ""
    upd = state.get("updates_channel_id") or ""
    dead_line = f"<#{dead}>" if dead else "_off_"
    upd_line = f"<#{upd}>" if upd else "_off_"
    return (
        f"**Mylo setup for {lab}**\n"
        "Both channels are optional — pick one below, or turn a category off.\n"
        f"• **Deadline announcements:** {dead_line}\n"
        f"• **Daily/weekly updates:** {upd_line}"
    )


_TEXT_CHANNELS = [discord.ChannelType.text, discord.ChannelType.news]


class SetupView(discord.ui.View):
    """Ephemeral, owner-scoped menu. Times out after 3 minutes of inactivity."""

    def __init__(self, user_id: int, guild_id: str, state: dict) -> None:
        super().__init__(timeout=180)
        self.user_id = user_id
        self.guild_id = guild_id
        self.state = state
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This setup menu isn't yours — run `/setup` to open your own.",
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True  # type: ignore[attr-defined]
        if self.message is not None:
            try:
                await self.message.edit(
                    content=_render_status(self.state)
                    + "\n\n_Menu closed — run `/setup` again to make more changes._",
                    view=self,
                )
            except discord.HTTPException:
                pass

    async def _apply(
        self, interaction: discord.Interaction, *, kind: str, channel_id: str
    ) -> None:
        # Defer silently (component ack); the preflight can exceed 3s.
        await interaction.response.defer()
        status, payload = await linking.bind_setup_channel(
            str(self.user_id), self.guild_id, kind=kind, channel_id=channel_id
        )
        if status in ("ok", "cleared"):
            self.state = {
                "lab_name": payload.get("lab_name", self.state.get("lab_name", "")),
                "deadlines_channel_id": payload.get("deadlines_channel_id", ""),
                "updates_channel_id": payload.get("updates_channel_id", ""),
            }
        note = payload.get("message", "")
        await interaction.edit_original_response(
            content=f"{_render_status(self.state)}\n\n{note}", view=self
        )

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=_TEXT_CHANNELS,
        placeholder="Deadline announcements channel…",
        min_values=1,
        max_values=1,
        row=0,
    )
    async def deadlines_select(
        self, interaction: discord.Interaction, select: discord.ui.ChannelSelect
    ) -> None:
        await self._apply(
            interaction, kind="deadlines", channel_id=str(select.values[0].id)
        )

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=_TEXT_CHANNELS,
        placeholder="Daily/weekly updates channel…",
        min_values=1,
        max_values=1,
        row=1,
    )
    async def updates_select(
        self, interaction: discord.Interaction, select: discord.ui.ChannelSelect
    ) -> None:
        await self._apply(
            interaction, kind="updates", channel_id=str(select.values[0].id)
        )

    @discord.ui.button(
        label="Turn off deadline announcements",
        style=discord.ButtonStyle.secondary,
        row=2,
    )
    async def clear_deadlines(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._apply(interaction, kind="deadlines", channel_id="")

    @discord.ui.button(
        label="Turn off updates", style=discord.ButtonStyle.secondary, row=2
    )
    async def clear_updates(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._apply(interaction, kind="updates", channel_id="")


class SetupCog(commands.Cog, name="Setup"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="setup",
        description="Choose where this server's lab reminders and updates post.",
    )
    @app_commands.guild_only()
    async def setup(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        status, payload = await linking.setup_state(
            str(interaction.user.id),
            str(interaction.guild_id) if interaction.guild_id else "",
        )
        if status != "ok":
            await interaction.followup.send(payload["message"], ephemeral=True)
            return
        view = SetupView(interaction.user.id, str(interaction.guild_id), payload)
        message = await interaction.followup.send(
            _render_status(payload), view=view, ephemeral=True, wait=True
        )
        view.message = message


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SetupCog(bot))
