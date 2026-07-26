# Phase E — Drift detection and portal health

**Status:** As built.
**Correlation ID:** `20260726-mylo-discord-drift`
**Umbrella:** [`mylo-discord-pipeline.md`](mylo-discord-pipeline.md)

## Objective

Notice when Discord changes underneath us, and let a lab lead see *why* nothing is
arriving.

## Decisions

| # | Decision | Why |
|---|---|---|
| E-a | **Three detection sources**: live gateway events, the nightly sweep, permanent outbox failures. | None is reliable alone. Events are lost across restarts, deploys and gateway disconnects; the sweep is up to a day stale; the outbox is often *first* to learn a channel is gone. |
| E-b | **`on_member_remove` is not used** (closes Q-4). | It needs the privileged Server Members intent — a Developer-Portal toggle plus verification review past 100 guilds. That is an external approval dependency, not a code change. Member drift is REST-side in the sweep instead. |
| E-c | **Channel liveness by channel list, not by posting.** | `preflight_channel` proving postability with a real message is right at bind time, when an admin is watching and wants proof, and wrong nightly — it would post into every lab's channel every night. |
| E-d | **The sweep re-checks the bot add-on.** | The hole the brief named: verified once at install and never again, so a lab that stopped paying kept receiving delivery indefinitely. |
| E-e | **`linked` and `dm_ok` stay independent of guild membership.** | A personal DM works through the person's own installation. Someone who left the server still gets reminders; they just cannot be tagged. Conflating them would tell people their reminders are broken when they are not. |
| E-f | **One health endpoint, not three.** | A lab lead asking "why is nobody getting anything?" needs guild, channels, add-on and roster together, because the cause could be any of them and the useful answer names which. |
| E-g | **A lapsed add-on pauses and explains** (L6). | Nothing removed, bindings kept, commands still work. |

## Where it lives

`mylo/bot/cogs/drift.py`, `integrations/services/reconcile.py::_reconcile_guild_health`,
`DiscordGuildLink.{announcement_channel_ok,updates_channel_ok,channel_checked_at,last_error_code,addon_ok}`
(migration `integrations/0006`), `DiscordHealthView` → `GET /api/integrations/discord/health?lab=`,
`web/app/src/components/portal/sections/discord-health-card.tsx`.

## Known gap

`ReminderSubscription.has_unlinked_targets` is still not rendered anywhere — there is
no reminder-management UI to hang it on. E-7 in the umbrella remains open; the
health card covers the same question at the roster level.
