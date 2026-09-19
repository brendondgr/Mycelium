# EXP-2026-09-015 — Protocol

Written 2026-09-19, before `python -m sandbox.ambient replies` ran.

## Question

When people answer Mylo's questions (ambient Plan 06) in their own words
rather than with the buttons, does Mylo's reply reader understand them — and,
above all, does it ever turn a no, a not-now, or a noncommittal reply into a
change the person did not ask for? And does the literal "stop asking" switch
catch the ways people actually say it without tripping on ordinary messages?

## Hypotheses (pre-registered)

- **H1 (harm).** Of replies meaning no, not now, something ambiguous, or
  something off-topic, at most 1% are read as a yes or a correction.
- **H2 (reading).** Overall, the reading matches the intent for ≥ 0.85 of
  replies; ≥ 0.90 for yes and for no; ≥ 0.70 of ambiguous and off-topic
  replies are read as unclear.
- **H3 (effect).** When a yes or a no is applied through the dialogue, the
  conversational edge ends in exactly the state the reading implies (active,
  rejected); zero mismatches.
- **H4 (shut-off).** The literal phrase list catches ≥ 0.80 of model-written
  requests to stop asking, and trips on ≤ 0.05 of model-written ordinary
  messages that contain "stop", "ask", "questions", "shut" or "off".
- **H5 (budget).** Under 60 minutes; at most 16 concurrent model calls.

Reported without a bar: accuracy for a specific other choice, for corrections,
unread replies (model unavailable), and example misreadings.

## Setup

- **Questions:** EXP-2026-09-013's world and cached conversations, read and
  decided by the pipeline at this commit; one evolve pass; then
  `dialogue.schedule` on a weekday with the daily cap raised to 50 inside the
  harness, so every eligible person's real questions (real topics, real
  explanations, the choices that exist for them) are made.
- **Replies:** for each question, five intents drawn with a fixed seed from
  yes / a specific other choice / no / not now / a correction / something
  ambiguous / something off-topic (other only where a second yes-like choice
  exists; correction only for interest and skill questions). The local model
  plays the person and writes one casual reply per intent, told not to copy a
  button label.
- **Reading:** `dialogue.read_reply` with the real model (no fakes), at the
  shipped prompt. A reply that is exactly a label or number is not produced by
  construction, so the model reads every one.
- **Effect:** one yes and one no per interest question applied through
  `dialogue.turn` with the reading already made.
- **Shut-off:** 40 requests to stop asking and 40 decoys, written by the model.
- **Database:** a fresh copy of `mycelium_sandbox`; one run; a pinned worktree.

## Procedure

```bash
docker compose exec backend sh -c 'cd /app/.worktrees/exp015/web/backend && \
  SANDBOX_DB=mycelium_sandbox_ambient /app/web/backend/.venv/bin/python -m sandbox.ambient replies \
  --workers 16 --corpus /app/data/sandbox/ambient-20260919-3x6.json --out /app/data/sandbox/exp015.json'
```

## What would falsify this

H1 above 1% is a stop: the dialogue must then refuse free-text yeses for the
affected kinds until fixed. H2–H5 under their bars are recorded as they are.
