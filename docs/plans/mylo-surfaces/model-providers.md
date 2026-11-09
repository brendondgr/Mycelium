# Plan P: model servers

Index, owner decisions and sequencing: [README.md](README.md).

## Objective

Let the host point Mycelium at any of the common language-model servers
(OpenAI, Anthropic, Gemini, and anything OpenAI-compatible: vLLM, llama.cpp,
Ollama, LM Studio, DeepSeek, Azure) instead of only the one local endpoint in
`.env`. The local model stays the default and stays in use: this plan makes
other servers available, it does not switch to one (S-13). Mylo's chat is the
first component that can use another server; every other component can be
pointed at one later without new code (S-2).

The model layer comes from the `llm-integration` skill
(`/home/bdgr/Projects/bdgrClaudeSkills/llm-integration/`), whose `llmkit`
package already solves discovery, capability detection, error classes, retry
and the three wire formats.

## Where things stand

- `web/backend/apps/core/llm.py` is one OpenAI-chat client. `build_llm_client(component=…)`
  uses the same `LLM_BASE_URL`, `LLM_API_KEY` and `LLM_MODEL` for all 23
  components; `component` only labels the usage ledger (`LLMUsageDaily`).
- The endpoint is configured by bare env vars in `config/settings.py`
  (`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_TIMEOUT`,
  `LLM_CONNECT_TIMEOUT`, `LLM_MAX_RETRIES`, `LLM_TEMPERATURE`, `LLM_REASONING`,
  `LLM_REASONING_STYLE`, `LLM_THINKING_BUDGET`). `mycelium.toml` holds only
  `llm.max_tokens`.
- The agent already isolates the model behind a port:
  `tools/agent/llmcall.py::default_port()` calls
  `build_llm_client(component="agent").complete_stream(...)`.
  `[tools.agent] model` overrides the model name on the same endpoint.
  `[tools.agent] context_window` is a hand-set number because the endpoint does
  not report it.
- `tools/agent/rebuild.py::messages()` produces OpenAI-shaped message dicts
  from the event log.

## Design

### Configuration

Servers are declared in `mycelium.toml`. Keys never are: a server names the
env var that holds its key, and the key lives in `.env`.

```toml
[llm]
max_tokens = 0
default = "local"        # the server every component uses unless routed
allow_cloud = false      # a cloud server does not load until this is true
fallback = []            # servers tried, in order, when the routed one is down

[llm.providers.local]    # written by `make setup` from LLM_BASE_URL / LLM_MODEL
kind = "openai_compatible"   # openai | anthropic | gemini | openai_compatible | ollama
base_url = "http://host.docker.internal:8000/v1"
api_key_env = "LLM_API_KEY"
model = "…"
label = "Local model"

[llm.providers.claude]
kind = "anthropic"
api_key_env = "ANTHROPIC_API_KEY"
model = "…"              # chosen from what the server lists; never hardcoded in code
enabled = false

[llm.routes]
agent = "local"          # component -> "server" or "server:model"
```

- **Nothing changes for an existing install.** With no `[llm.providers]`
  section, a server named `local` is synthesised from the `LLM_*` env vars, and
  every component routes to it.
- `[llm.providers.<name>]` is a dynamic section, resolved the way
  `[tools.<name>]` sections are today (`config/instance.py::_resolve_tool_sections`).
  Per-server fields: `kind`, `base_url`, `api_key_env`, `model`, `label`,
  `enabled`, `location`, `timeout`, `connect_timeout`, `context_window`,
  `reasoning`, `model_allow`, `model_deny`.
- `location` is `local`, `remote` or `cloud`. It is derived (kind `openai`,
  `anthropic`, `gemini` and known public hosts are `cloud`; loopback, private
  ranges and `host.docker.internal` are `local`; anything else is `remote`) and
  the host may state it. It drives the "where it runs" line (S-3).
- `llm.allow_cloud` is the single cloud switch. A `cloud` server with the
  switch off is reported as a config problem and never called.
- `[tools.agent] model` keeps working: it overrides the model of whichever
  server `llm.routes.agent` names.
- `ops/mycelium config` validates the section: unknown kind, missing
  `base_url` for a kind that needs one, `api_key_env` naming an unset variable,
  a route to an unknown or disabled server, a cloud server while
  `allow_cloud = false`.
- Server URLs come from this file only. No route, form or function accepts a
  URL from a user, so the server-side request forgery risk the skill warns
  about does not arise (S-1).

### Code layout

```
web/backend/apps/core/
  llmkit/            vendored from the skill's templates/llmkit (types, base, config,
                     registry, discovery, retry, errors, params, providers/*).
                     agent.py is not copied: Mycelium has its own loop.
  llm_servers.py     builds the llmkit Registry from mycelium.toml; resolve(component)
                     -> Route(server, kind, model, label, location); discovery cache;
                     health; never raises
  llm_bridge.py      KitClient: the same complete() / complete_stream() surface as
                     LLMClient, backed by an llmkit provider; translates messages,
                     tools, usage and errors at this one boundary
  llm.py             build_llm_client(component=…) asks llm_servers for the route and
                     returns LLMClient (OpenAI-compatible kinds) or KitClient (others)
```

- **OpenAI-compatible servers keep the existing `LLMClient`.** It carries the
  reasoning-style handling and the behaviour the 23 components were tuned on;
  routing only changes which base URL, key and model it is built with. `llmkit`
  serves these servers for discovery and health only.
- **Anthropic, Gemini and native Ollama go through `KitClient`.** Feature code
  never tests the server kind; the difference ends at `llm_bridge.py`.
- `llmkit` is vendored, not installed: `apps/core/llmkit/VENDORED.md` records
  the skill commit it was copied from and the one local change (import paths).
  The skill's `scripts/selftest.py` (130 offline checks against mock servers) is
  copied beside it and run by `apps/core/test_llmkit.py`, so it is part of
  `make test`.
- New dependencies in `web/backend/pyproject.toml`: `httpx` (pinned direct; it
  is already present through `openai`), `anthropic`, `google-genai`. They are
  ordinary dependencies, not an extra, because a plain `uv run` strips extras
  on this project. Both SDKs are imported lazily; a missing one is a reported
  problem, not an import error at start.

### What the bridge must get right

| Concern | Rule |
| --- | --- |
| Messages | OpenAI-shaped dicts in, `llmkit.Message` out. System text is hoisted for Anthropic and Gemini. Tool results follow the call they answer. |
| Tools | Function schemas pass through `harden_schema`. Tool calls come back fully assembled; arguments are re-serialised to the JSON string `LLMResponse.tool_calls` expects. |
| Opaque state | Anthropic thinking signatures, Gemini thought signatures and OpenAI encrypted reasoning are returned verbatim in `LLMResponse.opaque` and never parsed. See "Agent wiring". |
| Streaming | `StreamChunk` text and thinking map to `on_delta(kind, text)`; `should_stop()` closes the stream; exactly one final response. |
| Reasoning | `LLM_REASONING` levels map to `GenParams.reasoning_effort` through `snap_effort`. A server with no reasoning ignores it. |
| Usage | `llmkit.Usage` maps to the ledger's token counts using `billable_input_tokens`, so cached tokens are not counted twice. |
| Errors | `llmkit` error classes map to the errors `llm.py` raises today. `ContextLengthError` reaches the agent as the signal to compact. |
| Timeouts | Connect and read timeouts stay separate, per server. |

### Discovery and health

- `llm_servers.options()` returns, per server, without raising:
  `{server, label, kind, location, ok, error, cached, default, models:[{id, label, context_window, capabilities, loaded}]}`.
  An unreachable local server is a normal state: `ok: false` with the reason.
- Results are cached (`ModelCache`, 300 s; 15 s after an error) and warmed once
  at worker start.
- A server's context window comes from discovery (llama.cpp `/props`, Ollama
  `/api/show`, Anthropic's reported limit) unless `context_window` is set.
- `manage.py llm_check` lists every server, its health, the models it reports
  and the route of each component, then pings each enabled server with
  component `preflight`. `--strict` fails on any problem.
- `manage.py llm_probe <server> [--deep]` runs the skill's `scripts/probe.py`
  against one configured server (chat, streaming, tools, structured output).

### Fallback

`llm.fallback` is empty by default. When set, a call whose server is down
(circuit open after three failures, 30 s) tries the listed servers in order.
The served server is recorded on the response and in the ledger. A local
server never falls back to a cloud one unless the host listed it (S-14), and
a listed cloud server is still skipped while `llm.allow_cloud` is false.

### Agent wiring

- `tools/agent/llmcall.py::model_name()` and `default_port()` resolve
  `llm_servers.resolve("agent")`. The route is fixed for the length of a turn
  and written into the turn's `assistant` events as `{name, label, location}`
  (shared contract S3).
- `[tools.agent] context_window` default changes from `32768` to `0`, meaning
  "ask discovery, fall back to 32768". A stated value still wins.
- The `thinking` event payload gains `opaque: {kind, blocks}` when the server
  returned opaque reasoning state. `rebuild.messages()` returns it to the
  server only when the next call goes to the same server kind, and drops it
  otherwise. The activity view (S1) never carries it.
- The local-model repairs in `llmcall.parse` (leaked tool-call text, loose
  JSON, runaway repetition, empty-reply retry) stay on for every server. They
  do nothing when the reply is well formed.
- `tools/agent/health.py` reports the agent's server, its location and whether
  it answers.

### Usage ledger

`LLMUsageDaily` gains `server` (default `"local"`) in its uniqueness key, so a
component's spend is readable per server. `llm_usage.record(...)` takes
`server=`. No price table and no spend cap (S-13): `[tools.agent] daily_turns`
is the only brake, and it is off by default.

## Phases

### P1. Vendor `llmkit` and the config section

Copy `llmkit`; add the selftest; add `[llm] default / allow_cloud / fallback`,
`[llm.routes]` and the dynamic `[llm.providers.<name>]` section to
`config/instance.py`; synthesise `local` from the env; extend
`ops/mycelium config` validation and the rendered `mycelium.toml`; add the
dependencies.

```bash
cd web/backend && uv run --no-sync pytest -c pyproject.toml apps/core/test_llmkit.py apps/core/test_instance_config.py apps/core/test_config_cli.py -q
ops/mycelium config validate
```

Accept when: the selftest passes inside the repo; an install with no
`[llm.providers]` resolves exactly one server equal to today's env; each bad
configuration above is reported by name; no key appears in any rendered or
printed config.

### P2. Registry, discovery, health

`llm_servers.py`; the extended `llm_check`; `llm_probe`.

```bash
uv run --no-sync pytest -c pyproject.toml apps/core/test_llm_servers.py -q
uv run --no-sync python manage.py llm_check
```

Accept when: against mock servers of each kind, `options()` lists models and
context windows; a dead server yields `ok: false` within the connect timeout
and does not slow the others; the cache is used on the second call.

### P3. Routing and the bridge

`llm_bridge.py`; `build_llm_client` routes by component; fallback; the ledger
column and its migration (`core`).

```bash
uv run --no-sync pytest -c pyproject.toml apps/core -q
make test
```

Accept when: with the default config every existing test passes unchanged; a
component routed to a mock Anthropic and a mock Gemini server completes a
tool-call round trip and a streamed reply through `complete_stream`; opaque
state returns byte-identical; a routed server that is down falls back only as
listed and the ledger names the server that served.

### P4. Agent wiring (after Discord phase D1; see README)

`llmcall.py`, `rebuild.py`, `health.py`, `tool.py` (context window default),
status payload.

```bash
uv run --no-sync pytest -c pyproject.toml ../../tools/agent/tests -q
uv run --no-sync python ../../tools/_framework/golden.py write
make tools-check
```

Accept when: an agent turn with two function calls completes against each mock
server kind; the turn's events carry the server and location; switching
`llm.routes.agent` between turns of one thread works and drops the other
server's opaque state; context-length errors trigger compaction.

### P5. Operator view, docs, live checks

- `GET api/admin/llm/servers/` (staff only, read-only): the `options()` payload
  plus each component's route. HTTP 200 with `ok: false` for a dead server.
  The admin page that draws it is not part of this plan.
- `docs/skills/configure.md` (how to add a server, where keys go, the cloud
  switch), `docs/architecture.md`, `docs/repo-map.md`, `.env.example` (key
  variable names only), `tools/agent/README.md`.
- Live check of each server the host actually configures:
  `manage.py llm_probe <server> --deep`.
- Any comparison of servers on the agent baseline (EXP-2026-11-011) is a new
  experiment under `docs/research/experiments/`, scaffolded with
  `make new-experiment`.

Accept when: `make validate-research` and `make test` pass; the probe passes
for the local server and for one cloud server on a throwaway key; the chat
status line reads correctly for a local and a cloud route.

## Interfaces that change

| Kind | Change |
| --- | --- |
| Config | `[llm] default, allow_cloud, fallback`; `[llm.routes]`; `[llm.providers.<name>]`; `[tools.agent] context_window` default `0` |
| Env | Key variables named by `api_key_env` (for example `ANTHROPIC_API_KEY`); the `LLM_*` variables keep working |
| Commands | `llm_check` (extended), `llm_probe` (new) |
| Routes | `GET api/admin/llm/servers/`; `GET api/tools/agent/status/` gains `model.label`, `model.location` |
| Schema | `core`: `LLMUsageDaily.server`. `agent`: none (payload fields only) |
| Python | `LLMResponse.opaque`, `.server`; `apps.core.llm_servers`; `apps.core.llm_bridge` |

## Security and data

- Keys: env only, named by `api_key_env`; `ProviderConfig.redacted()` in every
  log, health line and API payload.
- Data leaving the host: only when `llm.allow_cloud = true` and a route names a
  cloud server. `llm_check`, the agent's health line, the web chat and Discord
  all state the location.
- The admin route is staff-only and read-only. Changing servers means editing
  `mycelium.toml` on the host.
- Tier gate: none new. Chat stays behind the existing `agent` entitlement.
- Background work: none new. Discovery warms in the web and Celery workers at
  start; nothing joins `mylo-daily.timer`.

## Exclusions

- Moving any nightly component off the local model. The routing exists; using
  it for `papers`, `briefing` and the rest is a later, per-component decision
  with its own validation.
- Embeddings. Retrieval keeps its local fastembed models.
- The decision port (`decision.*`), which stays as it is.
- A model menu, personal keys, per-org model choice, prices or spend caps.
- Rewriting `LLMClient` onto `llmkit` for OpenAI-compatible servers.
