# EXP-2026-09-002 — Results

Run 2026-11-12 under Amendment 1 (PROTOCOL.md). Every number is read from
`data/metrics.json` (written by `code/analyse.py` from `data/census.json`,
`data/rebuild.json` and `data/inject.json`).

## 1. Headline

**Removal precision could not be measured, and C-025 stays `unsupported`.**
The live instance has 71 weeklies, but 64 were written by the code fallback;
the 7 model-written ones (all the week of 2026-11-09, 31 project sections,
1,137 checked sentences) had **0 sentences removed**, and their evidence
packets are not stored and could not be rebuilt faithfully (0 of 7). On an
injected-error set built from real weekly sentences, the deterministic checks
caught **every** unresolvable citation (38/38) and invented percentage (38/38)
and **none** of 29 unsupported paraphrases — the precise failure the hypothesis
predicted.

## 2. Results table

| Measure | Value |
|---|---:|
| Weeklies on the instance (fallback / model-written) | 71 (64 / 7) |
| Model-written project sections | 31 |
| Sentences checked, all weeklies / model-written only | 2,295 / 1,137 |
| Sentences removed by the checks | 0 |
| Packets rebuilt / faithful (references identical and re-verification clean) | 7 / 0 |
| Re-verification of stored text against today's packet: sentences removed per weekly | 0–17 |
| Re-verification sentence counts equal to the stored counts | 7 of 7 |

Injected errors, one per copy, checked with `verify_line` against the rebuilt
packet (Wilson 95% intervals):

| Error class | Copies | Caught | Recall | 95% CI |
|---|---:|---:|---:|---|
| `[P#]` that the packet does not have | 38 | 38 | 1.00 | 0.91–1.00 |
| Number in the sentence changed in place | 2 | 1 | 0.50 | 0.09–0.91 |
| Invented percentage appended | 38 | 38 | 1.00 | 0.91–1.00 |
| Unsupported paraphrase, no new numbers (model-written) | 29 | 0 | 0.00 | 0.00–0.12 |

## 3. Figures

None.

## 4. Interpretation

- The protocol's question — does the verifier agree with a person — has no
  answer yet, for two separate reasons: the model-written weekly has only just
  started (one week), and when it ran the checks removed nothing, so there is
  no removal to judge. A precision measurement needs removals.
- **The weekly cannot be audited after the fact.** The re-verification counts
  match the stored counts exactly (the split of model-written text is right),
  but the packet a weekly was checked against is not stored, and today's
  rebuild differs from it in every case (references lists differ in all seven,
  and re-checking against today's packet would remove up to 17 sentences that
  were legitimately supported when written). Storing the packet — or at least
  its references and the numbers it contains — with each weekly is what makes
  C-025 measurable.
- The injection result matches the hypothesis's mechanism: the deterministic
  checks are a citation and number checker. An error that changes meaning
  without introducing a citation or a number passes untouched. Whether the
  optional entailment check (`EntailmentFn`) recovers that is untested here.
- Zero removals in 1,137 sentences is consistent both with a writer that stays
  inside its packet and with checks that rarely fire; this run cannot tell
  the two apart.

## 5. Threats to validity

- The injected errors are made by rule and judged by construction, not by a
  person; they measure recall on the error types built, not on the errors the
  writer actually makes.
- The packet used in the injection is today's rebuild, not the original;
  errors are relative to the packet given, so the test is internally
  consistent, but it says nothing about the original packets.
- 38 base sentences from 7 weeklies of one week; the in-place number class
  has n = 2.
- The paraphrase copies were written by the instance model; a few may by
  chance be supported by the packet, which would understate recall (it is
  already 0).

## AMENDMENTS

Amendment 1 (2026-11-12), in PROTOCOL.md, written before any labelling:
census, faithful-rebuild test, injected-error recall in place of the labelling
sheet.
