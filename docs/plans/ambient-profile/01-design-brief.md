# Plan 01 — Design Brief (the discussion gate)

**Status:** approved by the owner on 2026-09-18 with the instruction to
implement Plan 01 end to end. **Correlation ID:** `20260917-ambient-profile-01`.

This is the artefact Plan 01's discussion gate requires: what is being changed,
how, with what defaults, and what is deliberately not being done. It is written
before the code and updated when the code forces a change, so a reader can tell
the design from the drift.

## What is being built

The `ambient` Django app: the platform-independent evidence ledger, the consent
surface that decides whether anything is recorded, the transient raw buffer, the
adapter contract, retention, deletion, and the read API downstream stages use.

Nothing in Plan 01 touches a profile, a project, a report, or a recommendation.
Nothing in Plan 01 calls a model. There is no HTTP surface — the ingest endpoint
belongs to Plan 02 — and the app ships **off** (`AMBIENT_ENABLED=false`).

## Phases, each its own commit

| # | Phase | Delivers |
|---|---|---|
| 1 | The app and its consent surface | `apps/ambient`, `Source`, `ListeningConsent`, `eligibility.py`, settings, docs |
| 2 | The transient buffer | `buffer.py` (Redis, TTL, explicit delete), `RawMessageRef`, the content hash |
| 3 | The ledger | `Observation`, `ObservationFeedback`, `Retraction`, constraints |
| 4 | The adapter contract | `adapters/base.py`, the fake adapter, the record path end to end |
| 5 | Retention, reconciliation, deletion | the purge task, edit/delete reconciliation, retraction fan-out, "delete my observations" |
| 6 | The read API and the boundary | `read.py`, the import-graph guard, admin, docs |

## Models and migrations

One app, one migration per phase that adds tables. No existing table is altered
and no existing row is touched, so every migration is additive and reversible.

* **`Source`** — kind (`discord_guild`, `discord_dm`, `slack_workspace`,
  `teams_team`, `transcript`), `external_id`, cached `label`, nullable `lab`,
  `consent_state` (`pending` / `active` / `paused` / `revoked`), who changed it
  and when, and an optional `raw_ttl_hours` override that can only *shorten* the
  buffer window. Unique on (`kind`, `external_id`).
* **`ListeningConsent`** — (`user`, `platform`) unique, `enabled` default false,
  `questions_muted` for the "shut off" switch. An absent row reads as off, so
  opt-in is the default by construction rather than by a flag.
* **`RawMessageRef`** — external ids, timestamps, the speaker, the place, and a
  content hash. **No body.** It exists so a platform edit or deletion can be
  reconciled against what was derived from it.
* **`Observation`** — the durable record. Mylo's own account of what was said,
  the dates, the kind of place, the subject, the force, the project and its
  confidence, the understanding kind, visibility, provenance, supersession.
  **There is no quote column and no message body, on any table.**
* **`ObservationFeedback`** — append-only; the person's own verdict.
* **`Retraction`** — what was removed and what must therefore be recomputed.

## Settings and defaults

| Setting | Default | Why |
|---|---|---|
| `AMBIENT_ENABLED` | `false` | Reading what people say to each other is a deliberate decision, never an inherited default |
| `AMBIENT_RAW_TTL_HOURS` | `6` | OD-01b. The buffer is deleted explicitly after a window is read; the TTL is the safety net |
| `AMBIENT_RAW_TTL_HOURS_MAX` | `24` | A hard ceiling no per-source override can raise |
| `AMBIENT_REPEAT_WINDOW_DAYS` | `30` | A re-pasted link is one piece of evidence, not three |
| `AMBIENT_CACHE_URL` | Redis db 6 | Its own db — never the Celery broker or a shared cache |

## Prompts and model calls

**None in Plan 01.** Extraction and explanation are Plan 04's. The ledger stores
what a model wrote; it does not write it. There is therefore no
model-unavailable path to design here — Plan 04 owns principle 18 (the stage
skips that night and is retried; nothing rule-based stands in).

The one place the convention shows up early is `Observation.origin`, which
records `model` or `rule`. It exists so Plan 10's harm check ("zero
`origin = rule`") is a query rather than an assumption.

## What is deliberately not being done

* **No HTTP endpoint.** Plan 02 owns `/api/ambient/ingest/`; Plan 07 owns the
  review and settings endpoints. `docs/api-contract.md` is therefore untouched.
* **No Discord code.** No cog, no intent, no gateway change. The adapter written
  here is a fake, used by the tests.
* **No extraction, no attribution, no deliberation, no questions.** An
  observation's `project`, `influence`, and `explanation` are written by later
  plans; the columns exist and stay null.
* **No profile or project writes.** The app imports from `integrations` and
  `research`; it is imported by `content` only through `read.py`.
* **No attachment ingestion** (OD-01a): a pasted PDF contributes its URL, never
  its content.
* **No `context_version`** yet — the column is nullable and Plan 05 fills it.

## Deviations from the plan text, and why

* **`speaker_kind` sits on the raw reference, not on the observation.** Plan 01
  §4 lists it on `Observation` while also requiring `speaker` to be a Mycelium
  user, and Mylo has no Mycelium account — so a `mylo` observation could never
  be saved. The distinction is real but belongs where it applies: Mylo's own
  messages are buffered so a window reads coherently, and Plan 04 excludes them
  from evidence. Every observation has a linked human speaker.
* **`ListeningConsent` is introduced here** rather than in Plan 07. Plan 01 §4
  requires ingest to check that the person opted in, so the row that records
  that has to exist before anything can be ingested. Plan 07 builds the settings
  UI over it.
