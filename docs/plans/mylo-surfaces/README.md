# Mylo surfaces: model servers, web chat, Discord

Three plans that put the agent built in `tools/agent/` in front of people. They
share one rule: **the web app and Discord run the same agent and differ only in
how they draw it.** A surface authenticates someone, builds a `Caller`, calls
`service.send`, and renders the event stream. It holds no permission logic and
no prompt logic (`docs/plans/mylo-agent/permissions.md`, "Surfaces").

| Plan | File | Detail |
| --- | --- | --- |
| P. Model servers | [model-providers.md](model-providers.md) | Full |
| D. Mylo in Discord | [discord.md](discord.md) | Full |
| W. Mylo chat in the web app | [web-chat.md](web-chat.md) | Entry points and placement fixed against the reworked workspace; visual detail is settled while building |

Nothing here is built. The agent backend these plans stand on is on `main`
(`dc2c76f`); its own plan is `docs/plans/mylo-agent/`.

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

## Shared contract (track S)

Small backend changes both surfaces need. They are built once, in
`tools/agent/`, before either surface draws anything.

### S1. Activity view: what Mylo is doing, without the thinking

- `AgentFunction` (`tools/_framework/agentspec.py`) gains `activity: str`, a
  short present-tense label with optional argument slots, for example
  `"Searching the corpus for “{query}”"`, `"Reading {ref}"`,
  `"Looking at your projects"`. Every function in `tools/agent/functions/` and
  every contributing tool (`fulltext`, `files`) declares one. A framework test
  fails a function with no label.
- New `tools/agent/activity.py`: `project(message) -> message | None` turns a
  stream message into its display form:
  - `thinking` events and `delta{kind:"thinking"}` become
    `{type:"activity", state:"thinking"}` with no text.
  - `tool_call` becomes `{type:"activity", state:"running", label, call_id}`;
    `tool_result` closes it with `ok` or `failed`. Arguments are not sent
    beyond what the label shows.
  - `assistant`, text deltas, `question`, `todos`, `error`, `state`, `note`
    pass through. `usage`, `recall`, `verdict`, `compact` are dropped.
- `stream.follow(..., view="activity")` applies the projection. The SSE route
  and the thread-events route default to `view=activity`. The raw view stays
  for the CLI surface and for `export`; over HTTP it needs staff.
- The projection is the only place that decides what a surface may show, so
  S-9 is enforced on the server, not by each renderer.

### S2. A conversation about one thing (anchor)

- `AgentThread.settings["anchor"] = {"kind", "key"}`, set at creation and never
  changed. `kind` is any registered reference kind (`item`, `project`, `lab`,
  `department`, and `announcement`, added by the Discord plan).
- At every turn the anchor is resolved **for the current caller** and placed as
  reference `#1`, with one prompt line: "This conversation is about #1." If the
  caller may not see it, the turn runs without it.
- `POST api/tools/agent/threads/` accepts `anchor`, and `GET threads/` filters
  by it (so the web can reopen the conversation already open about a thing).
  The web's Mylo-face button and a Discord forum thread both use it.

### S3. Pinned chats and where the model runs

- `AgentThread.pinned` (bool, default false). `PATCH threads/<id>/` accepts
  `pinned`; `list_threads` orders pinned first.
- `service.status()` and `GET api/tools/agent/status/` return
  `model: {name, label, location}` where `location` is `local`, `remote` or
  `cloud`. Until plan P lands, `location` is `local` and `label` is the model
  name. Each `assistant` event records the same three fields.

### Validation (track S)

```bash
cd web/backend && uv run --no-sync pytest -c pyproject.toml ../../tools/agent/tests ../../tools/_framework/tests -q
uv run --no-sync python ../../tools/_framework/golden.py write   # then review the diff
make tools-check
```

Accept when: a thread that used three functions streams three labelled activity
steps and no thinking text under `view=activity`; the raw view is refused to a
non-staff session; an anchored thread shows `#1` on every turn and drops it for
a caller who cannot see it; migration `agent 0002` (pinned) applies on the
Compose Postgres.

## How the three plans run together

```
S  (shared contract) ──┬──> D1 → D2 → D3 → D4 → D5      Discord
                       └──> W1 → W2 → W3 → W4 → W5      Web
P1 → P2 → P3 ─────────────> P4 → P5                     Model servers
```

- **P1–P3 touch only `web/backend/apps/core/` and `web/backend/config/`.** They
  can run in parallel with S and with D1–D3.
- **P4 edits `tools/agent/llmcall.py` and `rebuild.py`; D1 edits `rebuild.py`
  and `loop.py`.** These two phases are not run at the same time. Do D1 first,
  then P4.
- **S before D1 and W1.** S adds agent migration `0002`; D1 adds `0003`.
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
