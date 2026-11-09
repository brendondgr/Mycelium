# Agent

Mylo as a conversational agent. A person asks a question in a thread (personal,
or opened in a lab, department or project); Mylo answers by calling read-only
functions over everything that person may see — their profile and what Mylo
understands about them, labs, projects and their state, feeds and slates, the
corpus, the knowledge graph, stored papers and uploaded files — and cites what
it read as `#n`. It changes nothing a person would call theirs. Backend only:
the API and a developer CLI; the web chat UI and Discord come next.

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
- **The turn.** `loop.py`: resolve pending calls, step cap, compaction
  (`compaction.py`), thrash guard, one model call (`llmcall.py`, with the
  local-model repairs), then the citation check (`verify.py`) on a final
  answer. Everything is an `AgentEvent`; streaming is Redis pub/sub
  (`stream.py`, SSE at `threads/<id>/stream/`).
- **Memory.** The profile block and scope block (`memory.py`), per-message
  recall stored as a `recall` event (`recall.py`), titles, purposes and
  digests after a turn (`memory_after.py`), and the learning pass
  (`learning.py`) that hands a quiet thread's own words to ambient as the
  `agent_chat` source through the `agent.thread_quiet` event — on unless the
  person opted out (D-3).
- **No model, no failure.** With no `LLM_MODEL` the tool still loads; the API
  answers `no_model` with a fix.

## Doors

- `service.py` — threads (create, list, update, delete, fork, export), send
  (queue, steer), answer, cancel, subscribe, preferences, org policy, catalog,
  status. Surfaces reach it with `tools._framework.services.get("agent")`.
- `read.py` — `thread_count`, `learning_enabled_for`.
- `events.py` — `agent.thread_quiet`.

## Operating it

- `manage.py agent chat --user <name> [--scope lab:<slug>|project:<uuid>]` —
  chat from the terminal (audited as `surface=cli`); `manage.py agent catalog
  --user <name>` shows what that person may use and why not.
- The output cap is off by default (`max_output_tokens = 0`); the context
  window is `context_window` (default 32768) because the endpoint does not
  report it.

## Tests

`uv run --directory web/backend pytest -c pyproject.toml ../../tools/agent`
(needs the Compose Postgres). The permission matrix's golden is
`tests/golden/catalog.txt`; rewrite it with `AGENT_GOLDEN_WRITE=1` and review
the diff.
