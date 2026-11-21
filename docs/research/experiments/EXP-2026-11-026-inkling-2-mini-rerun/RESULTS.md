# EXP-2026-11-026 — Results

**Status: running.** Each part is recorded and committed as it finishes;
sections for parts not yet finished say so. Every number below comes from
`tables/part<N>.md` and `data/metrics.json` (`code/analyse.py`). Gemma 4 31B's
and Qwen 3.8 27B's numbers there are read from the source experiments' files.

## 1. Headline

So far (parts 1–2 of 7): on Inkling 2 Mini, Mylo answered every turn,
leaked nothing on the model check's five access probes and gave all six
entitled askers their answer, as on both earlier models; it reached full
credit on 8 of 12 graded questions (Gemma 12, Qwen 10), every miss naming an
extra object. It decodes about twice as fast as Qwen 3.8 27B, but makes 2–3
times as many model calls on multi-step questions, so only one-lookup
questions are faster (median 2.2 s idle, 3.7 s with 8 at once).

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

Run 2026-11-21 17:39–18:07 UTC, alone on the server: 36 turns one at a time
(3 repetitions of 12 questions per group), then 96 turns from 8 processes at
once; code `a99e1a01`, harness `run_a6.py` (the Qwen row's). Tables:
`tables/part2.md`.

| Run | One lookup | A few | Compound | Turns |
|---|---:|---:|---:|---:|
| Qwen 3.8 27B, idle (A6) | 1.78 (3.14) | 9.12 (12.57) | 22.32 (61.85) | 36 |
| Qwen 3.8 27B, 8 at once (A6) | 5.39 (11.01) | 24.34 (43.44) | 67.1 (117.65) | 96 |
| Gemma 4 31B, idle (A5) | 14.4 (16.85) | 28.08 (58.12) | 63.18 (75.09) | 36 |
| Gemma 4 31B, 8 at once (A5) | 17.87 (27.91) | 39.05 (92.9) | 78.95 (109.22) | 96 |
| Inkling 2 Mini, idle | 2.23 (4.67) | 15.39 (87.44) | 61.97 (103.17) | 36 |
| Inkling 2 Mini, 8 at once | 3.66 (10.21) | 28.26 (82.66) | 124.66 (215.79) | 96 |

Median (worst) seconds to a complete answer.

**Analysis.**
- *Every turn finished:* 36/36 and 96/96 turns ended with text, none timed
  out; 1 and 3 model calls hit the reply cap and the same number came back
  empty (the loop recovered in every case).
- *The model is fast; the turns are not.* Inkling produces about twice Qwen's
  completion tokens per second of call time when idle (177–197 against
  88–103), and about three times with 8 at once (79–82 against 22–29). On
  one-lookup questions, where both models make 1 function call and 2 model
  calls, it is about as fast as Qwen when idle (median 2.23 s against 1.78 s)
  and faster with 8 at once (3.66 s against 5.39 s).
- *It does more work per question.* On "a few" questions it makes a median of
  9 function calls and 8 model calls (Qwen 5 and 5.5) and reads 55.7k tokens
  per turn (Qwen 21.4k). On compound questions it makes 37.5 function calls
  and 24 model calls (Qwen 20.5 and 8.5) and reads 347k tokens (Qwen 63.5k,
  about 5.5 times as many). It also writes about 2–7 times as many completion
  tokens per call (mostly reasoning). So its compound turns take about as long
  as Gemma's when idle (62.0 s against 63.2 s) and about twice Qwen's with 8 at
  once (124.7 s against 67.1 s).
- *For the paper:* a 3B-active model serves a one-lookup question in about
  2 s, but the gain in decoding speed is spent on longer loops for multi-step
  questions. Whether those extra calls buy correctness is part 4's question.
- *Comparability:* Qwen's A6 ran on the 2026-11-16 code and Gemma's A5 on
  round two's; Inkling ran on `a99e1a01`, after the overnight fixes.
  EXP-2026-11-010 A7 found the fixes left Qwen's calls per turn unchanged
  (1 / 2 / 6.0k on one-lookup questions), so the call counts above are a
  property of the model, not of the newer code.

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
