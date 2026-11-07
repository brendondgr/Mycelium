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
  `SIGNUP_ACCESS_CODE`, `LLM_API_KEY` live in `.env`.
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
