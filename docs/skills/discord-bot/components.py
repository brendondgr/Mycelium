"""Components: buttons, selects, modals, persistent views, Components V2.

Reference for the `discord-bot` skill. discord.py 2.7.1.

Limits: 5 buttons per row, 5 rows -> 25 buttons per message. 25 options per
select. 5 top-level components per modal. custom_id is capped at 100 chars.

Three things that bite people:

1. TIMEOUTS. A View times out (180s by default) and its buttons go dead while
   still looking clickable. Handle `on_timeout` and disable them.

2. PERSISTENCE. After a restart, buttons on old messages stop working -- unless
   the view is persistent (timeout=None + explicit custom_ids) AND re-registered
   with `bot.add_view(...)` in `setup_hook` on every boot.

3. OWNERSHIP. Anyone in the channel can click anyone else's button. Guard with
   `interaction_check`.
"""

from __future__ import annotations

import logging
import re

import discord
from discord import app_commands, ui
from discord.ext import commands

log = logging.getLogger(__name__)


# ==========================================================================
# 1. Ephemeral view: buttons + a select, scoped to the invoking user
# ==========================================================================
class ConfirmView(ui.View):
    """A yes/no confirmation. Times out; guards ownership; reports its result."""

    def __init__(self, *, owner_id: int, timeout: float = 60.0) -> None:
        super().__init__(timeout=timeout)
        self.owner_id = owner_id
        self.value: bool | None = None
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Runs before every child callback. False = reject, silently to others."""
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "This isn't your prompt.", ephemeral=True
            )
            return False
        return True

    async def on_timeout(self) -> None:
        """Don't leave dead buttons on screen."""
        for item in self.children:
            if isinstance(item, ui.Button | ui.Select):
                item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass  # message may already be gone

    @ui.button(label="Confirm", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm(self, interaction: discord.Interaction, button: ui.Button) -> None:
        self.value = True
        # edit_message updates the message the component lives on. This is the
        # response for THIS interaction -- component clicks get their own fresh
        # 3-second window.
        await interaction.response.edit_message(content="Deleted.", view=None)
        self.stop()  # release anyone awaiting view.wait()

    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button) -> None:
        self.value = False
        await interaction.response.edit_message(content="Cancelled.", view=None)
        self.stop()

    @ui.select(
        placeholder="Optional: pick a reason…",
        options=[
            discord.SelectOption(label="Duplicate", value="dupe", description="Already tracked"),
            discord.SelectOption(label="Irrelevant", value="irrelevant"),
        ],
        min_values=1,
        max_values=1,
    )
    async def reason(self, interaction: discord.Interaction, select: ui.Select) -> None:
        await interaction.response.send_message(
            f"Noted: {select.values[0]}", ephemeral=True
        )


# ==========================================================================
# 2. Persistent view: survives restarts
#    - timeout=None
#    - every child has an explicit, stable custom_id
#    - registered in setup_hook via bot.add_view(PersistentPanel())
# ==========================================================================
class PersistentPanel(ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)  # REQUIRED for persistence

    @ui.button(
        label="Subscribe to the digest",
        style=discord.ButtonStyle.primary,
        custom_id="mycelium:digest:subscribe",  # REQUIRED: stable across restarts
    )
    async def subscribe(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.send_message("Subscribed.", ephemeral=True)


# ==========================================================================
# 3. DynamicItem: carry state INSIDE the custom_id via a regex template.
#    The right tool when a button must know which record it belongs to without
#    a lookup table that dies with the process.
#    Register once: bot.add_dynamic_items(SavePaperButton)
# ==========================================================================
class SavePaperButton(ui.DynamicItem[ui.Button], template=r"paper:save:(?P<paper_id>\d+)"):
    def __init__(self, paper_id: int) -> None:
        self.paper_id = paper_id
        super().__init__(
            ui.Button(
                label="Save",
                style=discord.ButtonStyle.success,
                custom_id=f"paper:save:{paper_id}",  # must match the template
            )
        )

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: ui.Button,
        match: re.Match[str],
        /,
    ) -> SavePaperButton:
        return cls(int(match["paper_id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            f"Saved paper {self.paper_id}.", ephemeral=True
        )


# ==========================================================================
# 4. Modals: the only way to collect long or structured text.
#
#    A modal IS the response -- you cannot defer first, and you cannot open one
#    from inside another modal or after any other response.
# ==========================================================================
class FeedbackModal(ui.Modal, title="Send feedback"):
    """Classic form: TextInput as a class attribute. Read `.value` in on_submit."""

    summary = ui.TextInput(
        label="Summary",
        style=discord.TextStyle.short,
        placeholder="One line",
        max_length=100,
        required=True,
    )
    details = ui.TextInput(
        label="Details",
        style=discord.TextStyle.paragraph,  # multi-line box
        placeholder="What happened?",
        max_length=2000,
        required=False,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        log.info("feedback from %s: %s", interaction.user.id, self.summary.value)
        await interaction.response.send_message("Thanks — logged it.", ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        log.exception("modal submit failed", exc_info=error)
        await interaction.response.send_message("Couldn't save that.", ephemeral=True)


class TriageModal(ui.Modal, title="Triage"):
    """discord.py 2.6+ form: ui.Label wraps any component, and selects are
    allowed inside modals. Keep a reference to the inner component to read it.
    """

    def __init__(self) -> None:
        super().__init__()

        self.note = ui.TextInput(style=discord.TextStyle.paragraph, max_length=500)
        self.priority = ui.Select(
            options=[
                discord.SelectOption(label="High", value="high"),
                discord.SelectOption(label="Normal", value="normal", default=True),
            ]
        )

        # Label supplies the visible text + optional helper description.
        self.add_item(ui.Label(text="Note", component=self.note, description="What did you find?"))
        self.add_item(ui.Label(text="Priority", component=self.priority))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            f"Filed at **{self.priority.values[0]}**.", ephemeral=True
        )


# ==========================================================================
# 5. Components V2 (LayoutView): real layout control.
#    A message using a LayoutView CANNOT also use `content` or `embeds`.
#    Reach for it only when an embed genuinely can't express the layout.
# ==========================================================================
class DigestPanel(ui.LayoutView):
    def __init__(self, title: str, body: str) -> None:
        super().__init__(timeout=None)

        container = ui.Container(accent_colour=discord.Colour.blurple())
        container.add_item(ui.TextDisplay(f"## {title}"))
        container.add_item(ui.Separator())
        container.add_item(
            ui.Section(
                ui.TextDisplay(body),
                accessory=ui.Button(
                    label="Open",
                    style=discord.ButtonStyle.link,
                    url="https://example.com",
                ),
            )
        )
        self.add_item(container)


# ==========================================================================
# Wiring it together
# ==========================================================================
class ComponentsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="delete", description="Delete something, with confirmation.")
    async def delete(self, interaction: discord.Interaction) -> None:
        view = ConfirmView(owner_id=interaction.user.id)
        await interaction.response.send_message(
            "Delete this? This can't be undone.", view=view, ephemeral=True
        )
        # Needed so on_timeout can disable the buttons.
        view.message = await interaction.original_response()

        await view.wait()  # blocks until a button is pressed or the view times out
        if view.value is None:
            log.info("confirm timed out for %s", interaction.user.id)

    @app_commands.command(name="feedback", description="Send feedback via a form.")
    async def feedback(self, interaction: discord.Interaction) -> None:
        # NOTE: no defer. send_modal IS the response.
        await interaction.response.send_modal(FeedbackModal())

    @app_commands.command(name="panel", description="Post the persistent subscribe panel.")
    @app_commands.default_permissions(manage_guild=True)
    async def panel(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            "Digest controls:", view=PersistentPanel()
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ComponentsCog(bot))

    # Both of these must happen on EVERY boot, or components on messages sent
    # before the last restart go dead. Do them in Bot.setup_hook.
    bot.add_view(PersistentPanel())
    bot.add_dynamic_items(SavePaperButton)
