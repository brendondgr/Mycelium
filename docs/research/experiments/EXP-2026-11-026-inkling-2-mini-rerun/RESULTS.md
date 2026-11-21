# EXP-2026-11-026 — Results

**Status: running.** Each part is recorded and committed as it finishes;
sections for parts not yet finished say so. Every number below comes from
`tables/part<N>.md` and `data/metrics.json` (`code/analyse.py`). Gemma 4 31B's
and Qwen 3.8 27B's numbers there are read from the source experiments' files.

## 1. Headline

So far (part 1 of 7): on Inkling 2 Mini, Mylo answered every turn of the model
check, leaked nothing on the five access probes and gave all six entitled
askers their answer — the same as both earlier models. It reached full credit
on 8 of 12 graded questions (Gemma 12, Qwen 10); every miss named an extra
object, none left an expected one out.

## 2. Results by part

### Part 1 — the model check (EXP-2026-11-021, paper Appendix C, Table 4)

Run 2026-11-21 17:35–17:39 UTC, 8 in flight, code frozen at `640d7fe0` (the
paper's "all fixes" rows). Table: `tables/part1.md`.

| Model | Code | Answered | Leaks / probes | Controls | Full credit / graded | Median s | Worst s |
|---|---|---:|---:|---:|---:|---:|---:|
| Qwen 3.8 27B | 640d7fe0 | 30/31 | 0/5 | 6/6 | 10/12 | 96.0 | 354.6 |
| Gemma 4 31B | 640d7fe0 | 29/31 | 0/5 | 6/6 | 12/12 | 36.7 | 67.2 |
| Inkling 2 Mini | 640d7fe0 | 31/31 | 0/5 | 6/6 | 8/12 | 22.2 | 68.3 |

**Analysis.**
- *Access rules:* nothing changes with the model, as expected for a rule
  enforced in code: 0 of 5 probes leaked and 6 of 6 controls were answered.
- *It answers:* 31 of 31 turns ended in an answer, with no clarifying
  question, give-up line, server failure or blank reply. (MiniCPM 4.7, the
  other 3B-active model tried, failed 10 of 31 on an unstable server.)
- *Correctness:* 8 of 12. Recall was 1.00 on all twelve, so every expected
  object was cited. The four misses are precision misses: the answer also
  named objects the gold does not list (g-f04 and g-f06 at 0.50; g-p07 at 0.25
  and g-p10 at 0.40). Qwen 3.8 27B missed g-p07 and g-p10 with exactly the same
  precision, so those two look like properties of the questions or the gold,
  not of this model. The two one-item-field misses (g-f04, g-f06) are
  Inkling's own. One row is a check, not an estimate; part 4 (60 questions ×
  3 runs) measures this properly.
- *Speed:* median turn 22.2 s. This is not a speed comparison, because the
  earlier rows ran on servers under different loads; part 2 measures speed.

### Part 2 — latency (EXP-2026-11-010, paper §4.5)

Running.

### Part 3 — access probes, rules in code vs in the prompt (EXP-2026-11-016, paper §4.1, Table 2)

Not started.

### Part 4 — answers graded against stored facts (EXP-2026-11-018, paper §4.4, Table 1)

Not started.

### Part 5 — collaborator scenarios (EXP-2026-11-019, paper §4.2, Table 3)

Not started.

### Part 6 — memory deletion, opt-out, isolation (EXP-2026-11-017, paper §4.5)

Not started.

### Part 7 — collaborator controls after the fixes (EXP-2026-11-019 r6, paper §4.3)

Not started.

## 3. Figures

None yet.

## 4. Interpretation

Written once the primary parts (3 and 5) are in.

## 5. Threats to validity

- The product is held at the commits the earlier models were measured on,
  not today's code, so each comparison changes only the model. A result here
  says nothing about fixes made since.
- The earlier models ran on a single A100 at W4A16; Inkling runs NVFP4 on the
  operator's server. Latencies compare the deployed configurations, not the
  architectures alone.
- Parts 3–7 share the server with each other (up to 120 requests in flight).
  This affects time per turn, not grades. Part 2 ran alone.

## 6. What surprised us

Nothing yet.

## AMENDMENTS

See `PROTOCOL.md` Amendment 1 (the first-reply wrapper for part 3 and the
restart after part 1).
