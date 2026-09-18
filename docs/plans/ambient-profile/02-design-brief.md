# Plan 02 — Design Brief (the discussion gate)

**Status:** approved by the owner on 2026-09-18 with the instruction to
implement the plan in full after Plan 01. **Correlation ID:**
`20260917-ambient-profile-02`.

## What is being built

Mylo listens to a whole activated Discord server, with consent, and hands what
it hears to the ledger Plan 01 built. People talk normally; nobody types a
command to be understood. Commands and a message action exist as conveniences
and nothing depends on them.

## Phases, each its own commit

| # | Phase | Delivers |
|---|---|---|
| 1 | The adapter, the gateway's door, and what is worth hearing | `adapters/discord.py`, `service.py` (the single ORM boundary), `filters.py`, channel rules, the explicit flag, per-day volume counters |
| 2 | The listen cog (Stage A) | `mylo/listening.py`, `mylo/bot/cogs/listen.py`: DMs, mentions, edits, deletions; the Stage B switch, off |
| 3 | Consent where people are | `/setup`'s Listening section, the pinned marker, the one-time member notice, `/mylo listening` |
| 4 | Observability and docs | `/mylo health` listening state, the run-analytics line, the skill/architecture/repo-map corrections |

## The one architectural deviation, and why

**There is no `/api/ambient/ingest/` endpoint, and no REST hop.** Plan 02 §5
describes the cog posting to the backend "the way `mylo.reporting` already talks
to the backend over REST". That is a misreading of the existing code:
`mylo.reporting` posts to **Discord's** REST API, not to Mycelium. The gateway
does not talk to Mycelium over HTTP at all — `mylo/mycelium.py` configures
Django in-process and `mylo/linking.py` runs every ORM call through
`mycelium.db(...)`, which is how `/activate`, `/activate-lab` and `/setup`
already work. One database, one schema, one migration history, no second
credential to hold.

So listening follows the same path: a new `apps/ambient/service.py` is the
single ORM boundary, mirroring `integrations/services/resolve.py`, and
`mylo/listening.py` calls it through `mycelium.db`. This keeps Plan 02's actual
requirement — *eligibility is decided on the backend, once, on arrival, with no
cache* — while dropping a network hop the architecture does not have. Adding an
authenticated HTTP endpoint would be a new public attack surface carrying raw
message text, for no gain.

The spooling in §5 goes with it. There is no outage to spool across when the
write is a local transaction; what remains is that a failed write is logged and
dropped rather than retried, because a lost message is a lost message and the
nightly extraction is not entitled to a queue of people's words on disk.

## Models and migrations

One migration, additive, on the `ambient` app:

* `Source.excluded_place_ids` — channels a manager said Mylo must never read.
* `Source.listening_marker_message_id` — the pinned "Mylo is listening" post,
  so it can be edited rather than duplicated.
* `RawMessageRef.explicit` — true when the person deliberately told Mylo
  (a DM, a mention, `/mylo note`, the message action). Plan 04 weights it.
* `SourceActivity` — per source per day: heard, dropped, stored, and the reason
  counts. This is the aggregate §4 permits for messages that are discarded, and
  it is keyed on the source and the reason, never on a person.
* `MemberNotice` — that a person was told once, by DM, that a server is
  listening. Without it the notice either never arrives or arrives repeatedly.

## Settings and defaults

| Setting | Default | Why |
|---|---|---|
| `MYLO_LISTEN_ENABLED` | `false` | Stage B. The Message Content intent stays off until Plan 10 has measured Stage A (OD-02a) |
| `AMBIENT_MIN_MESSAGE_CHARS` | `24` | Below this, with no link, a message is chatter |
| `AMBIENT_MAX_MESSAGE_CHARS` | `4000` | A pasted document is not a remark; it is truncated for the buffer |

`AMBIENT_ENABLED` from Plan 01 still gates everything.

## Prompts and model calls

**None.** Plan 02 carries messages; it does not read them. Extraction is Plan
04's, and principle 18 (model-written, no rule-based fallback) applies there.
The only judgements here are deterministic and deliberately dull: is this a bot,
is this channel excluded, is this long enough to be worth keeping.

## What is deliberately not being done

* **The Message Content intent is not requested and not enabled** (OD-02a).
  Stage A uses the paths that need no privileged intent: DMs, mentions, and the
  message action. Stage B is written, tested and shipped **off** behind
  `MYLO_LISTEN_ENABLED`, so turning it on later is a config change rather than
  a code change.
* **No dialogue.** Mylo acknowledges a DM briefly and says nothing else. What
  Mylo asks, when, and how is Plan 06's, and writing a provisional version here
  would be a second voice to unpick later.
* **No extraction, no attribution, no questions, no web UI.**
* **No reaction handling beyond recording it.** `on_raw_reaction_add` on Mylo's
  own messages is carried as an explicit signal; what a 👍 *means* is Plan 06's.
