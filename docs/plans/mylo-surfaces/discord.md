# Plan D: Mylo in Discord

Index, owner decisions and sequencing: [README.md](README.md). Depends on the
shared contract (track S) in that file.

## Objective

People talk to Mylo in Discord by tagging it, replying to it, or sending it a
DM. In the forum threads Mylo opens for grants, conferences, fellowships and
department opportunities, a question is answered with that item already in
hand. A thread is one conversation that remembers everyone who asked. Every
answer comes from the same agent the web app uses (`tools/agent/`), under the
same gate, and everything is stored in this instance's own Postgres.

## What is taken from Manny, and what is not

Read from `~/Agents/Manny/utils/agent/`.

| Keep | Change |
| --- | --- |
| Triggers: a mention, a reply to the bot, any DM | "Hey Manny" text trigger is dropped (S-4) |
| A thread shares one session; a channel session is per person (S-6) | Sessions live in the agent's event log, with real compaction, not a second store |
| A status message that narrates what the bot is doing | It is edited into the answer, not deleted; it is a reply to the question |
| Speaker labels cleaned of `@ < > \ \` \|` and control characters, capped at 64 | No message can ping anyone, except the asker when an answer was slow (Manny's answer could ping anyone) |
| Plain text answers split under 2,000 characters | Splitting never breaks a code fence |
| | One turn per conversation at a time, with a queue (Manny has no lock) |
| | The opening post of a forum thread is context (Manny never reads it) |
| | No recall across channels a person cannot see (Manny's recall leaks) |
| | Deleting a question blanks it in memory; `/mylo forget` exists |

## Where things stand

- The bot is a `discord.py` gateway process (`mylo/bot/`) that runs Django
  in-process. Cogs import no Django; they call bridges (`mylo/linking.py`,
  `mylo/listening.py`) that wrap sync functions with `mylo/mycelium.py::db()`
  or `db_long()`.
- `mylo/bot/cogs/listen.py` holds the only `on_message` listener. Today a DM
  and an `@Mylo` mention are passed to the ambient profile
  (`listening.heard`) and a DM gets an acknowledgement or a dialogue reply.
- The Message Content intent is requested only when `MYLO_LISTEN_ENABLED` is
  set. Without it Discord still delivers the text of DMs, of messages that
  mention the bot, and of the bot's own messages. That is all this plan needs
  (S-4).
- Forum threads come from one producer, `tools/delivery/discord_announcements.py`.
  `AnnouncementPost.thread_id` leads to the announcement, its content item and
  its lab or department. `thread_id` has no index. `ClosingSoonPost` threads
  list a day's closing items.
- The agent has a Discord surface in its gate already (`AgentPreference.discord_allowed`,
  `AgentOrgPolicy.discord_channels_off`, `surface_groups_off =
  ["discord_channel:files"]`, golden rows `discord_dm`, `discord_lab`,
  `discord_unbound`) but no adapter, no `AgentThreadLink`, and three
  assumptions that Discord breaks:
  1. a thread has exactly one owner (`AgentThread.user`, "nobody else can read it");
  2. the worker rebuilds the caller from the thread's owner with audience
     `person` (`loop.run_turn` → `caller.for_thread`);
  3. every caller is a Mycelium user.

## Design

### Triggers

| Event | Treated as a question when |
| --- | --- |
| DM | always, unless it answers one of Mylo's own ambient questions (`listening.dialogue` keeps priority) |
| Guild message | it mentions the bot user or the bot's own role |
| Reply to a Mylo message | the reply pings Mylo (Discord's default). A reply with the ping turned off arrives with no text; Mylo answers once per person per hour: "I can only read replies that ping me." |

Ignored: bots, webhooks, `@everyone` and `@here`, edits. The mention is
stripped; an empty question gets "What can I help with?". Attachments are
ignored in shared places (the `files` group is off there) and accepted in DMs
under the files tool's own limits.

### Places

`apps/integrations/services/resolve.py` gains `place_for(guild_id, channel_id,
thread_id, parent_id)`, the one function that decides whose room a message is
in.

| Place | Scope | Audience | Anchor | Conversation |
| --- | --- | --- | --- | --- |
| DM | personal | person | none | the person's own, like web |
| Thread with a live `AnnouncementPost` | the binding's lab or department | that lab or department | the announcement | shared |
| Thread with a `ClosingSoonPost` | the binding's lab or department | same | the day's list | shared |
| Any other thread in a bound server | the owning binding | its lab or department | none | shared |
| Open channel in a bound server | the owning binding | its lab or department | none | per person |
| Server with no live binding | none | none | none | no answer; one line: "This server isn't set up for Mylo." |

"Owning binding": the binding whose `DiscordChannelRoute` names the channel or
its parent forum; otherwise the server's only live binding. When a server has
several bindings and none owns the channel, Mylo cannot tell whose room it is
and answers from public material only (audience `instance`).

The audience is fixed by the place, never by the asker. Every function result
is already filtered to it (`permissions.within_audience`), so a lab member
asking in a department channel gets nothing that only their lab may see.

### Who may ask (S-5, S-10, S-11)

There are two ways to be allowed:

1. **An activated account.** A Discord user linked to a Mycelium account whose
   email is verified. This works in a DM and in any bound server.
2. **Being in a bound server.** Anyone who can post in a channel of a server
   that an activated lab or department has connected (a live binding with the
   `bot_server` entitlement) may ask there, with or without an account.
   Someone without an account is a **guest**.

A DM from someone without an activated account gets one line with the connect
link and nothing else. There are no guests in DMs (S-10).

`[tools.agent] discord_access` lets the host tighten this later:

| Value | In a bound server | Meaning |
| --- | --- | --- |
| `public` (default now) | anyone who can post there | A linked account asks as itself. Anyone else asks as a guest. No plan check on this surface. |
| `linked` | linked accounts | Others get the existing "connect your Discord" line. |
| `entitled` | linked accounts whose plan includes `agent` | Today's `may_chat` rule. |

**Guests (S-11, S-16).** A guest is a Discord user with no Mycelium account:
`Caller.user = None`, `Caller.guest = Guest(discord_user_id, name)`. Being in
the server is the guest's permission, and it is taken as trust: a lab does not
invite strangers into its server. Discord's own membership and channel
permissions decide who can post, and Mylo answers whoever was able to post the
question. By default a guest is told what someone holding the `member` role in
that lab would be told in that same place, people included:

| A guest may use | A guest may not use |
| --- | --- |
| Corpus search and read (`corpus_search`, `corpus_item`) | Anything that starts from the asker's own account (`me_*`, `feeds_saved`, `knowledge_my_concepts`, `knowledge_backing`, `knowledge_introduction_paths`, `knowledge_people_beyond_lab`): a guest has no profile to start from |
| The thread's announcement in full, as reference `#1` | Files and full text |
| The lab's or department's overview (`org_lab`, `org_department`) | Recall of other conversations (`thread_search`) |
| Its slate, briefing and deadlines (`feeds_slate`, `feeds_briefing`, `feeds_deadlines`) | `ask_user` |
| Projects shared with it (`projects_list`, `projects_get`, `projects_feed`) | |
| **People:** the lab's members, a member's declared profile, and who in the lab could go after a call (`org_lab_members`, `org_person`, `knowledge_people_for_call`) | |

`knowledge_project_concepts` joins the left column in D1 if its read turns out
not to depend on the asker's own graph.

How this is enforced:

- The gate still fails closed. `AgentFunction` gains `guest`: the lowest guest
  level at which the function is offered (`"public"`, `"no_people"`, `"full"`),
  default `None` (never). The left column above is the whole list.
- A guest's handler takes the lab or department from the place
  (`functions/org.py::audience_lab`, `audience_department`), never from an
  argument. Asking about another lab is refused.
- Projects are the ones shared with that lab or department, the rule the lab's
  own pages already follow. Every result is still filtered to the place's
  audience.
- For the people functions a guest stands where a `member` of the place's lab
  stands. The limits a member already has in a shared reply apply unchanged:
  only people who belong to that lab, and only what each person declared
  (`org_person`'s "Only what they declared is shown", `declared_only` in
  `knowledge_people_for_call`). A guest never sees more about a person than a
  lab member sees in that channel.
- A guest is never learned from, and nothing a guest says reaches anyone's
  profile.

**Guest levels: the settings that narrow this.** Trust is the default, not a
fixed rule. Four levels, each a subset of the one before:

| Level | A guest in the server gets |
| --- | --- |
| `full` (default) | Everything in the left column above |
| `no_people` | The same without the three people functions. Names already printed in a thread's opening post stay visible; Mylo does not look up more about them |
| `public` | The thread's opening post and the public corpus only |
| `off` | Nothing. Only linked accounts may ask in this server |

The level is set in two places, and the lower one wins:

- **The host:** `[tools.agent] discord_guest_level` (default `full`), the most
  any lab on this instance may give a guest.
- **The lab or department:** `AgentOrgPolicy.discord_guests` (default `full`),
  set by a manager with `/mylo chat guests …` or in the organization's
  settings in the web app (plan W, W5). Like every org policy it can only
  narrow.

There is no per-person switch (open question 2).

Limits: `discord_guest_daily_turns` (10) per guest and
`discord_place_daily_turns` (200) per server, both settings.

The Discord gate gets two actions in `gate._ACTIONS`: `chat` (rate bucket
`chat`) and `chat_guest`. Both are audited like every other action.

### Shared conversations

Changes in `tools/agent/`:

- **Ownership.** `AgentThread.user` becomes nullable and `AgentThread.shared`
  is added, with a constraint that a thread is shared exactly when it has no
  owner. A shared thread belongs to its place. Every owner-assuming path is
  changed to refuse or skip shared threads: `get_thread`, `list_threads`,
  `update_thread`, `delete_thread`, `fork_thread`, `subscribe`, `export`, the
  learning pass, `memory_after`, recall digests. Shared threads are not
  reachable through the web API in this release.
- **Who is speaking.** A `user` event's payload gains
  `speaker: {kind: "member"|"guest", user_id, discord_user_id, name}` and
  `turn: {surface, audience_width, audience_ref, via}`.
  `AgentQueuedMessage` gains the same two fields.
- **The worker's caller.** `loop.run_turn` rebuilds the `Caller` from the
  newest unanswered `user` event (`caller.for_turn(thread, event)`), not from
  the thread's owner. A thread with no `turn` payload behaves as today.
- **Queue.** In a shared thread, messages that arrive during a turn are
  answered one at a time, each as its own turn under its own asker. They are
  never merged. At most five wait; a sixth gets "One at a time, please."
- **What a later turn sees.** In a shared thread, earlier turns are replayed
  as a transcript only: each question with its speaker's name, and each answer
  as posted. Function calls and their results are kept in the log but shown to
  the model only for the turn that made them. So what one person's turn
  fetched is never handed to the next person beyond what Mylo already posted.
  Numbered references are resolved again for the current asker.
- **Speaker names are data.** The prompt states that names are labels. A name
  is cleaned and capped before it is stored.
- **No `ask_user` where others read.** In shared places Mylo asks in prose and
  ends the turn, because a waiting thread blocks everyone else. DMs keep the
  question buttons.
- **Compaction** works as built; the summary keeps speaker names.

### Links and delivery records

New in `tools/agent/models.py` (agent migration `0003`):

```
AgentThreadLink
  thread            FK AgentThread
  guild_id          "" for a DM
  place_id          the Discord thread id, channel id or DM channel id
  discord_user_id   "" when shared
  binding_id        the owning binding, if any (plain id; no FK into integrations)
  anchor            {kind, key} or {}
  closed_at
  unique (guild_id, place_id, discord_user_id) where closed_at is null

AgentDiscordTurn
  link              FK AgentThreadLink
  user_event_seq
  trigger_message_id, status_message_id
  discord_user_id
  state             pending | answered | failed | cancelled
  created_at, finished_at
```

`AgentDiscordTurn` is what makes delivery survive a bot restart: on start and
on gateway resume the bot looks for pending rows. If the turn has
finished, the answer is delivered (with the ping, if it is late by then). If
the turn ended in an error, or the row is older than
`discord_turn_timeout_minutes` (30), the status message becomes "I lost track
of this one. Ask again." A turn that is still working is left alone: the
agent's own stuck-turn task restarts one that has made no progress for ten
minutes.

A per-person channel conversation that has been quiet for
`discord_channel_session_hours` (24) is closed and the next question starts a
new one, so an old topic does not colour a new one.

`tools/delivery/` changes: an index on `AnnouncementPost.thread_id`; a
reference kind `announcement` (through `Tool.agent`) whose card carries the
title, dates, facts and write-up, and whose resolver admits a member of the
target lab or department, or any caller whose place belongs to it.

### The adapter

`tools/agent/surfaces/discord.py`, reached by the bot through
`tools._framework.services.get("agent")` (the platform never imports a tool):

```python
ask(*, discord_user_id, name, guild_id, channel_id, thread_id, parent_id,
    message_id, text, attachments=()) -> Handle | Refusal
follow(handle) -> Iterator[message]        # stream.follow(view="activity", stop_when_idle=True)
stop(handle, *, discord_user_id) -> None
forget(*, discord_user_id, guild_id, place_id) -> int
reconcile() -> list[Handle]
```

`ask` runs the Discord gate, resolves the place, finds or opens the thread
through `AgentThreadLink`, builds the `Caller`, calls `service.send`, and
writes the `AgentDiscordTurn`. It returns a refusal with a ready sentence for
every "no" (not linked, rate limited, channel turned off by the lab, chat
turned off by the person, no model). It contains no permission rule of its
own.

The turn runs in the Celery worker, as on the web. The bot only enqueues and
watches. The bot process therefore needs the agent's Redis (the Celery broker
and the stream database). When the stream bus is unreachable, `follow` falls
back to reading the event log once a second, so an answer is late, not lost.

### What the bot draws

New: `mylo/chat.py` (bridge, like `linking.py`), `mylo/bot/cogs/chat.py`
(delivery, recovery and the Stop button; it adds no second `on_message`),
`mylo/bot/chat_render.py` (pure functions, no Django, no Discord I/O).

1. Mylo replies to the question with a status line taken from the activity
   view (S1): *Reading the call…*, *Looking at your lab's projects…*,
   *Searching the corpus for "…"…*. No thinking text exists in that view.
2. The line is edited as the activity changes, at most once every 1.5 seconds.
   It carries a **Stop** button the asker or a manager of the lab can press.
3. When the turn ends, the status message is edited into the answer. Further
   chunks follow as plain messages. An edit notifies nobody, which is right
   for a quick answer.
4. **A slow answer pings the asker (S-12).** When the answer took longer than
   `discord_ping_after_minutes` (default 10), Mylo posts it as a new reply
   that mentions the asker, and the status message becomes "Answered below."
   This is the only ping Mylo's chat ever sends, and it can only reach the
   person who asked.
5. Answers are Discord markdown, split under 2,000 characters on paragraph
   boundaries and never inside a code fence. `<@…>`, `@everyone` and `@here`
   in model output are neutralised. Every send and edit uses
   `AllowedMentions.none()`, except the one in step 4, which allows the
   asker's id and nothing else.
6. Citations become a short "Sources" list with masked links, embeds
   suppressed. A member's links open the item in the web app; a guest's links
   go to the item's public page.
7. A small subtext line names the model and where it runs: on every answer
   when it runs elsewhere, on the first answer of a conversation when it runs
   on this machine (S-3).
8. A queued question gets an hourglass reaction if Mylo may react there.
9. If Mylo cannot post in the channel, nothing is sent and the refusal is
   audited.

The prompt gets the place as facts from the caller (`via.place`: kind, thread
title, server name). The Discord wording rules (short answers, no tables) live
in `tools/agent/prompt.py`, keyed on the surface. The adapter and the bot hold
no prompt text.

### Routing inside the one listener

`listen.py::_handle` asks `mylo/chat.py::route(message)` first.

| Message | Chat | Ambient profile |
| --- | --- | --- |
| DM answering one of Mylo's ambient questions | no | `listening.dialogue`, as today |
| Any other DM | yes | Not sent to `listening.heard`. The personal thread is read by the agent's quiet-thread learning pass, like web chat (S-7). The DM acknowledgement line goes away. |
| Guild message that addresses Mylo | yes | `listening.heard(explicit=True)` as today, which records only under the lab's and the person's Discord consent (S-7) |
| Anything else | no | as today |

Shared threads are skipped by the agent's own learning pass, so a question in
a shared place is learned from by one path only, and a guest's by none.

This changes one existing behaviour: a DM stops being stored as an explicit
note with an acknowledgement and becomes a conversation.

### Commands and switches

Added to the existing `/mylo` group in `mylo/bot/cogs/mylo_commands.py`
(defer first, never decide access in the cog):

| Command | Does |
| --- | --- |
| `/mylo ask question: [private:]` | The same as a mention. `private` answers ephemerally in the person's own conversation. |
| `/mylo forget` | Blanks the caller's own questions in this place's memory. In a DM, deletes the conversation. |
| `/mylo chat on\|off` | The person's switch (`AgentPreference.discord_allowed`). |
| `/mylo chat here on\|off` | A manager turns chat on or off for this channel (`AgentOrgPolicy.discord_channels_off`). Needs the same right as `/setup`. |
| `/mylo chat guests full\|no-people\|public\|off` | A manager sets the guest level for this lab's server (`AgentOrgPolicy.discord_guests`). Same right. The reply states the level in force when the host's ceiling is lower. |

Slash commands reach production only after the owner's `@Mylo sync global`.

### Storage, retention, deletion

- Everything is in this instance's Postgres: the event log, links, delivery
  rows. Nothing is written to Discord beyond the messages people see, and
  nothing is sent to a third party unless the host routed chat to a cloud
  model (plan P).
- A guest's stored data is their Discord user id, the display name at the
  time, and the text of what they asked Mylo.
- A deleted question (the existing `on_raw_message_delete` in `listen.py`,
  extended to match `AgentDiscordTurn.trigger_message_id`) is removed from the queue if it has
  not run, and its stored text is blanked.
- A deleted Discord thread (`cogs/drift.py::on_raw_thread_delete`) closes the
  link and deletes the conversation.
- A closed announcement keeps its conversation for
  `discord_closed_thread_days` (30), then the retention sweep deletes it.
- A removed binding or a server Mylo leaves closes every link in it.
- DMs and per-person channel conversations follow `[tools.agent]
  retention_days`.
- Logging: the gate's audit row per question (allowed or denied, with the
  reason), the agent's own event log, and `mylo/reporting.py` for failures.

## Phases

### D1. Shared conversations, per-turn callers, guests (backend only)

`tools/agent/`: `models.py` (nullable owner, `shared`; migration `0003` with
the link and delivery tables), `caller.py` (`Guest`, `for_turn`),
`permissions.py` (guest layer, `discord_access`, `may_chat` for guests),
`loop.py` (caller from the turn, one queued message per turn),
`rebuild.py` (transcript replay), `service.py` (owner-assuming paths),
`tasks.py`/`learning.py` (skip shared), `tool.py` (settings below),
`agentspec.py` (`guest`), and the guest path in
`functions/{corpus,org,feeds,projects,knowledge}.py`. Golden permission matrix
gains rows for `discord_thread_member`, `discord_thread_guest`,
`discord_thread_guest_no_people`, `discord_thread_guest_public`,
`discord_channel_member`, `discord_ambiguous`.

```bash
cd web/backend && DATABASE_URL=postgres://…/mycelium_d1 \
  uv run --no-sync pytest -c pyproject.toml ../../tools/agent/tests ../../tools/_framework/tests -q
uv run --no-sync python ../../tools/_framework/golden.py write
make tools-check
```

Accept when, with the scripted model and no Discord:
- two members and a guest take turns in one shared thread; each turn's
  function list matches that asker's row in the matrix;
- the guest's turn is offered exactly the functions of its level, gets the
  lab's overview, slate, shared projects, member list and one member's
  declared interests, is refused another lab's and a person outside the lab,
  and its context contains no function result from an earlier turn;
- at `no_people` the three people functions are absent; at `public` the same
  guest is offered the corpus functions only; at `off` the guest is refused;
- a host ceiling of `no_people` over a lab at `full` gives `no_people`;
- a guest's `org_person` result holds nothing a member's result in the same
  place does not;
- a lab-only result is absent from a turn whose audience is the department;
- three messages queued during a turn produce three turns in order, each under
  its own asker;
- web threads behave exactly as before (the existing suite passes unchanged);
- no shared thread is returned by any web route.

### D2. Places, links, anchors, the adapter

`resolve.place_for`; `gate._ACTIONS` rows; the `AnnouncementPost.thread_id`
index and the `announcement` reference kind in `tools/delivery/`;
`tools/agent/surfaces/discord.py`; the Discord lines in `prompt.py`.

```bash
uv run --no-sync pytest -c pyproject.toml ../../tools/agent/tests ../../tools/delivery/tests apps/integrations -q
```

Accept when: each row of the Places table resolves as written, including the
several-bindings case; `ask` returns the right refusal sentence for every
denial; a forum-thread question has the announcement as `#1` for a member and for
a guest alike, and only the as-posted card for a guest where the lab's policy
is `public`; a DM from an unlinked or unverified account is refused with the
connect line; both guest limits hold; a second question in
the same thread reuses the thread and a quiet channel conversation rolls over
after the configured hours.

### D3. The bot: triggers, status, answers, recovery

`mylo/chat.py`, `mylo/bot/cogs/chat.py`, `mylo/bot/chat_render.py`, the route
call in `listen.py`, `INITIAL_EXTENSIONS`, a chat line in `/mylo health`
(model reachable, stream bus reachable).

```bash
make test-mylo        # unittest discover -s mylo/tests, from the repository root
```

Accept when: renderer tests cover splitting (fences, 2,000 limit), mention
neutralising, the sources list, throttled edits and the model line; a fake
transport (as `mylo/tests/test_listening_cog.py` fakes messages today) shows
status → edits → answer for a DM, a forum thread and a channel;
a restart with a pending row delivers the answer once; a reply without a ping
gets the one-line hint and no more than one per hour; an answer
that took longer than the configured minutes arrives as a new reply that
mentions the asker and nobody else, and a quicker one as a silent edit; every
other send and edit carries `AllowedMentions.none()` (asserted on the fake
transport).

Then by hand on the dev server: a DM, a mention in a channel, a mention in a
grant thread by a member, the same by an account that is not linked, two
people in one thread, Stop, and a bot restart mid-answer.

### D4. Commands and switches

`/mylo ask`, `/mylo forget`, `/mylo chat on|off`, `/mylo chat here on|off`,
`/mylo chat guests full|no-people|public|off`, the Stop button, DM question buttons, the hourglass reaction, message-delete
handling.

Accept when: each command is refused by the gate for the wrong person and
audited; `forget` blanks only the caller's own text; a channel turned off
refuses with the "ask in a DM instead" line; `/mylo chat off` is respected on
the next question.

### D5. Learning, retention, docs, smoke

Hook the DM thread into the quiet-thread pass; confirm shared threads are
skipped; retention rules above in `tasks.retention_sweep`; thread-delete and
binding-removal handling; `manage.py smoke_agent_discord` (a scripted
end-to-end run against the fake transport and the real model);
`docs/api-contract.md`, `docs/architecture.md`, `docs/repo-map.md`,
`docs/skills/configure.md`, `tools/agent/README.md`, the `discord-bot` skill
doc, `docs/changelog.md`.

```bash
make test
make tools-check
uv run --no-sync python manage.py smoke_agent_discord
```

Accept when: a member's question in a consented channel produces one ambient
observation and in an unconsented channel none; a guest's produces none
anywhere; a DM produces observations only through the agent path; deleting a
Discord thread deletes its conversation; the smoke run passes on the local
model.

## Interfaces that change

| Kind | Change |
| --- | --- |
| Settings, `[tools.agent]` | `discord_access` (`public`\|`linked`\|`entitled`, default `public`), `discord_guest_daily_turns` (10), `discord_place_daily_turns` (200), `discord_channel_session_hours` (24), `discord_closed_thread_days` (30), `discord_ping_after_minutes` (10), `discord_turn_timeout_minutes` (30), `discord_guest_level` (`full`\|`no_people`\|`public`\|`off`, default `full`) |
| Schema, `agent` | `AgentThread.user` nullable, `AgentThread.shared`; `AgentQueuedMessage.speaker`, `.turn`; `AgentOrgPolicy.discord_guests`; new `AgentThreadLink`, `AgentDiscordTurn` |
| HTTP | `GET`/`PATCH api/tools/agent/policy/<kind>/<ref>/` carries `discord_guests` and, read-only, the host's ceiling. No new route |
| Schema, `delivery` | index on `AnnouncementPost.thread_id` |
| Framework | `AgentFunction.guest` (a level, default none); reference kind `announcement` |
| Platform | `resolve.place_for`; `gate` actions `chat`, `chat_guest` |
| Bot | `cogs/chat.py`, `chat.py`, `chat_render.py`; five `/mylo` subcommands; DM behaviour change |
| HTTP | none |

No new gateway intent. Bot permissions needed where it answers: Send Messages,
Send Messages in Threads, Read Message History, Embed Links, Add Reactions
(optional).

## Security checklist

- Identity comes from the gateway event, never from message text.
- The one authorization path is `gate.authorize` / `authorize_guest`, then the
  agent's own gate. The cog and the bridge decide nothing.
- Audience by place; functions by asker; guests by a declared level per
  function, capped by the host and then by the lab.
- For a guest, the Discord server's own membership and channel permissions
  are the access control, and being in the server is treated as trust
  (S-16). Whoever a lab lets into its server can ask Mylo what a member could
  ask there, its people included, unless the host or the lab lowers the guest
  level. The setup flow says so in one line and names the command.
- Other people's text in a thread is context for a turn, never an instruction
  to change what the asker may see. Tool results stay inside the turn that
  fetched them.
- Model output cannot ping anyone or pose as a mention. The only ping is the
  asker's own, on a slow answer.
- Rate limits: the gate's bucket per person, the two daily settings, the
  five-deep queue.
- Tier gate: `discord_access` decides the person's side; the lab's or
  department's `bot_server` entitlement is always required.
- Background work: Celery only (turns, retention sweep, stuck-turn resume).
  Nothing joins `mylo-daily.timer`.

## Exclusions

- "Hey Mylo", the Message Content intent, and any reading of messages not
  addressed to Mylo (S-4). If this is wanted later it is a consent decision
  first and a small code change second.
- Showing shared conversations in the web app.
- Files and attachments in shared places.
- Voice, images, reactions as input, and message edits as new questions.
- Mylo starting a conversation on its own, or posting an answer anywhere but
  where it was asked.
- Unbound servers.
