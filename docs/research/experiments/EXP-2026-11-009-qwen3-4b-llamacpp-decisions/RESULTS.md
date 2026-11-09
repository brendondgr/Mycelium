# EXP-2026-11-009 — Results

**Model:** Qwen3-4B, `Q4_K_M` GGUF, on llama.cpp `llama-server` `b11912`
(Vulkan, Radeon 8060S), thinking off. **Path:** Mycelium's
`[decision] backend = "port"`, `openai` protocol (first-token logprobs).
**Data:** the 165 states of `EXP-2026-11-007`. Every number is read from
`data/metrics.json`, written by `code/analyse.py`.

## 1. Headline

The llama.cpp path works — 165/165 answered, deterministic, and llama.cpp runs
calls in parallel (22.8 calls/s at four in flight against 7.2 at one). But a
stock Qwen3-4B read through logprobs is **useless as a ranker**: it answered
`worth` ≥ 0.999995 for every pair, on- or off-theme, so its AUC is 0.489 and it
is 0.201 *below* d3-lite (95 % paired bootstrap [−0.280, −0.129]). The prior is
refuted.

## 2. Results table

<!-- BEGIN GENERATED TABLE -->
| Worth AUC (on- vs off-theme) | Qwen3-4B (llama.cpp) | d3-lite (decide) |
| --- | ---: | ---: |
| All (n=45 pairs) | 0.4889 | 0.6899 |
| paper (n=15) | 0.4667 | 0.8267 |
| grant (n=15) | 0.5 | 0.5378 |
| conference (n=15) | 0.5 | 0.7644 |

Difference -0.201, 95% paired bootstrap [-0.2798, -0.1286] (2000 resamples, seed 0).

| Throughput (synthetic state) | Calls/s | p50 ms |
| ---: | ---: | ---: |
| 1 in flight | 7.189 | 139.2 |
| 4 in flight | 22.792 | 128.3 |
| 8 in flight | 13.427 | 672.9 |
<!-- END GENERATED TABLE -->

## 3. Figures

None.

## 4. Interpretation

- **The transport is proven.** Protocol detection, the logprob readout, thinking
  suppression, and the production questions all work against a real
  llama.cpp server; a hand-made off-topic probe (a steel-corrosion paper for a
  neuroscientist) came back `no` with `yes` at log-probability −9.9, so the
  readout is not stuck on yes.
- **The model, not the plumbing, saturates.** On real states the reader's
  profile spans every theme, and the stock model answers as if asked "is this
  relevant to this researcher at all?" — always yes — with essentially no
  probability left for no. An instruction-tuned model's first-token
  distribution is not a calibrated probability, which is the whole reason
  decision models (d3-lite, pplx-decider, Jev) exist.
- **Throughput favours llama.cpp.** With 8 slots it served 3.2× the decide
  server's single-flight rate at four in flight. Eight in flight was slower
  than four (13.4 calls/s), likely slot churn evicting the per-slot prompt
  cache on a 48-call run; not investigated.
- **What this means for the switch:** keep the `openai` protocol (it is the
  right way to host a fine-tuned student, plan Phase 3/5), but do not point the
  nightly at a stock instruct model. The candidates are a real decision model
  behind the decide protocol (pplx-decider via a GAIFA adapter) or a model
  fine-tuned on Jev's judgements.

## 5. Threats to validity

- One model, one quantization, one prompt template. A prompt that hides the
  full profile and shows only the strand, or a larger model, could behave
  differently; neither was tried (follow-up).
- The off-theme control is noisy (see `EXP-2026-11-007`), but that cannot
  explain a model that gives every pair the same answer.
- Throughput on a synthetic ~400-character state; real states took 554 ms per
  pair sequentially (3-4 questions each).

## 6. What surprised us

How total the saturation was: 156 of 165 fit scores are exactly 3.0, and
grant eligibility is 1.0 everywhere — not a weak signal, no signal.

## 7. Follow-ups

- Q-062: Does showing a stock model only the strand (not the full profile), or
  asking it to compare two items, give any ranking signal — or is a decision
  model / fine-tune the only route?

## 8. Reproduction

See `PROTOCOL.md` §Procedure. Needs the scratch `states.json` from
`EXP-2026-11-007` (not committed — it holds profile text) or a fresh
`extract.py` run, which will give different slates.

## AMENDMENTS

**2026-11-09: the throughput comparison was unfair, and the conclusion is
withdrawn.**

- §4 says "throughput favours llama.cpp" (3.2× d3-lite). That set llama.cpp's
  8 slots against d3-lite behind GAIFA's decide server, which handles one
  request at a time.
- Both were measured on the ~400-character synthetic state.
- `EXP-2026-11-012` then measured both like for like on the 165 real states:

| Model | Pairs/s, real states |
| --- | --- |
| Qwen3-4B on llama.cpp, 1/4/8 in flight | 1.80 / 1.50 / 1.59 |
| d3-lite, 1/4/8 pairs per pass | 2.32 / 2.22 / 2.26 |

On production input d3-lite is about 1.4× faster, and concurrency helps
neither model. The quality findings above are unaffected.
