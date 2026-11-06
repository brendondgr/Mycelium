"""The whole ``/mylo`` command surface, in one cog.

Deliberately one cog rather than three. discord.py binds an ``app_commands.Group``
to the cog that declares it and mutates the group as commands register, so a group
shared across cogs collides the moment a second one loads — and a group declared
twice under the same name collides at sync time. Splitting ``/mylo`` by concern is
therefore not available; keeping the concerns visible in the section headers below
is the next best thing.

Two rules hold for every command here:

* **Defer first.** Discord allows about three seconds to acknowledge an interaction.
  These touch the database, the gate's Redis check and, for search, a query
  embedding. It looks fine against a warm cache and fails constantly in production,
  so deferring is the only correct shape — not an optimisation.
  (``health``/``lastrun`` are the exception: a plain file read, fast enough to answer
  directly.)
* **Reply ephemerally.** Someone's saved items, research feed and reminders are
  theirs; a channel is a public place.

Authorization is never decided here. Every command calls into ``mylo.linking`` →
``apps.content.discord_commands``, which starts at the single gate.
"""

from __future__ import annotations

import socket

import discord
from discord import app_commands
from discord.ext import commands

from ... import linking, listening
from ...runstate import read_run_state

BRAND = 0x3B7A57

_LISTENING_ON = (
    "✅ **On.** I'll keep up with your work from the conversation you're already "
    "having.\n\n"
    "I don't keep your messages. I keep short summaries of interests and project "
    "changes, with the dates and the kind of place they came up, and only after "
    "you confirm them do they affect anything. Say *shut off* any time to stop me "
    "asking questions, or run `/mylo listening off` to stop entirely."
)
_LISTENING_OFF = (
    "🔕 **Off.** Nothing you say is being recorded.\n\n"
    "Run `/mylo listening on` if you'd like me to keep up with your work from the "
    "conversation you're already having. You can change your mind whenever you "
    "like, and delete everything I've summarised, from your Mycelium settings."
)
_LISTENING_UNAVAILABLE = (
    "Listening isn't switched on for Mycelium yet, so nothing you say is being "
    "recorded. Your choice — **{choice}** — is saved and will apply if it is."
)
_NOTE_REFUSALS = {
    "person_not_opted_in": "You haven't turned listening on, so I didn't keep "
    "that. Run `/mylo listening on` first.",
    "speaker_unlinked": "Your Discord isn't connected to Mycelium yet, so I "
    "didn't keep that. Run `/activate` with a code from your profile.",
    "tier_free": "This is part of a paid plan. Nothing was saved.",
    "ambient_disabled": "I'm not set up to remember things yet. Nothing was saved.",
}
_AREA_LABEL = {
    "grant": "Grant",
    "conference": "Conference",
    "fellowship": "Fellowship",
    "paper": "Paper",
}


def _announce_view(results: list[dict]) -> discord.ui.View | None:
    """"Announce to #…" buttons for a manager, one per binding that has not posted
    a result. Handled by the announcements cog (``annx:``), which posts once."""
    view = discord.ui.View(timeout=600)
    for index, row in enumerate(results, start=1):
        for option in row.get("announce") or []:
            if len(view.children) >= 20:
                break
            view.add_item(
                discord.ui.Button(
                    label=f"{index}. Announce to {option['purpose']}"[:80],
                    style=discord.ButtonStyle.secondary,
                    emoji="📣",
                    custom_id=f"annx:{option['binding_id']}:{row['content_id']}",
                )
            )
    return view if view.children else None


class MyloCog(commands.Cog, name="Mylo"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    mylo = app_commands.Group(name="mylo", description="Mylo status and controls.")

    # ------------------------------------------------------- observability
    @mylo.command(name="health", description="Is Mylo online, and how did the last run go?")
    async def health(self, interaction: discord.Interaction) -> None:
        # Listening state is a database read, so this one defers where the rest
        # of `health` would happily answer from a file.
        await interaction.response.defer(ephemeral=True)
        config = getattr(self.bot, "config", None)
        channel_set = bool(getattr(config, "error_channel_id", None))
        state = read_run_state()

        lines = [f"\U0001F7E2 Mylo is online on **{socket.gethostname()}**."]
        lines.append(
            f"Error channel: {'configured' if channel_set else '**not set**'}."
        )
        if state is None:
            lines.append("Last daily run: none recorded yet.")
        elif state.get("ok"):
            lines.append(f"Last daily run: ✅ ok ({state.get('finished_at', '?')}).")
        else:
            lines.append(
                f"Last daily run: ❌ failed at "
                f"`{state.get('failed_stage', '?')}` ({state.get('finished_at', '?')})."
            )
        lines.extend(await self._listening_lines(interaction))
        await interaction.followup.send("\n".join(lines), ephemeral=True)

    async def _listening_lines(self, interaction: discord.Interaction) -> list[str]:
        """Listening state for the server `/mylo health` was run in.

        Reports the *stage* as well as the switch. "Listening is on" while the
        Message Content intent is missing would be a true statement about the
        database and a misleading one about what Mylo can actually hear, and an
        operator reading this is asking the second question.
        """
        if not interaction.guild_id:
            return []
        state = await listening.listening_state(str(interaction.guild_id))
        if not state.get("known") or not state.get("listening"):
            return ["Listening here: **off**."]

        stage_b = bool(
            getattr(getattr(self.bot, "config", None), "listen_enabled", False)
            and getattr(self.bot.intents, "message_content", False)
        )
        reach = (
            "every channel it is not excluded from"
            if stage_b
            else "DMs and messages that mention it only "
            "(server-wide listening is not enabled)"
        )
        lines = [f"Listening here: **on** — {reach}."]
        excluded = state.get("excluded") or []
        if excluded:
            lines.append(f"Never reads: {len(excluded)} channel(s).")
        lines.append(
            f"Today: heard {state.get('heard_today', 0)}, "
            f"kept {state.get('stored_today', 0)} for tonight's reading."
        )
        return lines

    @mylo.command(name="lastrun", description="Details of the most recent daily run.")
    async def lastrun(self, interaction: discord.Interaction) -> None:
        state = read_run_state()
        if state is None:
            await interaction.response.send_message(
                "No daily run has been recorded yet.", ephemeral=True
            )
            return

        ok = bool(state.get("ok"))
        embed = discord.Embed(
            title="Last daily run",
            colour=discord.Colour.green() if ok else discord.Colour.red(),
        )
        embed.add_field(name="Outcome", value="ok" if ok else "failed", inline=True)
        embed.add_field(name="Finished", value=str(state.get("finished_at", "?")), inline=True)
        embed.add_field(name="Host", value=str(state.get("host", "?")), inline=True)
        embed.add_field(
            name="Scrape ran", value="yes" if state.get("scrape_ran") else "no", inline=True
        )
        stages = ", ".join(state.get("stages_run") or []) or "—"
        embed.add_field(name="Stages completed", value=stages, inline=False)
        if state.get("failed_stage"):
            embed.add_field(
                name="Failed stage",
                value=f"{state['failed_stage']} (exit {state.get('exit_code', '?')})",
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @mylo.command(
        name="status", description="Am I linked to Mycelium, and is my link healthy?"
    )
    async def status(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        _, message = await linking.status(str(interaction.user.id))
        await interaction.followup.send(message, ephemeral=True)

    # -------------------------------------------------------------- listening
    @mylo.command(
        name="listening",
        description="Choose whether Mylo may learn from what you say here.",
    )
    @app_commands.describe(
        setting="on to let Mylo learn from your messages, off to stop, "
        "blank to see where you stand."
    )
    @app_commands.choices(
        setting=[
            app_commands.Choice(name="on", value="on"),
            app_commands.Choice(name="off", value="off"),
        ]
    )
    async def listening_command(
        self,
        interaction: discord.Interaction,
        setting: app_commands.Choice[str] | None = None,
    ) -> None:
        """Your own opt-in. Nobody needs a manager's permission to opt out."""
        await interaction.response.defer(ephemeral=True)
        user_id = str(interaction.user.id)
        if setting is not None:
            state = await listening.set_member_listening(
                user_id, on=setting.value == "on"
            )
        else:
            state = await listening.member_state(user_id)

        if not state.get("linked"):
            await interaction.followup.send(
                "Your Discord isn't connected to Mycelium yet, so there is "
                "nothing to turn on — and nothing about you is being recorded. "
                "Run `/activate` with a code from your profile first.",
                ephemeral=True,
            )
            return
        if not state.get("available", True):
            # Say so plainly. "On — I'll keep up with your work" would be false
            # while the deployment records nothing; the choice is still kept,
            # so it holds the day listening is switched on.
            await interaction.followup.send(
                _LISTENING_UNAVAILABLE.format(
                    choice="on" if state.get("enabled") else "off"
                ),
                ephemeral=True,
            )
            return
        await interaction.followup.send(
            _LISTENING_ON if state.get("enabled") else _LISTENING_OFF, ephemeral=True
        )

    @mylo.command(
        name="note",
        description="Tell Mylo something to remember about your work.",
    )
    @app_commands.describe(text="In your own words — no format, no syntax.")
    async def note(self, interaction: discord.Interaction, text: str) -> None:
        """A convenience for people who like commands. Nothing depends on it."""
        await interaction.response.defer(ephemeral=True)
        outcome = await listening.note(
            str(interaction.user.id),
            text,
            guild_id=str(interaction.guild_id or ""),
        )
        if outcome.get("stored"):
            await interaction.followup.send(
                "Got it — I'll take that into account.", ephemeral=True
            )
            return
        await interaction.followup.send(
            _NOTE_REFUSALS.get(
                outcome.get("reason", ""),
                "I couldn't record that just now. Nothing was saved.",
            ),
            ephemeral=True,
        )

    # ----------------------------------------------------------------- search
    @mylo.command(name="search", description="Search Mycelium's research corpus.")
    @app_commands.describe(query="What to look for.")
    async def search(self, interaction: discord.Interaction, query: str) -> None:
        await interaction.response.defer(ephemeral=True)
        status, payload = await linking.search(
            str(interaction.user.id),
            query,
            str(interaction.guild_id) if interaction.guild_id else "",
        )
        if status != "ok":
            await interaction.followup.send(
                payload.get("message", "Something went wrong."), ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"Results for “{payload['query']}”", colour=BRAND
        )
        for i, row in enumerate(payload["results"], start=1):
            bits = []
            if row["cluster"]:
                bits.append(row["cluster"])
            if row["matched_on"]:
                bits.append("matched on " + ", ".join(row["matched_on"]))
            if row["saved"]:
                bits.append("saved")
            title = row["title"][:200]
            name = f"{i}. {title}"
            value = " · ".join(bits) or _AREA_LABEL.get(row["type"], row["type"])
            if row["url"]:
                value = f"[Open]({row['url']}) · {value}"
            if row.get("thread_url"):
                # Already announced in this server: point at the conversation.
                value += f"\n💬 Already discussed here → [thread]({row['thread_url']})"
            embed.add_field(name=name, value=value[:1024], inline=False)

        if payload.get("confidence") == "low":
            # Search never abstains, so a weak match still returns something. Saying
            # so is the difference between a useful result and a misleading one.
            embed.set_footer(text="Nothing matched closely — these are the nearest.")
        view = _announce_view(payload["results"])
        if view is None:
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    # ----------------------------------------------------------------- digest
    @mylo.command(name="digest", description="Your compiled research report.")
    @app_commands.describe(lab="A lab's report instead of your own (optional).")
    async def digest(
        self, interaction: discord.Interaction, lab: str | None = None
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        status, payload = await linking.digest(str(interaction.user.id), lab or "")
        if status != "ok":
            await interaction.followup.send(
                payload.get("message", "Something went wrong."), ephemeral=True
            )
            return

        owner = payload.get("owner") or "your"
        heading = f"{owner} research report" if payload.get("owner") else "Your research report"
        embed = discord.Embed(title=heading, colour=BRAND)
        if payload["stale"]:
            # Never quietly present yesterday's report as today's.
            embed.description = f"From **{payload['generated_on']}** — today's isn't written yet."
        counts = payload.get("counts") or {}
        new_counts = payload.get("new_counts") or {}
        if counts:
            embed.add_field(
                name="Today",
                value="\n".join(
                    f"**{v}** {k}" + (f" ({new_counts[k]} new)" if new_counts.get(k) else "")
                    for k, v in counts.items()
                ),
                inline=False,
            )
        body = (payload.get("body") or "").strip()
        if body:
            embed.add_field(name="Mylo's read", value=_clip(body, 900), inline=False)
        embed.set_footer(text="The full report lives in Mycelium.")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @digest.autocomplete("lab")
    async def _lab_options(self, interaction: discord.Interaction, current: str):
        labs = await linking.user_labs(str(interaction.user.id))
        needle = (current or "").lower()
        return [
            app_commands.Choice(name=lab["name"][:100], value=lab["slug"])
            for lab in labs
            if needle in lab["name"].lower()
        ][:25]

    # ------------------------------------------------------------------ saves
    @mylo.command(name="saves", description="Your recently saved items.")
    async def saves(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        status, payload = await linking.saves(str(interaction.user.id), 0)
        if status != "ok":
            await interaction.followup.send(
                payload.get("message", "Something went wrong."), ephemeral=True
            )
            return
        view = SavesView(interaction.user.id, payload) if payload["has_more"] else None
        await interaction.followup.send(
            embed=saves_embed(payload), view=view, ephemeral=True
        )

    # ----------------------------------------------------------- reminders
    async def _reminder_options(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        status, payload = await linking.manageable_reminders(
            str(interaction.user.id), current or ""
        )
        if status != "ok":
            return []
        # Title, then *which* deadline, then the date. An item can carry
        # several reminders — a workshop deadline and two paper rounds — and
        # they all share a title, so the deadline is what tells them apart.
        return [
            app_commands.Choice(
                name=f"{row['title'][:60]}"
                + (f" · {row['deadline']}" if row.get("deadline") else "")
                + (f" · due {row['due_date']}" if row["due_date"] else ""),
                value=row["id"],
            )
            for row in payload["items"]
        ]

    # ----------------------------------------------------------------- snooze
    @mylo.command(name="snooze", description="Push a reminder back.")
    @app_commands.describe(
        reminder="Which reminder.",
        amount="How many days/weeks/months from now.",
        unit="Day, week or month.",
    )
    @app_commands.choices(
        unit=[
            app_commands.Choice(name="day", value="day"),
            app_commands.Choice(name="week", value="week"),
            app_commands.Choice(name="month", value="month"),
        ]
    )
    async def snooze(
        self,
        interaction: discord.Interaction,
        reminder: str,
        amount: app_commands.Range[int, 1, 52] = 1,
        unit: app_commands.Choice[str] | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        status, payload = await linking.snooze(
            str(interaction.user.id),
            reminder_id=reminder,
            amount=int(amount),
            unit=(unit.value if unit else "week"),
        )
        if status != "ok":
            await interaction.followup.send(
                payload.get("message", "Something went wrong."), ephemeral=True
            )
            return

        lines = [
            f"⏾ **{payload['title']}** ({payload['deadline']}) is snoozed "
            f"until **{payload['snoozed_until']}**."
        ]
        if payload["clamped"]:
            # Snoozing past the deadline would have silently cancelled it; say what
            # happened instead of pretending the request was honoured as given.
            lines.append(
                f"That's as far as it goes — the deadline itself is "
                f"{payload['due_date']}."
            )
        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @snooze.autocomplete("reminder")
    async def _snooze_options(self, interaction: discord.Interaction, current: str):
        return await self._reminder_options(interaction, current)

    # ----------------------------------------------------------------- cancel
    @mylo.command(name="cancel", description="Stop a reminder.")
    @app_commands.describe(reminder="Which reminder.")
    async def cancel(self, interaction: discord.Interaction, reminder: str) -> None:
        await interaction.response.defer(ephemeral=True)
        status, payload = await linking.cancel(
            str(interaction.user.id), reminder_id=reminder
        )
        if status != "ok":
            await interaction.followup.send(
                payload.get("message", "Something went wrong."), ephemeral=True
            )
            return

        # Idempotent by design: cancelling something already cancelled is a
        # confirmation, not an error.
        note = (
            f"**{payload['title']}** ({payload['deadline']}) was already cancelled."
            if payload["already"]
            else f"🔕 **{payload['title']}** ({payload['deadline']}) is cancelled "
            "— no more reminders for it."
        )
        await interaction.followup.send(note, ephemeral=True)

    @cancel.autocomplete("reminder")
    async def _cancel_options(self, interaction: discord.Interaction, current: str):
        return await self._reminder_options(interaction, current)


def saves_embed(payload: dict) -> discord.Embed:
    embed = discord.Embed(
        title=f"Your saved items ({payload['total']})", colour=BRAND
    )
    for row in payload["items"]:
        bits = [_AREA_LABEL.get(row["area"], row["area"])]
        if row["subtitle"]:
            bits.append(row["subtitle"][:80])
        if row["days_remaining"] is not None:
            days = row["days_remaining"]
            bits.append("due today" if days == 0 else f"{days} days left")
        value = " · ".join(bits)
        if row["url"]:
            value = f"[Open]({row['url']}) · {value}"
        embed.add_field(name=row["title"][:200], value=value, inline=False)
    page = payload["page"] + 1
    embed.set_footer(text=f"Page {page}")
    return embed


class SavesView(discord.ui.View):
    """Prev/Next over the saved list, scoped to whoever ran the command.

    ``interaction_check`` matters more than it looks: an ephemeral message is only
    *displayed* privately, and a component click is a fresh interaction that anyone
    holding the message could in principle send. The owner check is what makes the
    pagination as private as the first page was.
    """

    def __init__(self, user_id: int, payload: dict) -> None:
        super().__init__(timeout=180)
        self.user_id = user_id
        self.page = payload["page"]
        self.message: discord.Message | None = None
        self._sync_buttons(payload)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "That list isn't yours — run `/mylo saves` for your own.",
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    def _sync_buttons(self, payload: dict) -> None:
        self.previous.disabled = payload["page"] == 0
        self.next.disabled = not payload["has_more"]

    async def _turn(self, interaction: discord.Interaction, delta: int) -> None:
        await interaction.response.defer()
        status, payload = await linking.saves(
            str(interaction.user.id), max(0, self.page + delta)
        )
        if status != "ok":
            await interaction.followup.send(
                payload.get("message", "Nothing more to show."), ephemeral=True
            )
            return
        self.page = payload["page"]
        self._sync_buttons(payload)
        await interaction.edit_original_response(
            embed=saves_embed(payload), view=self
        )

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, _button) -> None:
        await self._turn(interaction, -1)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, _button) -> None:
        await self._turn(interaction, +1)


def _clip(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MyloCog(bot))
