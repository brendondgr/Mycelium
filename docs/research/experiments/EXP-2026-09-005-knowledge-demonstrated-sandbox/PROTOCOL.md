# EXP-2026-09-005 — Protocol

Written 2026-09-18, before any scored run. An 8-person smoke run was made first
to prove the harness end to end (recorded in ISSUES.md 1); its numbers are not
results and are not used below.

## Question

When people's own papers are read by plan CN-02's extractor and linked into the
knowledge graph, does each paper's real method become a demonstrated concept
that meets the same method in the person's declared profile — without merging
different methods, leaking anything private, or re-billing the model?

## Hypothesis

- **H1 (invariants).** Every invariant counter is zero in every arm:
  conversational edges, private concepts reached from a paper, thin works with
  edges, roll-up evidence naming someone else's work, neutral phrases on the
  deny-list, model calls and works read on a second pass, and writes by a
  second declared projection.
- **H2 (prompt).** A prompt revision that asks for each technique's standard
  name without qualifiers ("gradient boosting", not "specialized implementation
  of gradient boosting") and forbids generic descriptions as methods, together
  with a validator that refuses a method term made only of generic words
  ("high-dimensional structural representations") (arm B, prompt `w2`; added to
  this protocol while arm A was running and before any of its numbers were
  read), raises `q2_declared_and_demonstrated_recall` over the shipped
  prompt (arm A, `w1`) by at least 0.05 absolute and lowers
  `method_split_total`.
- **H3 (threshold).** At the shipped merge threshold, 0.92, no concept is
  reached by two different planted methods (`wrong_merge_total` = 0), including
  the planted near misses (Kalman filter vs particle filter, random forest vs
  gradient boosting). Lowering the threshold reduces splits; where the first
  wrong merge appears is exploratory.
- **H4 (field ruler).** `field_ruler_accuracy` ≥ 0.9.
- **H5 (Q1 at scale).** `q1_recall` ≥ 0.9 and `q1_precision` ≥ 0.8.

## Setup

- System: `apps/knowledge` at the commit in `manifest.yaml` — the linker
  (`KNOWLEDGE_MERGE_COSINE` 0.92), the declared projection, the work-facet
  extractor (`works.py`), demonstrated edges and roll-up (`demonstrated.py`),
  the pipeline (`papers.py`), and the read door (`read.py`: Q1, Q2).
- Harness: `web/backend/sandbox/collab` (world, corpus, seed, run, score,
  sweep), on a separate database, `mycelium_sandbox`, with both knowledge hooks
  forced off.
- Model: the deployment's configured endpoint, `llm-tunnel:9090`, model
  `default-model` (relay upstream `gemma4-26B-mtp`), for both writing the fake
  abstracts and reading them. Embedder: `BAAI/bge-small-en-v1.5` on CPU.
- Held fixed across arms: the world (seed 20260918, 240 people), the generated
  corpus (cached, read by both arms), the threshold (0.92) for arms A and B.

## Data

Entirely synthetic. `sandbox.collab.world.build(seed=20260918, people=240)`:
240 fictional researchers across 8 OpenAlex fields at 6 real university
domains, 16 methods (12 used in more than one field, each under two or three
names; two planted near-miss pairs), 3–6 papers each. Abstracts are written by
the same local model that later reads them, which is a circularity: an
extractor reading text its own model family wrote may find it easier than real
abstracts. **The judgments are planted ground truth, not human assessments.**
Abstracts that fail the generator's own check (never name their method, or
name another planted method) are excluded from the extraction metrics and
counted as `corpus_generator_slips`.

## Metrics

Primary: **`q2_declared_and_demonstrated_recall`** — of the (person, method)
pairs where a person declares a method and publishes with it, the share where
`read.backing` shows one concept both declared and demonstrated. It is the
user-visible question: does "your papers show this" meet "your profile says
this". The rest:

- `method_recall`: of non-thin clean papers, the share with at least one method
  term naming the planted method (by the method's signature fragments).
- `method_split_total`: summed over planted methods, distinct concepts the
  method's terms reached, minus one each. Lower is better.
- `wrong_merge_total`: concepts reached by terms naming two different planted
  methods. Must be zero.
- `method_term_contamination`: method terms naming a planted method other than
  the paper's own.
- `field_ruler_accuracy`: for each method's most-used concept, whether its
  OpenAlex field is the single field its papers came from, or blank when they
  came from several.
- `q2_declared_only_recall`, `q2_undeclared_method_shown_recall`: the planted
  declared-only interest shows as declared only; the planted undeclared method
  shows as demonstrated only.
- `q1_recall`, `q1_precision`: per project, the expected undeclared set is its
  problem, its data, and its uncovered need.
- Cost: model calls, mean seconds per call, wall clock per stage.

## Baselines

Arm A (the shipped prompt, `w1`) is the baseline for arm B. For H3, the
threshold sweep's other points are compared with 0.92.

## Procedure

Inside the backend container, from `/app/web/backend`:

```bash
# Arm A — the shipped prompt (works.PROMPT_VERSION "w1").
uv run --project . python -m sandbox.collab all --people 240 \
  --out /app/data/sandbox/exp005-arm-a.json
# Arm B — after the w2 prompt revision is committed.
uv run --project . python -m sandbox.collab all --people 240 \
  --out /app/data/sandbox/exp005-arm-b.json
# Threshold sweep on arm B's stored facets (no model calls).
uv run --project . python -m sandbox.collab sweep --people 240 \
  --out /app/data/sandbox/exp005-sweep.json
```

## What would falsify this

- H1: any invariant counter non-zero in any arm.
- H2: arm B's primary metric is less than 0.05 above arm A's, or its
  `method_split_total` is not lower.
- H3: `wrong_merge_total` > 0 at 0.92.
- H4: accuracy below 0.9. H5: recall below 0.9 or precision below 0.8.
