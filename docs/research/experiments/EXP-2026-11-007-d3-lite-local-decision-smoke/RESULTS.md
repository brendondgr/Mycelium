# EXP-2026-11-007 — Results

**Model:** `d3-lite` (0.85B, `vllm-sr/d3-lite` @ `03560c2`) on the local
Decisions server, `127.0.0.1:5107`. **Data:** one reader's per-theme slates on
2026-11-09 — 120 on-theme pairs (top 8 of 5 themes × papers, grants,
conferences) and 45 off-theme controls. **Judgements:** none. Every number is
read from `data/metrics.json`, written by `code/analyse.py` from
`data/pairs.json`.

## 1. Headline

The local server works as a drop-in transport: 165/165 calls answered, p50
367 ms and p95 551 ms per call, fully deterministic. But d3-lite does **not**
meet the pre-registered discrimination bar: AUC **0.690** (bar 0.75) for
telling an item's own theme from a foreign one — good on papers (0.827),
borderline on conferences (0.764), near chance on grants (0.538).

## 2. Results table

<!-- BEGIN GENERATED TABLE -->
| Metric | Value |
| --- | --- |
| area_eligible_mean | 0.2865 |
| area_venue_fit_mean_off | 0.66 |
| area_venue_fit_mean_on | 0.8707 |
| availability | 1.0 |
| conference_auc_worth | 0.7644 |
| conference_verdict_exact | 0.4 |
| conference_worth_mean_on | 0.8132 |
| determinism_max_abs_diff_worth | 0.0 |
| discrimination_auc_fit | 0.4593 |
| discrimination_auc_worth | 0.6899 |
| discrimination_paired_win_rate | 0.8222 |
| fused_vs_worth_kendall_mean | 0.0619 |
| grant_auc_worth | 0.5378 |
| grant_verdict_exact | 0.2 |
| grant_worth_mean_on | 0.7918 |
| latency_server_ms_p50 | 366.7 |
| latency_server_ms_p95 | 550.6 |
| moved_share | 0.8167 |
| n_control | 45 |
| n_on_theme | 120 |
| n_pairs | 165 |
| paper_auc_worth | 0.8267 |
| paper_verdict_exact | 0.1 |
| paper_worth_mean_on | 0.5354 |
| verdict_exact | 0.2333 |
| verdict_n | 120 |
| verdict_spearman_fit | -0.2839 |
| verdict_within_one | 0.5833 |
| wall_seconds_main | 65.88 |
| worth_distinct_2dp | 57 |
| worth_mean_off_theme | 0.4961 |
| worth_mean_on_theme_top3 | 0.7195 |
| worth_saturated_share | 0.0667 |
<!-- END GENERATED TABLE -->

## 3. Figures

None.

## 4. Interpretation

- **The plumbing is solved.** `/v1/decide` takes a JSON state and a list of
  `yesno` / `choice` / `score` questions and returns a probability per answer —
  the same contract as Jev's Noul / Choice / Score. The production state from
  `typesafe_rerank.build_state` was sent unchanged; only the question objects
  needed translating (a Noul's true/false criteria fold into the `yesno`
  question text). A local backend for `apps/core/systemone.py` is a small
  transport, not a redesign.
- **Latency is fine for the nightly run.** Sequential, ~0.4 s per pair at
  ~2.3k-character states; a 400-pair target (5 themes × 4 types × 20) is about
  2.5 minutes before fingerprint reuse, which skips most pairs on a quiet night.
- **The `worth` yes/no reads the strand on papers.** 82 % of controls scored
  lower on the foreign theme than at home; paper AUC 0.827.
- **It is fooled by shared words on grants.** It rated a DoW *eye-vision*
  clinical trial award 0.96 for "Agentic AI & Orchestration" and an NSF
  Combinatorics program 0.95 — exactly the "matches only a shared word" case the
  question's own `no` criterion describes. Grant `eligible` averaged 0.29, which
  looks too harsh for a US university researcher (unverified).
- **The four-level `fit` Score is unusable on this model.** AUC 0.459 (chance)
  and Spearman −0.28 against the stored verdict; its argmax favours `read`
  (74/120). Production sorts by `worth`, not `fit`, but `fit` feeds the stored
  verdict, so a local backend should drop or reword it.
- **Reference, not a paired baseline:** on 2026-09-17 slates Jev scored 0.561
  exact / 0.772 within-one against the same kind of stored verdict, and
  averaged worth 0.36 to d3-lite's ~0.72 here — d3-lite is the far more
  generous judge.

Nothing here supports or refutes a claim in `CLAIMS.md`; it is a go/no-go for
building the local path, and the answer is "build the transport, do not ship
d3-lite as the judge".

## 5. Threats to validity

- **The control is noisy.** "Off-theme" means a theme whose slate does not hold
  the item, not a theme it is irrelevant to; one reader's five themes overlap
  (agentic AI, knowledge graphs, healthcare AI…), and the fused ranker itself
  places some off-topic items in a theme (an enterprise-architecture paper in
  the healthcare slate). This caps the AUC any judge could reach; Jev was not
  run on the same control, so the gap between models is unmeasured.
- **The stored verdict is a system output,** partly the prose model's call and
  partly rank-band fallback (`verdicts.derive_verdict`), so verdict agreement is
  weak evidence in either direction.
- **n is small:** 15 controls per content type; the per-type AUCs are wide.
- **Question translation:** folding criteria into the `yesno` text is our
  choice; the server has no criteria field, and another wording could score
  differently.

## 6. What surprised us

How different the two questions behave on the same call: `worth` separates
themes on papers while `fit` is at chance. And how generous d3-lite is overall
— its on-theme worth mean is double Jev's.

## 7. Follow-ups

- Q-059: Does a larger local decision model (the candidate is
  `pplx-decider-flash-v1.2`, GGUF, via llama.cpp or vLLM) pass the same
  discrimination bar — and does Jev, on the same control — so the comparison is
  paired?
- Q-060: Does a short-level or yes/no-per-level rewording rescue the `fit`
  Score on small decision models?

## 8. Reproduction

See `PROTOCOL.md` §Procedure. The Decisions server must be up on
`127.0.0.1:5107` with `d3-lite` loadable (`POST /v1/load`). The states file
holds the reader's profile text and is kept outside the repository.
