# Phase C — The five `/mylo` commands

**Status:** As built. Written against the code as it stands after Phase B.
**Correlation ID:** `20260726-mylo-slash-commands`
**Umbrella:** [`mylo-discord-pipeline.md`](mylo-discord-pipeline.md)

## Objective

`/mylo search`, `digest`, `saves`, `snooze`, `cancel` — all behind the Phase B gate,
all deferring before any work, all ephemeral.

## Decisions taken during the build

| # | Decision | Why |
|---|---|---|
| C-a | **One cog owns `/mylo`**, not three. | discord.py binds an `app_commands.Group` to the cog that declares it and mutates the group as commands register, so a group shared across cogs collides the moment a second loads, and two cogs declaring the same group name collide at sync time. Splitting by concern is simply not available; section headers carry that job instead. Discovered by a real failure (`CommandAlreadyRegistered: health`), not predicted. |
| C-b | **`SearchView`'s body moves into `search_service.search_for_user`**, and the view becomes one of two callers. | The alternative was the bot calling `run_search` alone and quietly showing worse results than the website. Now a disagreement between Mylo and the portal is a bug in one function. |
| C-c | **No match percentage in search results.** | Search scores by rank fusion and never computes one. Showing `matched_on` in words ("matched on meaning") reports what actually happened; a percentage would be a figure with nothing behind it. |
| C-d | **Free `/mylo digest` says so plainly** (closes Q-2 → L8). | Free is never run through the daily pipeline, so there is genuinely nothing. Naming what Spore adds beats assembling a hollow report. |
| C-e | **`snoozed_until` suppresses without sealing.** | The offsets stay open, so when the snooze lapses the still-pending ones trigger together and the existing one-message-per-day collapse sends a single reminder with the true days remaining. Sealing would have been the difference between "later" and "never". |
| C-f | **Snoozing past the deadline clamps and says so.** | Otherwise "snooze" silently means "cancel". |
| C-g | **Cancel is soft on both surfaces** (closes Q-7). | The web endpoint switched from hard delete, so "why did this stop reminding me?" keeps an answer and the fired ledger stays intact. |
| C-h | **Autocomplete is part of the authorization surface.** | Offering a reminder that would then be refused still tells the caller it exists. |

## Where it lives

- `apps/content/discord_commands.py` — the five command bodies, `(status, payload)`.
- `apps/content/search_service.py` — the shared search path.
- `mylo/linking.py` — async facades; `mylo/bot/cogs/mylo_commands.py` — the one cog.
- `ReminderSubscription.snoozed_until` (migration `content/0017`).

## Validation

`apps/content/tests/test_discord_commands.py` (25), `mylo/tests/test_bot.py`.
