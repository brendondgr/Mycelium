# Mylo surfaces: model servers, web chat, Discord

Three plans that put the agent built in `tools/agent/` in front of people. They
share one rule: **the web app and Discord run the same agent and differ only in
how they draw it.** A surface authenticates someone, builds a `Caller`, calls
`service.send`, and renders the event stream. It holds no permission logic and
no prompt logic (`docs/plans/mylo-agent/permissions.md`, "Surfaces").

| Plan | File | Detail |
| --- | --- | --- |
| P. Model servers | Shipped 2026-11-09; plan deleted. How to configure: `docs/skills/configure.md` ("Model servers"); code: `apps/core/llm_servers.py`, `llm_bridge.py`, `llmkit/` | Done |
| D. Mylo in Discord | [discord.md](discord.md) | Full |
| W. Mylo chat in the web app | [web-chat.md](web-chat.md) | Entry points and placement fixed against the reworked workspace; visual detail is settled while building |

Track S (the shared contract below) and plan P (model servers) have shipped;
D and W are not built.
The agent backend these plans stand on is on `main` (`dc2c76f`); its own plan
is `docs/plans/mylo-agent/`.

## Owner decisions (2026-11-09)

| # | Decision |
| --- | --- |
| S-1 | **The host chooses the model.** Servers are listed in `mycelium.toml`; one is the default. No per-person model menu and no personal API keys. |
| S-2 | **Chat first, others ready.** The server registry lives in the shared core so any component can be pointed at any server, but only Mylo's chat is switched over. The nightly pipeline stays on the local model. |
| S-3 | **Cloud is the host's call, and the chat says where it runs.** Cloud servers are off until the host turns one on. Web and Discord state which model answers and whether it runs on this machine. No extra org or personal switch. |
| S-4 | **Discord trigger: `@Mylo`, a reply to Mylo, or a DM.** No "Hey Mylo" text trigger and no Message Content intent. Mylo reads only what is addressed to it, plus its own posts. |
| S-5 | **Who may ask in Discord is configurable; public for now.** One host setting chooses between anyone in a bound server, linked accounts only, or linked accounts on a paid plan. |
| S-6 | **Memory: shared in threads, per person in channels.** A forum or Discord thread is one conversation that remembers each person who asked. In an open channel each person has their own. |
| S-7 | **Learning from Discord:** a DM is treated like web chat (on by default, the person can opt out). A question in a shared place is learned from only under the existing Discord listening consent. People without an account are never learned from. |
| S-8 | **Web panel icons:** history, new chat, pin a chat. No per-answer bookmarks. |
| S-9 | **Mylo never shows its thinking.** Both surfaces show what Mylo is doing ("Reading the call", "Looking at your projects"), never the reasoning text. |
| S-10 | **A DM needs an activated account.** A linked Mycelium account with a verified email. There are no guests in DMs. |
| S-11 | **In a bound server, being there is enough.** Anyone who can post in a server that an activated lab or department has connected may ask Mylo there, with or without an account, and is answered there. Guest limits (10 a day per person, 200 a day per server) are settings. |
| S-12 | **Mylo pings only for a slow answer.** A normal answer replaces the status message silently. An answer that took longer than about ten minutes (a setting) is posted as a new reply that mentions the asker and nobody else. |
| S-13 | **No spend cap.** Other model servers are made available, not switched on; the instance keeps using its local model. Tokens are recorded per server. |
| S-14 | **No fallback from a local server to a cloud one** unless the host lists that server in `llm.fallback`. |
| S-15 | **"Ask Mylo" is a small button with Mylo's face** on each thing (feed cards, the opened item, project and lab pages). Pressing it opens the side panel on a conversation about that thing. |
| S-16 | **Being in a bound server is trust.** A guest is told what a lab member would be told in that place, named people included (members, a member's declared profile, who could go after a call). Two settings can narrow it, a host ceiling and a level per lab: `full` (default), `no_people`, `public`, `off`. |

## Shared contract (track S) — shipped

Built once in `tools/agent/`; both surfaces rely on it. The full shapes are
in `docs/api-contract.md` (Mylo agent); this is what a surface needs.

**S1. Activity view (S-9).** `tools/agent/activity.py` decides what a
surface may show. `stream.follow(thread, view="activity" | "raw")` (default
`raw`, for the CLI); `service.subscribe(caller, thread, view=...)` and
`service.thread_events(caller, thread, after=, view=...)` default to
`activity`; the `events/` and `stream/` routes take `?view=` (default
`activity`; `raw` is 403 `raw_view_staff_only` unless the user is staff or
the surface is the CLI). In the activity view:

- thinking → `{type: "activity", payload: {state: "thinking"}}`, once per run
  of thinking, no text;
- each call → `{type: "activity", payload: {state: "running", label, call_id,
  name}}`, closed by the same with `state: "ok"` or `"failed"`. Labels come
  from `AgentFunction.activity` (every function declares one; ref slots show
  the object's title, never its id). Arguments and results are never sent;
- `assistant` keeps `text`, `final`, `partial`, `removed`, `model`; empty
  intermediate steps, `usage`, `recall`, `verdict`, `compact`, `progress`
  and notes meant for the model are dropped; the rest passes through.

Stored-event messages keep their `id`, so `Last-Event-ID` still works.

**S2. Anchor.** `POST threads/` takes `anchor: {kind, key}` (or
`"kind:key"`; any registered reference kind) → `settings["anchor"]`, never
changed, reference `#1`. Each turn resolves it for the current caller and
audience (`refs.resolve_anchor`); if they cannot see it the turn runs without
it, title included. `GET threads/?anchor=kind:key` finds the conversations
already open about a thing; thread JSON carries `anchor` (or null). In code:
`service.create_thread(user, scope=, surface=, anchor=)`,
`service.list_threads(user, anchor=)`.

**S3. Pinned and the model.** `AgentThread.pinned` (agent migration
`0002_thread_pinned`); `PATCH threads/<id>/ {pinned}`; lists are pinned
first. `GET status/` and `service.status()` return `{model: {name, label,
location}}` (filled from the server `[llm.routes] agent` names since plan P;
`label` is the server's label when the host set one, else the model name), and
every `assistant` event's payload has the same `model` object.

## How the three plans run together

```
S  (shared contract) ──┬──> D1 → D2 → D3 → D4 → D5      Discord
                       └──> W1 → W2 → W3 → W4 → W5      Web
P1 → P2 → P3 ─────────────> P4 → P5                     Model servers (shipped)
```

- **P shipped before D1.** P4 changed `tools/agent/llmcall.py`, `rebuild.py`
  (opaque reasoning state on the `thinking` event, replayed to the same server
  kind only), `loop.py` (a context-length error compacts once and retries),
  `compaction.py` and `health.py`; D1 builds on those. P added no agent
  migration, so D1 still takes `0003`.
- **S before D1 and W1** (S is on `main`). S added agent migration `0002`;
  D1 adds `0003`.
- **W touches only `web/app/`** once S has landed, so it can run in parallel
  with D and P. W3 edits the two feed files other front-end work also edits
  (`feed/opportunity-feed.tsx`, `sections/research-papers-section.tsx`); merge
  `main` in first.
- **D does not depend on P.** Discord works on the local model as it is.
- Each track is built in its own git worktree (other sessions share the main
  checkout), branched after merging local `main` in.

Shortest path to something usable: S → D1–D3 (Mylo answers in Discord on the
local model), with P1–P3 alongside.

## Open questions

Three remain. Each has the answer the plans assume; none blocks a start.

1. **Should a shared Discord conversation be readable in the web app** by the
   lab's members [after D5]? Assumed: no, not in this release.
2. **Should a member be able to keep themself out of what guests are told**
   [D1]? Assumed: no new switch. A guest sees about a person only what a lab
   member already sees in that channel, which is what the person declared.
   The host and the lab can lower the guest level for everyone (S-16).
3. **Keep the bottom-right launcher as well as the Mylo-face buttons** [W2]?
   Assumed: yes. The buttons ask about one thing; the launcher is the way to
   ask about anything else.

## Exclusions common to all three

- No function that changes anything. The agent stays read-only (`max_risk =
  "read"`).
- No per-person model choice, no personal API keys, no URL typed by a user
  anywhere (S-1). Server URLs come only from `mycelium.toml`.
- No "Hey Mylo" trigger and no reading of messages not addressed to Mylo (S-4).
- No Slack or Teams surface.
- No change to the nightly pipeline's model, cadence or ranking.
- Provider comparisons are evaluations: any number from one is recorded under
  `docs/research/experiments/` first (`docs/research/AGENT_INSTRUCTIONS.md`).

## When these ship

Delete the plan that shipped. Record the outcome in `docs/changelog.md`, and
update `docs/repo-map.md`, `docs/api-contract.md`, `docs/architecture.md`,
`docs/skills/configure.md` and `tools/agent/README.md` in the same change.
