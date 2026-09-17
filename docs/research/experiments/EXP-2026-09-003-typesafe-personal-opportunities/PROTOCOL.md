# EXP-2026-09-003 — Protocol

**Written before any call was made.** The client (`apps/core/systemone.py`) and
the scripts under `code/` existed and had been dry-run against the database
(states built, nothing sent) when this was written; no TypeSafe call had been
made from this repository.

## Question

On one reader's current grant and conference slates, how far does a calibrated
decision model (TypeSafe Jev) agree with (a) the fused retrieval order that
decides the slate and (b) the verdict the prose model wrote for each item — and
what does one reader's worth of judgements cost and take?

## Hypothesis

Partly pre-registered, partly exploratory, and the split is stated here.

**Pre-registered `[PRE]`:**

1. **Verdict agreement.** The model's argmax fit level and the stored LLM
   verdict (read / skim / file / skip) agree exactly on **≥ 50 %** of pairs and
   within one step on **≥ 85 %**. Chance for four classes is 25 % exact.
   Falsifier: exact agreement ≤ 30 %. That would mean at least one of the two
   judges is close to noise on this task, and the record would not know which.
2. **Order agreement is weak and positive.** Kendall tau between the fused
   position and the `worth` probability, per theme, averages between **0.1 and
   0.5**. The fused order is retrieval, not judgement, and the record has never
   claimed it orders by worth (C-004 unsupported), so strong agreement would be
   the surprise. No falsifier; the range is a prior, and either tail is a finding.
3. **Determinism.** Three repeated calls on five identical pairs differ in
   `worth` by **≤ 0.01** absolute. Falsifier: any difference > 0.05, in which
   case every number here is reported as mean ± std over three runs and the
   manifest says so.

**Exploratory (no prior):** the grant eligibility probability, the conference
venue-fit probability, the confidence distribution, and how many distinct
`fit` scores appear inside a ten-item theme (C-016's failure mode was 1.99).

## Setup

- Model: `jev-1.13.0`, pinned; the `jev-latest` alias is refused by the script.
- One call per (theme, item) pair. Every question for the pair rides in that
  one call, which the API evaluates in parallel against the same state.
- State is a JSON object: the researcher block (the production
  `opportunity_llm._profile_text` output — career stage, institution,
  statement, focus, keywords, skills), the strand block (label and its declared
  interests), and the opportunity block (the production
  `opportunity_llm._candidate_brief` text; for grants also the eligibility
  text and applicant types). The prose model sees the same profile text and the
  same brief, which is what makes the verdict comparison like for like.
- Questions: `fit`, a four-level Score whose level texts are the four verdict
  blurbs from `apps/content/verdicts.py`; `worth`, a Noul; and one area
  question — `eligible` for grants, `venue_fit` for conferences.
- Concurrency 8; the documented rate limit is 1,200 requests per minute.
- Failures keep the pair with an error string; nothing is retried.

## Data

The reader's own account on the development deployment's compose Postgres, as
of the run date. Every `RelevanceScore` row for that user whose
`signals.cluster_slates` is non-empty, for `content.type` in {`grant`,
`conference`} — the slate the daily run produced. Three declared themes.
Expected size from the dry run: about 59 pairs (27 grant, 22 conference rows;
some items sit in two themes).

**There are no relevance judgements.** Both comparators — the fused order and
the stored LLM verdict — are system outputs. The reader's own reading of the
tables is the next step, and it is a preference, not a label (Q-029's rule).

**What leaves the host.** The researcher block is the reader's own profile
text, sent at their explicit instruction for this experiment on their own
account. It is *not* written into this folder; `data/pairs.json` records its
SHA-256 and length only. Opportunity text is public. Nothing from any other
account is sent.

## Metrics

- `verdict_exact` — share of pairs where argmax(`fit`) equals the stored
  verdict. **Primary.**
- `verdict_within_one` — share within one step on skip < file < skim < read.
- `tau_mean` — Kendall tau-a between fused rank (ascending) and `worth`
  (descending), per theme, averaged over themes; also reported per theme.
- `distinct_fit_per_theme` — distinct `fit` scores (2 dp) per theme, mean.
- `confidence_mean` — mean `fit` confidence.
- `determinism_max_abs_diff` — over the repeated pairs.
- `input_tokens_total`, `output_tokens_total`, `cost_usd` at the list price
  on the run date ($0.042 per million input tokens, output free, read
  2026-09-17), `latency_ms_median`, `latency_ms_p95`, `wall_seconds`.

## Baselines

The two comparators above. There is no third judge.

## Procedure

```bash
# 1. Key in the repository root .env as TYPESAFE_API_KEY.
# 2. Dry run: build every state, send nothing, write data/dry_run.json
uv run --project eval python docs/research/experiments/EXP-2026-09-003-typesafe-personal-opportunities/code/run.py --user brendondgr --dry-run
# 3. The run: writes data/pairs.json
uv run --project eval python docs/research/experiments/EXP-2026-09-003-typesafe-personal-opportunities/code/run.py --user brendondgr
# 4. Analysis: writes data/metrics.{json,csv} and tables/*.md from pairs.json only
uv run --project eval python docs/research/experiments/EXP-2026-09-003-typesafe-personal-opportunities/code/analyse.py
```

## What would falsify this

Hypothesis 1: exact verdict agreement at or below 30 %. Hypothesis 3: any
repeated pair moving by more than 0.05. Hypothesis 2 has no falsifier and says
so. A run that fails on more than 10 % of pairs is recorded as failed, not
analysed.
