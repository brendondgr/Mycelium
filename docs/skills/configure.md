# Configure a Mycelium instance

Use this skill when someone asks an agent to set up, configure, open up, lock
down, or troubleshoot the limits of **their own** Mycelium — "set this up for my
lab", "why can I only make three clusters", "let anyone at my university sign
up", "turn on email", "cap what the nightly run spends".

Everything an operator decides lives in one file, `mycelium.toml` at the repo
root, and one command changes it: `ops/mycelium config` (or
`make config ARGS="…"`). Do not edit Python, `settings.py`, or `.env.example` to
change a limit or a policy — that is exactly what this layer exists to prevent.

## How the configuration works

- **Four layers**, each overriding the one before: built-in defaults → the
  deployment **profile** → `mycelium.toml` → environment variables. `config
  show` prints every value and the layer it came from.
- **Profiles** are starting points, not modes:

  | Profile | For | Billing | Limits | Sign-up | Verify email |
  |---|---|---|---|---|---|
  | `personal` | one person | off | none | closed (admin makes accounts) | no |
  | `lab` (default) | one lab | off | none | invite | no |
  | `department` | several labs | off | none (suggested numbers in comments) | invite | no |
  | `institution` | a whole school | subscriptions | per tier | shared code | yes (Resend) |

- **Billing is a module.** `billing.mode = "off"` means no plans, tiers or seats
  exist as far as anyone can tell; `"subscriptions"` brings back tiered plans and
  the `[limits.tiers.*]` numbers.
- **Every limit is off until given a number.** `"unlimited"` or an integer;
  setting one key turns on that one limit and nothing else.
- **Secrets never go in the file**: `RESEND_API_KEY`, `EMAIL_HOST_PASSWORD`,
  `SIGNUP_ACCESS_CODE`, `LLM_API_KEY` live in `.env`. So do the full-text
  tool's publisher keys (`ELSEVIER_API_KEY`, `ELSEVIER_INST_TOKEN`,
  `SPRINGER_API_KEY`, `WILEY_TDM_TOKEN`, `CORE_API_KEY`): one set for the
  whole instance, never per person. Without them only the publisher APIs are
  off; `manage.py fulltext_sources --check` tells a rejected key from a valid
  one this server's network is not entitled to use.
- **Tools have their own sections.** `[tools]` holds the policy for all of
  them (`strict`, `disabled`); each installed tool adds `[tools.<name>]` with
  `enabled` and the keys its `tool.py` declares (`config explain tools.<name>`
  lists them). A bad value fails only that tool; a section for a tool that is
  not installed is only a warning. `make tools-check` shows what loaded.
- The backend reads the file at start, so a change needs `make restart`.

## The conversation

Ask only what changes the answer, and ask it in plain words. Four questions
cover almost every instance:

1. **Who will use it?** Just you / one lab / several labs / a whole school —
   and roughly how many people.
2. **Can it be reached from the internet?** (If yes, never recommend
   `signup.mode = "open"`.)
3. **Can it send email?** None / a Resend account / an SMTP server.
4. **Does the model endpoint bill per call?** (A paid API wants a nightly
   budget; a self-hosted model does not.)

One more only if they care how slates are ordered: **which decision model
re-orders each theme's top items?** TypeSafe's hosted Jev (`[decision] backend
= "jev"`, `TYPESAFE_API_KEY` in `.env`, sends profile text off the host), a
model they serve (`backend = "port"`, `port_url = "http://host:port"`: a decide
server, or llama.cpp / vLLM), or none (`off`). Leaving it at `auto` picks Jev
with a key, a port with a URL, else none. After setting a port, run
`manage.py decision_check` to confirm it answers from where the nightly runs.
A port should serve a *decision* model (a decide server, or a model fine-tuned
to decide); a stock chat model on llama.cpp answers "yes" to everything and
gives no ordering (`EXP-2026-11-009`). The local model of choice is d3-lite on a
decide server (`port_protocol = "decide"`, `port_model = "d3-lite"`): on real
states it beats a 4B model on llama.cpp and gains nothing from concurrency, so
set `nightly.rerank_concurrency` to 1–2 (`EXP-2026-11-012`). The nightly asks
from inside the backend container, so a server bound to the host's `127.0.0.1`
(GAIFA's decide is) is out of its reach. Turn on `decision.port_relay` with
`port_url = "http://host.docker.internal:<port>"`: the `decision-relay`
service forwards that port to the host's loopback, and the server is left as
it is. Then `make restart` and run `decision_check` inside the backend.

The same holds for the model server itself. When `LLM_BASE_URL` names a
server that listens only on the host's `127.0.0.1`, set it to
`http://host.docker.internal:<port>/v1` and turn on `llm.port_relay`; the same
`decision-relay` service forwards that port too. Then `make restart` and run
`llm_check` inside the backend.

The relay accepts connections only from Docker's bridge ranges
(`172.16.0.0/12`, `192.168.0.0/16`). On a server other people also run
containers on, narrow that to this stack's own network: find its subnet with
`docker network inspect <project>_default` and set `DECISION_RELAY_ALLOW` to
it in `.env`, otherwise their containers can reach the forwarded server too.

Then get a structured recommendation instead of reasoning one out yourself:

```bash
ops/mycelium config recommend --people 12 --email none --json
```

It returns `{ "profile", "set": {key: value}, "reasons": [...] }`. Show the user
the profile, each key it would set, and each reason — in their terms, not the
key names alone. Offer the one or two changes they are most likely to want
(e.g. "set a limit of 6 clusters per person?") and wait for them to agree.

Apply only after they agree:

```bash
ops/mycelium config init --profile lab                    # fresh instance
ops/mycelium config set signup.mode open limits.clusters 6  # existing file
ops/mycelium config validate                                # exit 1 = not workable
make restart
```

`validate` names every combination that cannot work (domain sign-up with no
mail provider, verification with nowhere to send the code, a code mode with no
code in `.env`). Fix each one with the user before restarting — never restart
on a failing `validate`.

After the restart, `make doctor` checks the instance end to end (stack,
migrations, model, embedding model, corpus, secret-file modes, exposure, and
`check --deploy` when `PUBLIC_HOSTNAME` is set) and exits 1 with the reason and
the fix. `make status` lists the steps that need root (the systemd timer, the
Discord bot): give the user those commands; never run `sudo` yourself.

## A fresh instance

`make setup` is the entry point. Without a terminal it asks nothing and reads
`PUBLIC_HOSTNAME`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` (and `PROFILE=…`)
from the environment; pass them as the user answered. No model named means
"none for now": it sets `llm.enabled = false`, so the instance runs on plain
drafts and the nightly run and `make doctor` do not treat it as an outage. To
connect one later: set `LLM_*` in `.env`, `ops/mycelium config set llm.enabled
true`, `make restart`, then `make doctor`. The first admin's password is
printed once by setup; `make admin NAME=<user>` sets a new one. The first
collection is `make nightly`.

## Model servers

The instance's own model is the server named `local`: the endpoint in `.env`
(`LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`). There is no default endpoint or
model: until `LLM_MODEL` names one, every model seam uses its deterministic
draft (`llm.enabled = false` records that this is deliberate). It stays the
default and stays in use. Other servers are made *available*; nothing switches to one until the host
routes a component to it.

```toml
[llm]
default = "local"        # what every component uses unless routed
allow_cloud = false      # the single cloud switch; off = nothing leaves the host
fallback = []            # servers tried in order when the routed one is down

[llm.providers.claude]   # one section per extra server
kind = "anthropic"       # openai_compatible | vllm | llamacpp | ollama | openai | anthropic | gemini | deepseek
api_key_env = "ANTHROPIC_API_KEY"   # the variable's NAME; the key goes in .env
model = "…"              # one the server lists: `manage.py llm_check`
# base_url = "http://gpu-box:8000/v1"   needed for openai_compatible, vllm, llamacpp, ollama
# location = "remote"    # local | remote | cloud; derived from kind and address if unset
# label, enabled, timeout, connect_timeout, context_window, reasoning,
# model_allow, model_deny are optional

[llm.routes]             # component = "server" or "server:model"
agent = "claude"         # Mylo's chat; the nightly components stay on local
```

- Add a server: `ops/mycelium config set llm.providers.gpu.kind vllm
  llm.providers.gpu.base_url http://gpu-box:8000/v1 llm.providers.gpu.model
  Qwen/Qwen3-8B`, then `config validate`, `make restart`, and
  `manage.py llm_check` (lists every server, its models and context windows,
  and each route). `manage.py llm_probe <server> --deep` tests one server the
  way Mycelium uses it. Azure's v1 endpoint, LM Studio, LiteLLM and other
  OpenAI-style APIs are `openai_compatible` with a `base_url`.
- A **cloud** server (OpenAI, Anthropic, Gemini, DeepSeek, or a known public
  API host) is never called while `llm.allow_cloud = false`; `validate`
  reports it. Turning the switch on is the host's decision: say in one plain
  sentence that prompts (profiles, papers, the person's questions) will then
  leave the machine for that provider. The web chat and Discord then say which
  model answers and that it runs elsewhere; a model on this machine is not
  named.
- Fallback is off by default. A server falls back only to the servers listed in
  `llm.fallback`, so a local model never falls back to a cloud one unless the
  host listed it (and `allow_cloud` is on).
- There is no spend cap and no price table: tokens are recorded per component
  and per server in the daily ledger. `[tools.agent] daily_turns` is the only
  brake on chat.
- Never put a key in `mycelium.toml` (the loader refuses an `api_key` field).
  Only the variable name goes there.

## Mylo chat in Discord

Who may ask Mylo in Discord is the host's choice, in `[tools.agent]`:

- `discord_access`: `public` (default: anyone who can post in a server a lab
  or department has connected may ask; someone without an account asks as a
  guest), `linked` (linked accounts only) or `entitled` (linked accounts whose
  plan includes the agent). A DM always needs a linked account with a
  verified email, and the server's binding always needs the bot add-on.
- `discord_guest_level`: the most any lab may let a guest see —
  `full` (what a lab member would be told there, people included),
  `no_people` (the same without looking people up; a project or a feed a
  guest reads still names the members it names), `public` (the thread's post
  and the corpus) or `off`. A lab or
  department that has not chosen gives guests `public` only — no people, so
  someone without an account cannot list the lab's members or their
  interests. It raises or lowers that for its own server with
  `/mylo chat guests …` or in its settings (`AgentOrgPolicy.discord_guests`);
  the lower of the lab's level and this ceiling applies.
  Say plainly that being in the server is treated as trust (S-16).
- Limits: `discord_guest_daily_turns` (questions per guest per day) and
  `discord_place_daily_turns` (guest questions per server per day). Both are
  `0` by default, which is no limit: a guest is limited only where the host
  or the lab set it up that way.
- `discord_channel_session_hours` (24), `discord_closed_thread_days` (30),
  `discord_ping_after_minutes` (10, when a slow answer pings the asker) and
  `discord_turn_timeout_minutes` (30).

A manager turns chat off for one channel with `/mylo chat here off`; a person
turns it off for themself with `/mylo chat off`.

## The public demo

"Let people try it" / "show a demo" means `[demo]`. Two steps, in order:
`manage.py demo build` (in the backend container) makes the fictional world from
`web/backend/apps/demo/world.yaml` and ranks it once, then
`ops/mycelium config set demo.enabled true` serves `/demo`. Tell the operator
three things: anyone who can reach the site can look around it without an
account; it is read-only; and each visitor may ask Mylo ten questions, which
costs model calls — `demo.questions_per_day` caps them all together (`0` keeps
the demo up with Mylo off) — and the nightly run ranks and briefs its nine
targets (six people, the lab, two projects) while it is on. Turning it off
(`demo.enabled false`) keeps the world and drops it from the nightly;
`manage.py demo refresh` brings it up to date at once, and `demo status` says
how fresh it is; `manage.py demo delete` removes it. Editing the fixture means another
`demo build`.

## Answering "why am I limited?"

1. `ops/mycelium config show --changed --json` — what differs from the defaults
   and where each value came from (`profile:…`, `mycelium.toml`, `env:NAME`).
2. `ops/mycelium config explain <key>` — what the key does and its value under
   each profile.
3. If a value comes from `env:NAME`, the file cannot change it: the variable in
   `.env` or the shell wins. Say so, and change it there.
4. A single person's watch-topic limit can also be set by an admin on the
   admin page (`watch_topic_limit`); that per-person override beats the file.

## Rules

- Recommend; do not decide. The operator chooses; you show the consequence.
- Never put a secret in `mycelium.toml`, a commit, or chat output. Tell the user
  which `.env` variable to fill in.
- Never weaken sign-up on an internet-reachable instance without saying so in
  one plain sentence first ("anyone who finds this address could create an
  account").
- `mycelium.toml` is git-ignored and belongs to the deployment. Do not commit
  it. `mycelium.example.toml` is the committed template and is regenerated, not
  hand-edited.
- When the user wants a key that does not exist, say so — do not invent one.
  `ops/mycelium config explain` is the complete list.
