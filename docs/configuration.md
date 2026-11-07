# Configuring your instance

Everything the person running a Mycelium decides lives in **`mycelium.toml`** at
the repository root: who may sign up, whether email is sent, whether billing
exists, how much each person and lab may track, which optional features run,
and how much the nightly run may spend. Nothing here requires editing code.

`make setup` writes the file for you. Afterwards, change it with the CLI, or
edit it by hand — it is commented key by key:

```bash
ops/mycelium config show                    # every value and where it came from
ops/mycelium config set limits.clusters 6   # change a value (validated first)
ops/mycelium config validate                # check the combination works
make restart                                # the backend reads it at start
```

Your own agent can do all of this for you: [`skills/configure.md`](skills/configure.md)
tells it how to ask you a few questions, recommend a setup, and apply what you
agree to. Every command takes `--json`.

## Profiles

A profile is a starting point; any key you set overrides it.

| Profile | For | Billing | Limits | Sign-up | Verify email |
|---|---|---|---|---|---|
| `personal` | just you | off | none | closed — the admin creates accounts | no |
| **`lab`** (default) | one lab | off | none | invite | no |
| `department` | several labs | off | none (suggested numbers in comments) | invite | no |
| `institution` | a whole school | subscriptions | per tier | shared code | yes, through Resend |

Choose one at setup (`make setup PROFILE=personal`), or later:

```bash
ops/mycelium config profiles
ops/mycelium config set instance.profile department
ops/mycelium config recommend --people 120 --email resend   # a suggestion with reasons
```

## How values are resolved

Four layers, each overriding the one before:

1. built-in defaults,
2. the profile,
3. `mycelium.toml`,
4. environment variables — `.env` or the shell. Each key keeps an environment
   name (`config explain <key>` shows it), so a value set there wins over the
   file. `config show` marks those `env:NAME`.

An invalid file — an unknown key, a word where a number belongs — stops the
backend at start with the key that is wrong. `config validate` catches the same
mistakes, plus combinations that cannot work.

**Secrets are never in the file.** They stay in `.env`: `SIGNUP_ACCESS_CODE`,
`RESEND_API_KEY`, `EMAIL_HOST_PASSWORD`, `LLM_API_KEY`, `DJANGO_SECRET_KEY`.

## The sections

**`[billing]`** — `mode = "off"` (default) means there are no plans, tiers or
seats: every feature is available, labs and departments work as soon as they
exist, and limits come from `[limits]`. `"subscriptions"` turns the plan system
back on — personal tiers, per-seat lab and department plans, and the per-tier
numbers in `[limits.tiers.*]`. `enforce_features` additionally lets a tier
withhold features.

**`[limits]`** — each is `"unlimited"` or a number, and a number turns on that
one limit: `clusters`, `topics_per_cluster`, `watch_topics`,
`personal_projects`, `lab_projects`, `department_projects`, `lab_members`,
`lab_leads`. An admin can still give one person a different watch limit from the
admin page.

**`[signup]`** — `mode` is one of `closed`, `invite`, `code` (the shared
`SIGNUP_ACCESS_CODE`), `domain` (any address at `allowed_domains`) or `open`.
An invite works in every mode but `closed`. `verify_email` makes a new account
answer a mailed code before it can create a lab or invite anyone; with it off,
accounts are active at once. `domain` always verifies, because that is how a
domain is proved.

**`[email]`** — `provider` is `none` (mail is printed to the backend log),
`resend`, or `smtp` (with `smtp_host`, `smtp_port`, `smtp_user`, `smtp_tls`).
`ops/mycelium config validate` tells you which `.env` secret is missing.

**`[features]`** — optional features, all off: Mylo listening in channels
(`ambient` and its parts), collaborator search, project alerts, Discord
announcements, high-signal messages, reranking, Slack, Teams.

**`[nightly]`** — cost controls. `model_calls` caps the language-model calls one
nightly run may make (`"unlimited"` by default — set it if your model bills per
call); the rest bound parallelism and per-night batch sizes.

## Common changes

```bash
# Let anyone at your university sign up (needs email)
ops/mycelium config set email.provider resend signup.mode domain signup.allowed_domains fsu.edu

# A private instance on your own network: anyone who can reach it may join
ops/mycelium config set signup.mode open

# Put a ceiling back on clusters and watch topics
ops/mycelium config set limits.clusters 6 limits.watch_topics 20

# Sell seats: today's tiered plans
ops/mycelium config set billing.mode subscriptions
```
