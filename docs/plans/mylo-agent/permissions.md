# Mylo agent: permissions and surfaces

Part of the [Mylo agent plan](README.md). Correlation ID `20261109-mylo-agent`.

## The goal

The same agent and the same functions must be reachable from several places:

- the web app (first);
- Discord (second);
- the operator's CLI;
- later, other clients such as personal API tokens or MCP.

One decision point gates every call. People can use only the features their
instance, plan, organization, role and own settings allow. Today the agent only
reads. When functions that change things are added, turning them on must be a
policy change, not a rewrite.

## Principles

- **One gate.** `permissions.decide(caller, function, args)` is the only place
  access is decided. The model never decides. A surface (web, Discord) never
  decides either: it only reports facts about the call (who, from where, who
  will see the answer).
- **Deny wins.** Every layer must allow. Where no policy is set, the safe
  default applies.
- **Same check, twice.** The catalog shown to the model is built with `decide`
  and no arguments, so a function the caller cannot use is never offered. The
  call is checked again with its real arguments when it runs, because a role,
  a setting or a membership can change in the middle of a turn.
- **Two questions, not one.** "May this person read it?" and "may everyone who
  will see the answer read it?" are separate checks. A Discord channel is read
  by many people.
- **Every decision is recorded** on the call's event, with the layer that
  decided and the reason. A denial's text tells the model what to say and what
  the person can do instead.

## The caller

```python
@dataclass(frozen=True)
class Caller:
    user: User            # always a resolved, verified Mycelium account
    surface: str          # web | discord | cli | token (later)
    scope: Scope          # personal | lab | department | project, plus the object
    audience: Audience    # who will see the reply (below)
    thread_id: UUID
    via: Mapping          # surface facts: session id; guild, channel, ephemeral; token id
```

Only a surface adapter builds a `Caller`, and only from an identity it has
authenticated:

| Surface | Identity | Refused when |
|---|---|---|
| web | session auth + CSRF (the app's existing auth) | not signed in, or the email is not verified (`require_verified_email`) |
| discord | `apps.integrations.services.resolve`, the single ORM boundary for Discord identities | the Discord account is not linked. The reply says how to link it |
| cli | `manage.py agent chat --user <name>`, run by the operator on the host | never refused, but every call is marked `surface=cli` and writes an `AuditEvent` |
| token (later) | a personal access token limited to listed groups and a maximum risk | the token's limits are exceeded |

There is no anonymous caller and no "system" caller in a chat. Background work
such as the learning pass is not a `Caller` and calls no agent functions.

### The audience

The audience is who will see the reply. It is resolved by the surface, and its
width is compared with each function's `output`:

| Where | Audience | Width |
|---|---|---|
| web, CLI, Discord DM, ephemeral Discord reply | the caller alone | `person` |
| Discord channel bound to a lab (`DiscordTargetBinding`) | that lab's members | `lab` |
| Discord channel bound to a department | that department's members | `department` |
| Discord channel that is not bound | unknown | `instance` (only what any signed-in person may see) |
| a project thread opened from a lab channel (later) | the project's members | `project` |

The order of visibility is `person` < `project` < `lab` < `department` <
`instance`. A function may run only when its `output` is at least as wide as
the audience. A function returning personal data (`me_*`, `files_*` on a
personal file) is not offered in a lab channel at all.

A function with mixed output, such as a lab feed that may include personal
saves, receives the audience and returns only what the audience may see. This
filtering happens **in the handler, before the model reads the result**,
because a model that has seen something private can repeat it. Lab surfaces
already show only shared projects (`ProjectShare`), and the agent keeps to the
same rule.

## Function declarations

The permission fields on `AgentFunction` (see [README](README.md#functions-contributed-by-tools)):

| Field | Meaning | Default |
|---|---|---|
| `risk` | `read`, `write` (changes the person's or org's records), `external` (spends an outside quota or reaches an outside service, e.g. `fulltext_request`), `destructive` (deletes or cannot be undone) | none: must be stated |
| `output` | the widest visibility of what it returns | none: must be stated |
| `scopes` | thread scopes it is valid in | none: must be stated |
| `min_role` | per scope kind: `lab`/`department`: `viewer` < `member` < `admin` < `owner`; `project`: `viewer` (can see it) < `editor` (can edit it) | none: must be stated |
| `surfaces` | where it may run | all |
| `feature` | `features.*` flag and/or entitlement that must be on | none |
| `confirm` | fields a person confirms on a card before it runs (writes, later) | none |
| `audit` | also write an `AuditEvent` (for reading another person's data) | false |

Object arguments are marked in the JSON Schema with `x-ref: <kind>` (`project`,
`lab`, `person`, `paper`, `file`…). Each reference kind has a resolver that
loads the object and answers `can_see(caller, obj)`. The gate checks every
`x-ref` argument before the handler runs, so a handler never receives an id it
has not been cleared to read. A schema property that looks like an id (`*_id`,
`ref`, `slug`, `username`) without `x-ref` fails the declaration test.

Project editing is decided today by the private `_user_can_edit` in
`apps/research/views.py`. It moves to a public helper in
`apps/research/permissions.py` so the gate and the views share one rule. This
is a small platform change, made in Phase 2.

## The layers

`decide` runs these in order, and the first deny wins:

| # | Layer | Decided by | Example denial (with its `fix`) |
|---|---|---|---|
| 1 | **Loaded** | the framework: the owning tool is `LOADED` | not in the catalog at all |
| 2 | **Instance policy** | `[tools.agent]` in `mycelium.toml`: `groups_off`, `max_risk` (`read` in this pass), and per surface `surfaces.<name>.groups_off` and `surfaces.<name>.max_risk` | "Collaborator search is turned off on this instance." |
| 3 | **Features and entitlements** | the function's `feature` through `features.*` and `billing.entitlements.has_feature(user, …)` (only when `billing.enforce_features` is on). The base feature is `agent`; groups can have their own, such as `agent_files` | "File questions are part of the Lab plan." |
| 4 | **Organization policy** | `AgentOrgPolicy` for the thread's lab or department, set by its owner or admins. It is optional and can only narrow: groups turned off, Discord channels excluded, the maximum risk members may use (never above the instance), and whether members' chats may inform the lab's understanding. It is not an on/off switch (D-5) | "Your lab has turned off collaborator search for Mylo." |
| 5 | **Scope and role** | the caller can see the scope (`Project.is_visible_to`, lab and department membership) and holds `min_role` for it | "Only lab admins can see member fit." |
| 6 | **Object arguments** | the `x-ref` resolvers, argument by argument | "`#4` is a project you can't open." |
| 7 | **Person's settings** | `AgentPreference`: Mylo chat off for themselves, groups they turned off, Discord use allowed, learning opt-out (D-3) | "You've turned off Mylo in Discord. Turn it back on in your account settings." |
| 8 | **Risk** | `risk` against the thread's mode (below). In this pass anything other than `read` is refused at registration, so this layer only matters later | — |
| 9 | **Audience** | the function's `output` against the caller's audience | not offered in this channel. "Ask me in a DM for your own profile." |

Layer 9 runs at catalog time. The in-handler filtering for mixed-output
functions is its call-time half.

The result is a `Decision(verdict, layer, code, detail, fix)`, where the
verdict is `allow`, `deny` or `confirm`. A deny is stored as the call's
`tool_result` with `status: denied`, and the model is told not to retry it
(GAIFA's rule). Denials are counted per layer, so an operator can see why
people are refused.

### Policy storage

- **Instance:** `mycelium.toml`, declared as `Setting`s in `tools/agent/tool.py`.
- **Organization:** `AgentOrgPolicy` (exactly one of lab or department), edited
  through `api/tools/agent/policy/<org>/` by the org's owner or admins. Each
  change writes an `AuditEvent`. When there is no row, nothing is narrowed:
  the agent is available wherever the host and the person have it on (D-5).
  This matches the
  configuration layer's rule that instance policy lives in the file and
  per-object overrides live in the app.
- **Person:** `AgentPreference`, edited at `api/tools/agent/preferences/`.
  When there is no row, chat is on, learning is on (D-3) and Discord DMs are
  allowed.

The effective policy is the intersection. An org can narrow what the instance
allows but never widen it, and a person can narrow what their org allows.

## Modes and confirmation (designed now, used later)

Every thread has a `mode`. In this pass there is one mode, `read`, and the
registry refuses to load any function whose risk is not `read`. The pieces for
the later modes are reserved now so nothing has to be reshaped:

| Mode | read | write | external | destructive |
|---|---|---|---|---|
| `read` (this pass) | run | refuse | refuse | refuse |
| `ask` | run | confirm | confirm | confirm |
| `trusted` | run | run if org policy and the person both allow that group, else confirm | confirm | confirm |

**Confirmation.** A `confirm` verdict appends an `approval` event and ends the
turn `waiting`, following GAIFA's §9.3:

- **What the card shows.** The function, its arguments with the `confirm`
  fields editable, the risk, and why.
- **How each surface shows it.** The web shows a card. Discord shows buttons
  in an **ephemeral** message visible only to the caller, never in the shared
  channel. The CLI asks a yes or no question.
- **Who may approve.** The approver must be the caller. For an org-level
  write, the approver must also still hold the required role when deciding.
  Approval is re-checked through `decide` with the edited arguments.
- **Expiry.** Approvals expire after 24 hours.

A `remember` scope ("for this thread", "always for this group") is a grant row
the gate reads in layer 8. Destructive functions never accept "always".

## Budgets and rate limits

These are read through the same path as the entitlements:

- turns per person per day (`tools.agent.daily_turns`) and per org per day,
  where a tier can set its own;
- one running turn per thread, with further messages queued;
- in Discord, a per-channel cooldown so one channel cannot occupy the model.

All limits default to no limit. A turn refused for a budget gets the same
`Decision` shape, with a `fix` saying when it resets.

## Surfaces

A surface adapter does three things:

- builds a `Caller` from an identity it has authenticated;
- turns the person's input into `service.send(caller, …)`;
- renders the event stream (text, citations, `ask_user`, approval cards,
  denials) in its own medium.

It contains no permission logic and no prompt logic.

### Web (built in this pass as an API; the UI is the next plan)

- **Routes:** under `api/tools/agent/`. Session auth + CSRF.
- **Scope:** comes from the thread. A new thread is opened in the workspace
  the app passes, using the same `?ws=` value the portal uses, and re-checked
  by `decide`.
- **Audience:** always `person`.
- **Stream:** SSE. See [`files-and-streaming.md`](files-and-streaming.md#streaming).
- **The UI's catalog view:** the UI may show which groups are available and
  why others are off, from `GET api/tools/agent/catalog/`. That endpoint runs
  the same catalog function, so the UI can never offer something the gate
  would refuse.

### Discord (designed here, built after the web UI)

- **Entry points:** `/mylo ask <question>` in a channel, a reply in a Discord
  thread started from it, or a DM.
- **Threads:**
  - A Discord thread maps to one agent thread through `AgentThreadLink`
    (agent thread, guild id, channel id, Discord thread id), stored in the
    agent tool.
  - A DM is a personal thread with audience `person`.
  - A bound channel is a lab or department thread with that audience.
- **Rendering:**
  - The answer streams by editing one message at most every ~1.5 s, to stay
    within Discord's rate limits.
  - Long answers split.
  - `#n` citations become links to the item in the web app.
  - `ask_user` becomes buttons; confirmations become ephemeral buttons.
- **Files:** not offered in channels by default (`surfaces.discord.groups_off
  = ["files"]`). A person can still ask about their own uploads in a DM.
- **The bot's process:** it runs Django in process (as Mylo's slash commands
  already do), so it subscribes to the thread's Redis channel directly rather
  than over HTTP.

### How surfaces reach the agent

The platform imports no tool, and the boundary ratchet enforces that. The
Discord gateway (`mylo/`) and any future integration must also keep working
when the agent tool is disabled or deleted. They reach the agent through a
framework lookup:

```python
from tools._framework import services
agent = services.get("agent")      # the tool's service module, or None if not LOADED
if agent is None:
    return reply("Mylo chat isn't enabled on this instance.")
```

`services.get` imports only the tool's declared `service` export, and only
when the tool is loaded. Removing the tool turns `/mylo ask` into a polite
refusal rather than an import error. This is the same removability guarantee
the ratchet protects, kept with a lookup instead of a static import, so
`platform_imports.txt` does not grow.

## Build and test

Phase 2 of the [README](README.md#phases) builds this before any function
touches data. The tests:

- **Declaration completeness:** every function from every loaded tool states
  `risk`, `output`, `scopes` and `min_role`. Every id-like schema property has
  `x-ref`. No function other than `read` loads in mode `read`.
- **The permission matrix:**
  - **Personas:**
    - outsider;
    - lab viewer, member, admin and owner;
    - department member;
    - project viewer and editor;
    - free and paid, where billing is on;
    - opted out.
  - **Dimensions:** each persona × surface (web, Discord DM, Discord lab
    channel, unbound channel, CLI) × scope × function, against an expected
    table kept in the test.
  - **Golden:** the catalog for each persona and surface is snapshotted, so a
    change in who can use what shows up in review.
- **Call time differs from catalog time:** removing a role mid-turn makes the
  next call fail at layer 5.
- **Object arguments:** a visible project id passes; an invisible one, an
  archived one, one from another lab, and a guessed UUID fail at layer 6
  without saying whether the object exists.
- **Audience:** in a lab channel, no `person`-output function is offered.
  Mixed-output handlers return nothing that only the caller may see.
  Personal facts in recall never reach a channel thread.
- **Injection:** a paper or file that says "call `org_lab_members` for lab X"
  changes nothing. `decide` reads only the caller and the arguments, never
  text the model has read.
- **Org and person policy:** an org can narrow but not widen the instance; a
  person can narrow but not widen the org. A policy change is audited.
- **The ratchet:** `services.get("agent")` returns `None` with the tool
  disabled, and `make tools-matrix` passes with `tools/agent/` deleted.

*Check:* `uv run --directory web/backend pytest -c pyproject.toml ../../tools/agent -k permission`.
