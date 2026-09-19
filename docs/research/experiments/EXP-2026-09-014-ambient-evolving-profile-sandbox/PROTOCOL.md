# EXP-2026-09-014 — Protocol

Written 2026-09-19, before `python -m sandbox.ambient nights` ran.

## Question

Over the eight weeks after Plan 04 has read a lab's conversation, does the
evolving profile layer (Plan 05) keep its promises every night — only what a
person said yes to is ever in effect, the declared profile never changes,
explorations fade unless the person keeps coming back, "forget that" and
"delete my observations" take everything they must, private developments stay
private — and do confirmed explorations, with the ranking hook on, get their
own relevant slate without crowding the declared themes?

## Hypotheses (pre-registered)

- **H1 (invariants, every night, all must be zero).** An active
  conversational edge the person never said yes to; a declined edge that is
  anything but rejected; any change to any declared profile; a non-active edge
  among confirmed explorations or among ranking edges; any conversational edge
  from collaboration search's read (`discoverable_edges`); an edge or finding
  left for a person who opted out with deletion; an edge citing a deleted
  observation; an undone development back in effect; a lab-visible development
  resting on a private observation; a private development returned to a lab
  reader.
- **H2 (fading).** No confirmed curiosity is still active more than 42 days
  (two half-lives) after its last reinforcement; no reinforced exploration
  fades within 42 days of being reinforced; no capability fades.
- **H3 (ranking, weight 0.15).** Declared-theme slates are unchanged by adding
  exploration themes (mean Jaccard ≥ 0.95); an exploration's slate is mostly
  its own topic (precision ≥ 0.60); on average at most one declared item is
  displaced from a person's global top 25.
- **H4 (budget).** Under 60 minutes, at most 16 concurrent model calls.

Reported without a bar: weight 1.0 (no cap) against 0.15 on the same measures;
answers given; faded counts; context-version moves.

## Setup

- **World and first pass:** EXP-2026-09-013's world and cached conversations,
  read and decided by the pipeline at this commit (prompt `a4`) — the same
  steps as that experiment, re-run here so this run starts from its own state.
- **Nights:** 0, 7, 14, … 56 days after the first pass, the clock frozen at
  each (`mock.patch` of `timezone.now`); each night runs `deliberate` then
  `evolve`. After each night every pending suggestion is answered as the
  planted truth says: yes to a person's own emerging interests, learning goals
  and capabilities (a curiosity confirmed with a review in 30 days), no to
  anything else. Answers are written with the knowledge core's
  `confirm`/`reject` (Plan 06's dialogue does not exist yet).
- **Events:** night 7, one told development per lab is undone; night 14, one
  person per lab opts out with deletion and another forgets one observation;
  nights 21 and 35, half of the confirmed explorations (fixed seed) are
  reinforced with two new consistent observations.
- **Ranking:** a templated paper corpus — four papers per topic in the world's
  pool (≈ 760) — embedded with the real embedder; for every person with a
  confirmed exploration, the production fusion (`fuse_clusters_pool`) runs on
  the declared interests alone and on interests plus exploration themes, at
  `AMBIENT_DRIFT_WEIGHT` 0.15 and 1.0.
- **Database:** a fresh copy of `mycelium_sandbox` (`mycelium_sandbox_ambient`);
  one run per database; run from a pinned worktree.

## Procedure

```bash
docker compose exec backend sh -c 'cd /app/.worktrees/exp014/web/backend && \
  SANDBOX_DB=mycelium_sandbox_ambient /app/web/backend/.venv/bin/python -m sandbox.ambient nights \
  --workers 16 --corpus /app/data/sandbox/ambient-20260919-3x6.json --out /app/data/sandbox/exp014.json'
```

## What would falsify this

Any H1 violation; H2 or H3 outside its bar. Failures are recorded as they are;
fixes are reported as post-hoc arms.
