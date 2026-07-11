"""Slash commands: options, validation, autocomplete, groups, checks, context menus.

Reference for the `discord-bot` skill. discord.py 2.7.1.

The type annotation IS the schema. Discord renders the picker, validates the
input, and rejects bad values in the client -- so a well-typed command never
receives garbage. Lean on that instead of validating by hand in the body.

Naming rules Discord enforces: command names are 1-32 chars, lowercase, and
match ^[-_'\\p{L}\\p{N}]{1,32}$. Descriptions are 1-100 chars and are the only
documentation the user ever sees, so write them for a human.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from .errors import NotFoundError

# --------------------------------------------------------------------------
# A stand-in for your domain layer. Note: no `discord` import in here.
# Keep business logic in services/ so it is testable without a gateway.
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Lab:
    slug: str
    name: str


_LABS = [Lab("neuro", "Neuroscience Lab"), Lab("bio-eng", "Bioengineering Lab")]


async def search_labs(query: str) -> list[Lab]:
    q = query.casefold()
    return [lab for lab in _LABS if q in lab.name.casefold() or q in lab.slug]


async def get_lab(slug: str) -> Lab | None:
    return next((lab for lab in _LABS if lab.slug == slug), None)


# --------------------------------------------------------------------------
# Transformer: parse + validate an option into a domain object, with a clean
# error if it fails. This runs BEFORE your command body, so the body can assume
# a valid `Lab`. It can also supply its own autocomplete.
# --------------------------------------------------------------------------
class LabTransformer(app_commands.Transformer):
    async def transform(self, interaction: discord.Interaction, value: str) -> Lab:
        lab = await get_lab(value)
        if lab is None:
            raise NotFoundError(f"a lab called `{value}`")  # -> rendered by the tree error handler
        return lab

    async def autocomplete(  # type: ignore[override]
        self,
        interaction: discord.Interaction,
        value: str,
    ) -> list[app_commands.Choice[str]]:
        labs = await search_labs(value)
        # HARD CAP: 25. Return the 25 BEST matches, not the first 25 you find.
        return [app_commands.Choice(name=lab.name, value=lab.slug) for lab in labs[:25]]


# `Transform[ReturnType, TransformerClass]` is how you attach it to a parameter.
LabOption = app_commands.Transform[Lab, LabTransformer]


class ResearchCog(commands.Cog):
    """One cog per feature area."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

        # Context menus CANNOT be declared with a decorator inside a class.
        # Build them here and register them on the tree by hand.
        self.summarize_message = app_commands.ContextMenu(
            name="Summarize this message",  # shows in the right-click -> Apps menu
            callback=self.summarize_message_callback,
        )
        self.bot.tree.add_command(self.summarize_message)

    async def cog_unload(self) -> None:
        # Extensions can be reloaded; remove what you manually added or you'll
        # get CommandAlreadyRegistered on the next load.
        self.bot.tree.remove_command(self.summarize_message.name, type=self.summarize_message.type)

    # ----------------------------------------------------------------------
    # 1. The basics: typed options + describe
    # ----------------------------------------------------------------------
    @app_commands.command(name="ping", description="Check that the bot is alive.")
    async def ping(self, interaction: discord.Interaction) -> None:
        latency_ms = self.bot.latency * 1000
        await interaction.response.send_message(f"Pong — {latency_ms:.0f}ms", ephemeral=True)

    @app_commands.command(name="find", description="Search the corpus for papers.")
    @app_commands.describe(
        query="What to search for.",
        limit="How many results to show (1-25).",
        scope="Where to search.",
        public="Show the result to the whole channel instead of just you.",
    )
    async def find(
        self,
        interaction: discord.Interaction,
        query: str,
        # Range gives Discord min/max -- the client refuses out-of-bounds input,
        # so it never reaches your code.
        limit: app_commands.Range[int, 1, 25] = 5,
        # Literal renders a fixed dropdown. Equivalent to @app_commands.choices.
        scope: Literal["papers", "grants", "fellowships"] = "papers",
        # A default value makes the option optional.
        public: bool = False,
    ) -> None:
        await interaction.response.defer(thinking=True, ephemeral=not public)
        results = await search_labs(query)  # stand-in for real work
        text = "\n".join(f"• {lab.name}" for lab in results[:limit]) or "_No matches._"
        await interaction.followup.send(f"**{scope}** results for `{query}`:\n{text}")

    # ----------------------------------------------------------------------
    # 2. Autocomplete attached to a plain string option
    #    (the other way; the Transformer above is usually cleaner)
    # ----------------------------------------------------------------------
    @app_commands.command(name="watch", description="Watch a topic for new results.")
    @app_commands.describe(topic="Start typing to see suggestions.")
    async def watch(self, interaction: discord.Interaction, topic: str) -> None:
        await interaction.response.send_message(f"Watching **{topic}**.", ephemeral=True)

    @watch.autocomplete("topic")
    async def watch_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Fires on EVERY KEYSTROKE and must answer within 3 seconds.

        Never call a slow API from here. Query a cache, an index, or an
        in-memory list. If you can't answer fast, return [] rather than hanging.
        """
        topics = ["protein folding", "CRISPR delivery", "neural decoding"]
        return [
            app_commands.Choice(name=t, value=t)
            for t in topics
            if current.casefold() in t.casefold()
        ][:25]

    # ----------------------------------------------------------------------
    # 3. Transformer-backed option: the body receives a `Lab`, never a string
    # ----------------------------------------------------------------------
    @app_commands.command(name="lab-info", description="Show a lab's profile.")
    @app_commands.describe(lab="Which lab.")
    async def lab_info(self, interaction: discord.Interaction, lab: LabOption) -> None:
        embed = discord.Embed(title=lab.name, description=f"slug: `{lab.slug}`")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ----------------------------------------------------------------------
    # 4. Context menus: right-click a message or a user
    # ----------------------------------------------------------------------
    async def summarize_message_callback(
        self,
        interaction: discord.Interaction,
        message: discord.Message,  # annotation decides the menu type
    ) -> None:
        await interaction.response.send_message(
            f"Summarizing {message.jump_url}…", ephemeral=True
        )

    # ----------------------------------------------------------------------
    # 5. Checks: permissions, scope, cooldowns.
    #    Guard with decorators, not with `if` statements in the body -- failed
    #    checks raise typed errors that the tree handler renders consistently.
    # ----------------------------------------------------------------------
    @app_commands.command(name="reindex", description="Rebuild the search index.")
    # Who SEES the command by default. Server admins can override this per-role
    # in Server Settings -> Integrations.
    @app_commands.default_permissions(manage_guild=True)
    # Who may actually RUN it (enforced server-side by us).
    @app_commands.checks.has_permissions(manage_guild=True)
    # Not usable in DMs.
    @app_commands.guild_only()
    # Abuse control: 1 use per 60s per user. Put one on anything that hits an
    # external service or costs money.
    @app_commands.checks.cooldown(1, 60.0, key=lambda i: i.user.id)
    async def reindex(self, interaction: discord.Interaction) -> None:
        # Before doing something privileged, confirm WE have the permission.
        # Failing with a sentence beats failing with a raw Forbidden.
        if not interaction.app_permissions.manage_messages:
            raise NotFoundError("the Manage Messages permission (grant it to my role)")
        await interaction.response.send_message("Reindexing…", ephemeral=True)


# --------------------------------------------------------------------------
# 6. Command groups: /config alerts set  --  reads better than /set_alert_config
#    Max TWO levels of nesting (group -> subgroup -> command).
# --------------------------------------------------------------------------
class ConfigCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # A Group declared as a class attribute is bound to the cog automatically.
    config = app_commands.Group(
        name="config",
        description="Configure the bot for this server.",
        default_permissions=discord.Permissions(manage_guild=True),
        guild_only=True,
    )

    # A nested subgroup: /config alerts ...
    alerts = app_commands.Group(
        name="alerts",
        description="Digest and alert delivery.",
        parent=config,
    )

    @config.command(name="show", description="Show the current configuration.")
    async def config_show(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message("…", ephemeral=True)

    @alerts.command(name="set", description="Set the channel alerts are posted to.")
    @app_commands.describe(channel="Where to post alerts.")
    async def alerts_set(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ) -> None:
        await interaction.response.send_message(f"Alerts → {channel.mention}", ephemeral=True)


# --------------------------------------------------------------------------
# 7. User-installable commands: the user installs the APP to their account, so
#    the command works in any server and in DMs -- even where the bot isn't a
#    member. Useful for personal, read-only utilities.
# --------------------------------------------------------------------------
class PersonalCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="my-digest", description="Show your personal digest.")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def my_digest(self, interaction: discord.Interaction) -> None:
        # In a user-install context there may be no guild and very few permissions.
        # `interaction.is_user_integration()` tells you which you're in.
        where = "user-installed" if interaction.is_user_integration() else "server"
        await interaction.response.send_message(f"Your digest ({where} context)…", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Every extension module exposes this. `await bot.load_extension(...)` calls it."""
    await bot.add_cog(ResearchCog(bot))
    await bot.add_cog(ConfigCog(bot))
    await bot.add_cog(PersonalCog(bot))
