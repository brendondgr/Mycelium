# Agent

Mylo as a conversational agent. A person asks a question in a thread (personal,
or opened in a lab, department or project); Mylo answers by calling read-only
functions over everything that person may see — their profile and what Mylo
understands about them, labs, projects and their state, feeds and slates, the
corpus, the knowledge graph, stored papers and uploaded files — and cites what
it read as `#n`. It changes nothing a person would call theirs. Surfaces:
the API, a developer CLI, the web chat panel and Discord.

| | |
|---|---|
| Depends on | `retrieval`, `recommendation` (both core) |
| Exports | `read`, `service`, `events` |
| Config | `[tools.agent]` in `mycelium.toml` (on by default) |
| Nightly stages | — (Beat: learning pass every 10 min, resume sweep, retention sweep) |
| API | `api/tools/agent/` (see `docs/api-contract.md`) |

## How it fits together

- **Two switches (D-5).** The host turns the agent on or off for everyone
  (`[tools.agent] enabled`); each person turns it on or off for themselves
  (`AgentPreference`). An org's `AgentOrgPolicy` can only narrow (groups off,
  Discord channels off), never switch the agent on or off.
- **The one gate.** `permissions.decide(caller, function, args)` checks nine
  layers (loaded, instance, features/entitlements, org policy, scope and role,
  object arguments, person, risk, audience) for the catalog the model sees and
  again for every call. Surfaces (`surfaces/web.py`, `surfaces/cli.py`) only
  build the `Caller`.
- **Functions come from tools.** Any loaded tool contributes functions and
  reference kinds through `Tool.agent` (`tools/_framework/agentspec.py`); the
  agent's own are in `functions/`. Only `read` functions load.
- **Lists say whether they are complete.** The feed functions (`feeds_slate`,
  `feeds_saved`, `feeds_deadlines`, `projects_feed`) share `functions/lists.py`:
  a deadline filter (`due_from`, `due_to`, `deadline`, `types`) is applied in
  the database to the whole slate before anything is cut, a long result pages
  with `offset`, rows fit the `result_cap_tokens` budget, and the last line of
  every result says either that the list is complete ("all 4 of 4") or how to
  get the rest ("only the first 20 of 36 …; pass offset=20"). With no first
  day a window opens today, and a conference's own dates are a deadline only
  when asked for (`deadline="event"`). Nothing here ranks.
- **The turn.** `loop.py`: resolve pending calls, step cap, compaction
  (`compaction.py`), thrash guard, one model call (`llmcall.py`, with the
  local-model repairs), then the checks on a final answer (`verify.py`):
  every citation must match something surfaced, an item cited but not read
  in view must be read, and every concrete detail (an `Authors:`/`Venue:`/
  `DOI:`/date/amount line, a DOI, a measured figure) must appear in what was
  read. One repair is asked for with functions still on; what stays unbacked
  is removed and the person told. A reply that loops (`runaway_cut`) is
  thrown away and retried once, then replaced by a plain "I got stuck" line. Everything is an `AgentEvent`; streaming is Redis pub/sub
  (`stream.py`, SSE at `threads/<id>/stream/`).
- **Malformed calls are not failures.** A function that fails twice in a turn
  is not run a third time (`FAILURE_LIMIT`). A call whose arguments were
  malformed — a name the function does not take, a required one left out, a
  value in the wrong form (`bad_arguments`, `need_*`) — is counted apart, up to
  `MALFORMED_LIMIT` per function and turn, so the corrected call still runs.
  `dispatch.py` checks a call's arguments against the function's schema after
  the gate has allowed it, and the error names what the function accepts.
- **What a person sees.** `activity.py` projects the log into the activity
  view: no thinking text, each call shown only as its function's `activity`
  label (every `AgentFunction` declares one; a framework test fails one that
  does not), no arguments or results. `stream.follow(view=...)` applies it;
  the HTTP routes default to it, and the raw view is for the CLI, export and
  staff.
- **A conversation about one thing.** A thread created with an `anchor`
  (`settings["anchor"] = {kind, key}`, never changed) holds it as reference
  `#1`; `prompt.py` resolves it for the current caller every turn
  (`refs.resolve_anchor`) and says "This conversation is about #1", or leaves
  it out, title included, for a caller who cannot see it.
- **Memory.** The profile block and scope block (`memory.py`), per-message
  recall stored as a `recall` event (`recall.py`), titles, purposes and
  digests after a turn (`memory_after.py`), and the learning pass
  (`learning.py`) that hands a quiet thread's own words to ambient as the
  `agent_chat` source through the `agent.thread_quiet` event — on unless the
  person opted out (D-3).
- **No model, no failure.** With no `LLM_MODEL` the tool still loads; the API
  answers `no_model` with a fix.
- **Which model answers.** Chat is component `agent`: it goes to the server
  `[llm.routes] agent` names (default: `local`, the `.env` endpoint), and
  `[tools.agent] model` overrides that server's model. The route is fixed for
  a turn (`llmcall.default_port`). `llmcall.model_info()` is `{name, label,
  location}` (`local`, `remote` or `cloud`; `label` is the server's label when
  the host gave one, else the model name); `service.status()` returns it and
  every `assistant` event records it (S-3). `health.report()` adds whether the
  server answers.
- **Reasoning state stays with its server.** Anthropic thinking signatures and
  Gemini thought signatures are kept on the `thinking` event as `opaque`;
  `rebuild.messages()` hands them back only to a server of the same kind and
  drops them when the route changes. The activity view never shows them.
- **A context overflow compacts.** If the server rejects a prompt as too long,
  the turn clears old results or summarizes once and retries.
- **Pinned chats.** `AgentThread.pinned`; `list_threads` puts them first.

- **Discord (plan D).** `surfaces/discord.py` is the adapter the bot
  (`mylo/`) calls through `services.get("agent").discord_surface()`: `ask`
  runs the Discord gate, resolves the place (`resolve.place_for`), finds or
  opens the conversation (`AgentThreadLink`), builds the `Caller` and calls
  `service.send`; `follow`, `result`, `stop`, `forget` and `reconcile` serve
  delivery and recovery (`AgentDiscordTurn`). A DM is the person's own
  thread. A forum or Discord thread is one **shared** thread (no owner;
  `AgentThread.shared`) where each question is a turn under its own asker
  (`speaker` and `turn` on the `user` event; `caller.for_turn`), queued
  questions get one turn each (at most five wait). An earlier turn replays in
  full when the person asking now asked it, or when every lookup in it came
  from a function whose `output` is `instance` (the same for anyone: the
  corpus, function loading, skills) and names only objects visible to them
  (`rebuild._replayed`); otherwise as a transcript only, so a lookup written
  for one person never reaches another. An open channel has one
  shared-type thread per person, rolled over after
  `discord_channel_session_hours`. A question that replies to one of Mylo's
  answers (any of its messages: `AgentDiscordTurn.status_message_id` and
  `message_ids`) or to the question it answered continues that conversation,
  whoever asked it. `/mylo new` closes the caller's open conversation in the
  place (`new_conversation`) without deleting it. Shared threads are never
  returned by the web API and are skipped by the learning pass, recall,
  digests and titles.
- **Guests.** Someone in a bound server without an account is a `Guest`
  (`Caller.user is None`). They stand where a `member` of the place's lab or
  department stands, but only for functions that declare a guest level
  (`AgentFunction.guest`: `public`, `no_people`, `full`), capped by
  `discord_guest_level` and the org's `AgentOrgPolicy.discord_guests`
  (`permissions.guest_level`). The host ceiling defaults to `full`; an org
  that has not chosen (`discord_guests = ""`) gives guests `public` only, so
  nobody without an account can list a lab's people until the lab raises it.
  The daily limits default to none. What a guest still lacks at `full` needs an account to mean
  anything (their own profile, saves, files, earlier conversations,
  introductions) or a viewer the knowledge app can check (a project's
  concepts). A guest is never learned from.

## Doors

- `service.py` — threads (create, list, update, delete, fork, export), send
  (queue, steer), answer, cancel, subscribe, preferences, org policy, catalog,
  status. Surfaces reach it with `tools._framework.services.get("agent")`.
- `read.py` — `thread_count`, `learning_enabled_for`.
- `events.py` — `agent.thread_quiet`.

## Operating it

- `manage.py smoke_agent_discord [--scripted] [--keep]` — Mylo in Discord end
  to end against a fake transport (member and guest in an announcement
  thread, a DM, the refusals); the real model unless `--scripted`; rolled back.
- `manage.py agent chat --user <name> [--scope lab:<slug>|project:<uuid>]` —
  chat from the terminal (audited as `surface=cli`); `manage.py agent catalog
  --user <name>` shows what that person may use and why not.
- Each chat call is capped (Q-078): `max_output_tokens` (default 4096) for
  the whole reply, thinking included, and `thinking_budget` (default 512) for
  the thinking alone on servers that take vLLM's `thinking_token_budget`. A
  reply cut off at the cap is asked for again, shorter; an empty one gets one
  more try and then an honest line, never a blank (Q-070). The context
  window is `context_window` when set; at its default `0` it is what the
  model server reports (vLLM, llama.cpp, Ollama, Anthropic, Gemini), else
  32768.
- Model servers are the host's choice in `mycelium.toml`
  (`docs/skills/configure.md`, "Model servers"); `manage.py llm_check` lists
  them and their routes, `manage.py llm_probe <server> --deep` tests one.

## Tests

`uv run --directory web/backend pytest -c pyproject.toml ../../tools/agent`
(needs the Compose Postgres). The permission matrix's golden is
`tests/golden/catalog.txt`; rewrite it with `AGENT_GOLDEN_WRITE=1` and review
the diff.
