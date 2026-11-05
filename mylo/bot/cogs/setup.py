"""``/setup`` — the interactive, after-activation configuration menu.

Renders an ephemeral menu with three independent, optional sections:

* **Deadline announcements** — where the lab's deadline reminders post.
* **Daily/weekly updates** — where recurring lab updates post.
* **Listening** — whether Mylo may learn from this server's conversation, and
  which channels it must never read.

Each channel is a native picker (so no channel enumeration is needed) plus a
**Turn off** button (opt-out). Selecting a channel proves postability by posting a
real confirmation there before binding (the gateway has no ``app_permissions`` to
read overwrites from). Nothing is mandatory; a lab can leave any of the three off.

Listening is the consequential one, so it says what it does in the menu itself
rather than in a policy nobody opens, and turning it on posts a visible marker
in the server saying so. Turning it *on* for the server is only the first of
three gates — each member still opts in for themselves, and their effective tier
must be paid — which is why the menu says "your members choose for themselves"
instead of implying the switch is the whole decision.

Authority: the server must already be activated (``/activate-lab`` or
``/activate-department``) and the caller a **linked** manager of the lab or
department being configured — config actions still terminate in
``apps.accounts.permissions``. A server can hold several labs and a department; when
it does, `/setup` first asks which one, and each is configured on its own.
All policy + ORM work lives in :mod:`mylo.linking` and :mod:`mylo.listening`; this
cog is the adapter.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ... import linking, listening


#: Posted in the updates channel when listening is turned on, and edited rather
#: than re-posted when the settings change. The whole feature rests on people
#: knowing, so this is not optional (OD-02b).
MARKER = (
    "**Mylo is listening in this server.**\n"
    "I read what is said here so I can keep each member's research profile and "
    "project notes up to date without anyone filling in a form.\n\n"
    "**Nobody is included unless they choose to be.** Listening is off for every "
    "person until they run `/mylo listening on`, and it needs a linked Mycelium "
    "account on a paid plan. If you have not opted in, your messages are dropped "
    "and nothing about you is recorded.\n\n"
    "**I do not keep your messages.** I keep short summaries of interests and "
    "project changes, with the dates and the kind of place they came up, and only "
    "after you confirm them do they affect anything.\n\n"
    "{excluded}"
    "Turn yourself off any time with `/mylo listening off`, or say *shut off* to "
    "stop me asking questions."
)


def _marker_text(excluded: list[str]) -> str:
    if not excluded:
        return MARKER.format(excluded="")
    listed = ", ".join(f"<#{one}>" for one in excluded[:20])
    return MARKER.format(excluded=f"**I never read:** {listed}\n\n")


def _render_status(state: dict) -> str:
    lab = state.get("lab_name") or "this lab"
    dead = state.get("deadlines_channel_id") or ""
    upd = state.get("updates_channel_id") or ""
    dead_line = f"<#{dead}>" if dead else "_off_"
    upd_line = f"<#{upd}>" if upd else "_off_"
    listen = state.get("listening")
    excluded = state.get("excluded") or []
    if not state.get("available", True):
        listen_line = "_not available on Mycelium yet_"
    elif listen:
        listen_line = "**on** — your members choose for themselves"
        if excluded:
            listen_line += f" (never reading {len(excluded)} channel(s))"
    else:
        listen_line = "_off_"
    return (
        f"**Mylo setup for {lab}**\n"
        "Everything here is optional — pick a channel below, or turn a section off.\n"
        f"• **Deadline announcements:** {dead_line}\n"
        f"• **Daily/weekly updates:** {upd_line}\n"
        f"• **Listening:** {listen_line}"
    )


_TEXT_CHANNELS = [discord.ChannelType.text, discord.ChannelType.news]


class SetupView(discord.ui.View):
    """Ephemeral, owner-scoped menu. Times out after 3 minutes of inactivity."""

    def __init__(self, user_id: int, guild_id: str, state: dict) -> None:
        super().__init__(timeout=180)
        self.user_id = user_id
        self.guild_id = guild_id
        self.state = state
        self.binding_id = state.get("binding_id")
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
            str(self.user_id),
            self.guild_id,
            kind=kind,
            channel_id=channel_id,
            binding_id=self.binding_id,
        )
        if status in ("ok", "cleared"):
            self.state = {
                **self.state,
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

    # -- listening --------------------------------------------------------- #

    async def _apply_listening(
        self, interaction: discord.Interaction, *, on: bool
    ) -> None:
        await interaction.response.defer()
        status, payload = await listening.set_guild_listening(
            str(self.user_id), self.guild_id, on=on
        )
        if status != "ok":
            await interaction.edit_original_response(
                content=f"{_render_status(self.state)}\n\n"
                f"{payload.get('message', 'Nothing was changed.')}",
                view=self,
            )
            return

        self.state = {**self.state, **payload}
        note = (
            "👂 Listening is **on**. Each member still chooses for themselves with "
            "`/mylo listening on`; until they do, their messages are dropped."
            if on
            else "🔕 Listening is **off**, and this server's buffered messages were "
            "deleted straight away."
        )
        if on:
            note += await self._post_marker(interaction)
        await interaction.edit_original_response(
            content=f"{_render_status(self.state)}\n\n{note}", view=self
        )

    async def _post_marker(self, interaction: discord.Interaction) -> str:
        """Post — or update — the visible "Mylo is listening" notice.

        Mandatory, not a nicety: the whole feature rests on people knowing
        (OD-02b). It goes in the updates channel if one is bound, otherwise
        where `/setup` was run, so there is always somewhere it lands.
        """
        channel_id = self.state.get("updates_channel_id") or ""
        channel = None
        if channel_id:
            channel = interaction.client.get_channel(int(channel_id))
        if channel is None:
            channel = interaction.channel
        if channel is None:
            return "\n\n⚠️ I could not post the listening notice anywhere."

        text = _marker_text(self.state.get("excluded") or [])
        existing_id = self.state.get("marker_message_id") or ""
        try:
            if existing_id and str(self.state.get("marker_channel_id")) == str(
                channel.id
            ):
                message = await channel.fetch_message(int(existing_id))
                await message.edit(content=text)
            else:
                message = await channel.send(text)
                try:
                    await message.pin()
                except discord.HTTPException:
                    pass  # pinning needs a permission the notice does not
                await listening.set_marker(
                    self.guild_id,
                    channel_id=str(channel.id),
                    message_id=str(message.id),
                )
                self.state = {
                    **self.state,
                    "marker_channel_id": str(channel.id),
                    "marker_message_id": str(message.id),
                }
        except discord.HTTPException:
            return (
                "\n\n⚠️ I could not post the listening notice — check I can write "
                "to that channel. People should be able to see that I am listening."
            )
        return f"\n\nPosted the listening notice in <#{channel.id}>."

    @discord.ui.button(
        label="Turn listening on", style=discord.ButtonStyle.primary, row=3
    )
    async def listening_on(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._apply_listening(interaction, on=True)

    @discord.ui.button(
        label="Turn listening off", style=discord.ButtonStyle.secondary, row=3
    )
    async def listening_off(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._apply_listening(interaction, on=False)

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=_TEXT_CHANNELS,
        placeholder="A channel Mylo must never read…",
        min_values=1,
        max_values=1,
        row=4,
    )
    async def exclude_select(
        self, interaction: discord.Interaction, select: discord.ui.ChannelSelect
    ) -> None:
        await self._apply_exclusion(interaction, str(select.values[0].id))

    async def _apply_exclusion(
        self, interaction: discord.Interaction, channel_id: str
    ) -> None:
        """Add (or, if it is already excluded, remove) a never-read channel."""
        await interaction.response.defer()
        excluded = [str(one) for one in (self.state.get("excluded") or [])]
        turning_on = channel_id not in excluded
        status, payload = await listening.set_channel_rule(
            str(self.user_id),
            self.guild_id,
            channel_id,
            rule="excluded",
            on=turning_on,
        )
        if status != "ok":
            await interaction.edit_original_response(
                content=f"{_render_status(self.state)}\n\n"
                f"{payload.get('message', 'Nothing was changed.')}",
                view=self,
            )
            return
        self.state = {**self.state, **payload}
        note = (
            f"🚫 I will never read <#{channel_id}>."
            if turning_on
            else f"✅ <#{channel_id}> is no longer excluded."
        )
        if self.state.get("listening"):
            note += await self._post_marker(interaction)
        await interaction.edit_original_response(
            content=f"{_render_status(self.state)}\n\n{note}", view=self
        )


class BindingPicker(discord.ui.View):
    """Which lab or department to configure, when a server holds more than one."""

    def __init__(self, user_id: int, guild_id: str, bindings: list[dict]) -> None:
        super().__init__(timeout=120)
        self.user_id = user_id
        self.guild_id = guild_id
        options = [
            discord.SelectOption(
                label=(b["name"] or "Unnamed")[:100],
                description="Department" if b["kind"] == "department" else "Lab",
                value=str(b["binding_id"]),
            )
            for b in bindings[:25]
        ]
        select = discord.ui.Select(placeholder="Lab or department…", options=options)
        select.callback = self._picked  # type: ignore[method-assign]
        self.add_item(select)
        self.select = select

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This setup menu isn't yours — run `/setup` to open your own.",
                ephemeral=True,
            )
            return False
        return True

    async def _picked(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await _open_menu(
            interaction,
            self.user_id,
            self.guild_id,
            int(self.select.values[0]),
            edit=True,
        )


async def _open_menu(
    interaction: discord.Interaction,
    user_id: int,
    guild_id: str,
    binding_id: int | None,
    *,
    edit: bool = False,
) -> None:
    status, payload = await linking.setup_state(str(user_id), guild_id, binding_id)
    if status == "choose":
        view: discord.ui.View = BindingPicker(user_id, guild_id, payload["bindings"])
        await interaction.followup.send(
            payload["message"], view=view, ephemeral=True
        )
        return
    if status != "ok":
        if edit:
            await interaction.edit_original_response(
                content=payload["message"], view=None
            )
        else:
            await interaction.followup.send(payload["message"], ephemeral=True)
        return
    # Listening belongs to a lab's own server; a department binding has none.
    if payload.get("target_kind") == "lab":
        payload = {**payload, **await listening.listening_state(guild_id)}
    else:
        payload = {**payload, "available": False}
    view = SetupView(user_id, guild_id, payload)
    if edit:
        await interaction.edit_original_response(
            content=_render_status(payload), view=view
        )
        view.message = await interaction.original_response()
    else:
        view.message = await interaction.followup.send(
            _render_status(payload), view=view, ephemeral=True, wait=True
        )


class SetupCog(commands.Cog, name="Setup"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="setup",
        description="Choose where this server's lab or department messages post.",
    )
    @app_commands.guild_only()
    async def setup(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        await _open_menu(
            interaction,
            interaction.user.id,
            str(interaction.guild_id) if interaction.guild_id else "",
            None,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SetupCog(bot))
