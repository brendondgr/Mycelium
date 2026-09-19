# EXP-2026-09-013 — Protocol

Written 2026-09-19, before the harness (`sandbox.ambient`) ran.

## Question

Given four weeks of realistic lab conversation with known, planted
statements, does ambient Plan 04 (hourly reading, nightly deciding) find what
people actually said about themselves and their projects, decide the right
outcome for each topic, and keep every privacy promise while doing so?

## Hypotheses (pre-registered)

- **H1 (harm checks, all must be zero).** An observation or finding for the
  person who never opted in; an observation or explanation sharing a 6-word run
  with any message (a quote); an observation with `origin = rule`; a message
  body still in the buffer after its window was read; a lab-visible finding
  resting on a personal observation; a suggestion or capability for a person
  resting only on observations whose subject is not `self`; an explanation
  naming a date not among its notes.
- **H2 (extraction recall).** Of the planted statements that made it into the
  generated conversation, ≥ 0.70 yield an observation from the right speaker,
  on the right message, whose topic matches the planted topic.
- **H3 (reading quality).** Among matched observations, the kind is right for
  ≥ 0.80 (interest kinds — enduring interest, current curiosity — count as
  one), and a colleague's idea is read as `self` for ≤ 0.20 of colleague plants.
- **H4 (deciding).** Across planted topics with an expected outcome, the
  decided outcome matches for ≥ 0.75; and the false-suggestion rate — a
  suggest or capability outcome for a one-off, colleague, rejected or
  already-declared topic — is ≤ 0.05.
- **H5 (explanations).** ≥ 0.90 of non-ignore findings get an explanation.
- **H6 (budget).** Every phase that calls the model finishes, and the whole run
  under 60 minutes, with at most 16 concurrent model requests (the relay
  allows 32; the other half is left for other users).

Reported without a bar: observations not matching any plant (a strict
precision — filler conversation can contain real statements), force and
subject accuracy, refusal codes, and outcome confusion.

## Setup

- **World** (fixed seed): three labs, each with six opted-in, paid, linked
  people, one linked member who never opted in (their messages must be
  dropped at the edge), two lab projects with every member on them, and a
  personal DM surface per person. Every person has two or three declared
  areas; one person per lab has a full set of clusters (the cap), so the
  budget's swap path runs.
- **Plants** per opted-in person (topics drawn without replacement from a
  pool of distinct research topics):
  1. an emerging interest — three preferences on three days ≥ 5 days apart,
     in different conversations → **suggest**;
  2. a one-off — one mention → **ignore**;
  3. a colleague's idea — two mentions with subject colleague → **ignore**;
  4. a capability — two first-person "I ran / built" statements → **capability**;
  5. a learning goal — two "I want to learn" statements → **suggest**;
  6. a rejected possibility — a possibility, then later a rejection → **ignore**;
  7. a declared area — two preferences about an area they already declared →
     **ignore (covered)**;
  8. a project fact told to Mylo in a DM → **record**.
- **Conversations.** The local model (`default-model` via the relay) writes
  each day's conversations: the harness hands it the day's plants, each with
  its speaker and topic phrase, and asks for 6–12 realistic messages in which
  each plant is said once, by its speaker, using the topic phrase, among
  filler. A plant that does not appear (speaker, topic phrase) is dropped from
  the truth and counted. Generated text is cached; conversations are fake and
  name nobody real.
- **Pipeline under test:** messages enter through `service.heard` (the
  gateway's door), are read by `reading.read_ready` with the real extractor
  and model, then `deliberate.deliberate` and `explain.explain_pending`. The
  buffer is a local in-process cache for the run. The embedder is the real
  one. Settings are the shipped defaults.
- **Database:** a copy of `mycelium_sandbox` (`mycelium_sandbox_ambient`); one
  run per database.

## Procedure

```bash
docker compose exec backend sh -c 'cd /app/web/backend && \
  SANDBOX_DB=mycelium_sandbox_ambient uv run --project . python -m sandbox.ambient all \
  --workers 16 --out /app/data/sandbox/exp013.json'
```

## What would falsify this

Any H1 violation; H2–H6 under their bars. A failure is recorded as it is;
a fix is reported as a separate, post-hoc arm and never replaces the verdict.
