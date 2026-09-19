# EXP-2026-09-021 — Protocol

Written 2026-09-19, before the run.

## Question

Ambient Plan 11 states its own test: adding a platform must change nothing
outside `apps/ambient/adapters/` and `apps/integrations/`. If it did, the
Plan 01 abstraction was wrong. So: do the same conversations, from the same
people, with the same consent, produce the same ledger on Slack and on Teams
as on Discord?

## Hypotheses (pre-registered)

- **H1 (people's messages).** The multiset of messages kept is identical to
  Discord's on Slack and on Teams: 0 differences. Messages are compared by
  (speaker, content hash) and read from `RawMessageRef`.
- **H2 (what is dropped).** The drop counters by reason (`SourceActivity`) are
  identical to Discord's on both platforms. This covers not opted in, no
  account, too short and bot.
- **H3 (Mylo's own lines).** Slack keeps as many of Mylo's own DM lines as
  Discord does. Teams keeps none, by construction: the Bot Framework does not
  deliver a bot's own messages. The count not delivered is reported. It is a
  known difference, not a failure, and its consequence is written up.
- **H4 (the full stack).** Every Slack request and Teams activity passes its
  real endpoint, including signature or token verification (no 401) and with
  no error.
- **H5 (budget).** Under 30 minutes. No model is called.

## Setup

- World and corpus: EXP-2026-09-013's
  (`data/sandbox/ambient-20260919-3x6.json`, seed 20260919). Unknown speakers
  are kept, so the no-account drop is exercised on every platform.
- `python -m sandbox.ambient platforms` (`sandbox/ambient/platforms.py`):
  - one fresh copy of `mycelium_sandbox` (`mycelium_sandbox_ambplat`),
    migrated at the pinned commit;
  - the world seeded, then each platform's replay inside a transaction that
    is rolled back;
  - for Slack and Teams, each Discord identity mirrored as a Slack or Teams
    identity, the same opt-ins on that platform, and each lab's workspace or
    team listening.
- Slack requests are signed with a sandbox secret. Teams activities carry an
  RS256 token signed by a key made at run time, whose public half the auth
  module is given in place of Microsoft's.

## Procedure

```bash
docker compose exec -T backend sh -c 'cd /app/.worktrees/exp021/web/backend && PYTHONDONTWRITEBYTECODE=1 \
  SANDBOX_DB=mycelium_sandbox_ambplat /app/web/backend/.venv/bin/python -m sandbox.ambient platforms \
  --corpus /app/data/sandbox/ambient-20260919-3x6.json --out /app/data/sandbox/exp021.json'
```

## What would falsify this

Any difference in H1 or H2 means something past the adapter behaves
differently per platform, and it is fixed there. Any 401 or error in H4 does
too.
