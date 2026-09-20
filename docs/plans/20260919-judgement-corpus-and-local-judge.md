# Judgement Corpus and a Local Slate Judge — Implementation Plan

**Status:** proposed, nothing built.
**Correlation ID:** `20260919-judgement-corpus`
**Evidence so far:** `EXP-2026-09-003` (one reader's slates), `EXP-2026-09-004`
(LongEval, yes/no framing beats the rubric). Nothing here changes a claim in
`docs/research/CLAIMS.md` until an experiment below runs.

## Objective

Turn the nightly TypeSafe rerank into a training corpus, then find out whether a
small self-hosted model fine-tuned on that corpus reorders a reader's slates the
way TypeSafe does. Concretely:

1. Every judgement the nightly run asks of TypeSafe is written to a file as one
   record: the exact input the judge saw, the exact answer it gave. A copy of
   those files is the dataset. Nothing about the reorder changes.
2. An exporter turns the records into the prompt a local model would be given
   and the answer it should produce, so the pair *input → expected output* can
   be read by a person and consumed by a trainer.
3. A local judge that answers the same question from a model's own logprobs,
   first zero-shot, then fine-tuned on the corpus, measured for agreement with
   the stored judgements on held-out readers before it is allowed to reorder
   anything.

The method is the one in the shared write-up on distilling DeepSeek into a 4B
decision model: thinking off, logprobs over constrained options read as a
probability, soft labels from the teacher, a student that only does the
judgement. Our teacher is the model already in production and our synthetic
data is real candidates paired with synthetic strands.

## What the corpus is, and why it is state rather than a prompt

Each record stores the **structured state** `build_state()` already assembles
in `apps/content/typesafe_rerank.py` (researcher text, strand label and
interests, one candidate block), the **question texts** as asked, and the
**answers** as returned. It does not store a rendered prompt. TypeSafe consumes
state and questions natively; a local model needs a chat template around them;
the rendering is a function of (state, questions, template version) and belongs
to the exporter, so the same record can be rendered for Qwen today and for
something else next year. The exporter emits the rendered prompt alongside the
state, so the human-readable "what we send, what should come back" file exists
too.

One line of JSON per call, newline-delimited, one file per run date:

```
data/judgements/2026-09-20.jsonl
```

```json
{
  "id": "1f3a…",                        // typesafe_rerank.fingerprint(model, state)
  "recorded_at": "2026-09-20T03:14:07Z",
  "source": "nightly",                  // nightly | synthetic | replay
  "judge": {"provider": "typesafe", "model": "jev-1.13.0",
            "question_version": "2026-09-17.1"},
  "content_type": "grant",
  "target": {"kind": "user", "hash": "9c0e…", "entitled": true},
  "content_id": "…", "cluster_id": "…",
  "state": {"researcher": "…", "strand": {"label": "…", "interests": ["…"]},
            "opportunity": {"brief": "…", "eligibility": "…"}},
  "questions": {"worth": {"type": "noul", "instructions": "…", "true": "…", "false": "…"},
                "fit":   {"type": "score", "instructions": "…", "levels": ["…", "…", "…", "…"]},
                "eligible": {"type": "noul", "…": "…"}},
  "answers": {"worth": {"noul": 0.73},
              "fit": {"score": 1.92, "confidence": 0.51, "probabilities": {"0": 0.1, "1": 0.2, "2": 0.5, "3": 0.2}},
              "eligible": {"noul": 0.88}},
  "usage": {"input_tokens": 1140, "output_tokens": 0},
  "latency_ms": 212
}
```

`id` is the fingerprint the reorder already computes, so a record and the
judgement stored on the row at `signals["typesafe"][cluster_id]` name each
other. Reused judgements are not re-logged: a fingerprint appears once.
`target.hash` is a salted hash of the target id; no name, email, slug or
institution string leaves the state text itself, and the state text is the
profile text the pipeline already sends off-host.

## Assumptions and open questions

- **Teacher.** TypeSafe (`jev-1.13.0`, pinned) is the teacher because parity
  with it is the target and its answers are already paid for. Read TypeSafe's
  terms on training against its outputs before Phase 5; if they forbid it, the
  corpus is still the evaluation set and the teacher for training becomes the
  relay's model through the same logger (`source: "replay"`).
- **Personal data.** The state carries a reader's profile text. The files live
  under `data/`, are git-ignored, are pruned after `JUDGEMENT_LOG_RETENTION_DAYS`,
  and copying them to a training machine is a transfer of user profile text
  that the operator decides on, not the code. The synthetic bulk in Phase 4 is
  what lets the training set be large without that transfer; real readers'
  records are for evaluation first.
- **Corpus size from nightly alone is small.** Reuse by fingerprint means only
  new (theme, item) pairs are asked each night: on the order of tens per reader,
  a few thousand a month for the current user base. That is an evaluation set,
  not a training set, which is why Phase 4 exists.
- **Student size.** The task is one binary question over ~1,100 tokens. The
  plan tries Qwen3-1.7B (LoRA, logprob head) first and a ~150M encoder with a
  regression head second; 4B only if both miss the bar. The 16 GB Quadro on the
  dev host takes either; a full 4B fine-tune needs the unified-memory box.
- **Where the judge runs.** Not on the shared relay as a second heavy model
  (it returns 502s under load; see the concurrency budget). `JUDGE_BASE_URL` is
  a separate setting so it can point at the dev host's card or a CPU server.

## Phases

### Phase 1 — Write the record (observe only)

- New module `apps/content/judgement_log.py`: `write(record: Mapping) -> None`
  appending one JSON line to `JUDGEMENT_LOG_DIR / <run-date>.jsonl`, with a
  process-level file lock. A write failure logs a warning and returns; it can
  never change a reorder, the same rule `llm_usage.record` follows.
- `apps/core/systemone.py`: add `question_to_dict(question)` beside
  `answer_to_dict`, so the SDK's `Noul`/`Score`/`Choice` objects flatten to the
  `questions` block above without the exporter importing the SDK.
- `apps/content/typesafe_rerank.py`: in `reorder_id_groups`'s `one(job)`, after
  a successful `client.ask`, call `judgement_log.write(...)` with the state,
  fingerprint, questions, `result.answers_as_dicts()`, usage and latency.
  Reused judgements are skipped. `emit` gains one line: `judgements logged: N`.
- Settings: `JUDGEMENT_LOG_ENABLED` (default on), `JUDGEMENT_LOG_DIR` (default
  `data/judgements`, next to `RUN_ANALYTICS_*`), `JUDGEMENT_LOG_RETENTION_DAYS`
  (default 365), `JUDGEMENT_LOG_SALT`. Prune inside the existing analytics
  sweep rather than a new nightly stage.
- Docs: `architecture.md` config table and the "what leaves the host" row;
  `repo-map.md` row for the module; `.env.example` block.

**Validation.** `uv run --project web/backend pytest apps/content -k judgement`
with: logging on and off produces byte-identical reorder output; a record
validates against `scripts/judgements/record.schema.json`; a raising writer
does not fail the reorder; a record never contains the target's name or email.
After one nightly run: line count equals the run log's `asked` count.

### Phase 2 — Export: input → expected output

- Management command `export_judgements --since --until --out DIR
  [--template qwen3-noul] [--split by-reader|by-date]`.
  - Dedupes by `id`, drops `source: synthetic` unless `--include-synthetic`.
  - Splits so no `target.hash` appears in more than one of train/val/test
    (`by-reader`, the default), or by run date for a temporal check.
  - Renders each record with the named template into
    `{"id", "messages": [system, user], "target": {"yes": p, "no": 1-p},
    "hard": "yes"|"no", "state", "answers"}`. The template is a versioned
    function in `apps/content/judge_prompts.py`, the same one the local judge
    uses at inference, so training and serving cannot drift.
  - Writes `train.jsonl`, `val.jsonl`, `test.jsonl`, and `README.md` with
    counts per content type, per reader hash, per date, and the template
    version.
- Also renders the `fit` Score as a four-option question with the level texts
  and the stored distribution as the soft target, so a student can learn both
  from the same record. `worth` is what decides order; `fit` is a second head.

**Validation.** Round-trip test: render → parse back the state; a fixture
corpus of 30 records exports with the expected split sizes and no reader
overlap. `uv run --project web/backend pytest apps/content -k export_judgements`.

### Phase 3 — The local judge behind the same switch

- `apps/core/judge.py`: a `Judge` protocol, `ask(state, questions) -> {qid:
  answer dict}` returning the same dict shapes `answer_to_dict` produces.
  `TypeSafeJudge` wraps `SystemOneClient`. `LogprobJudge` wraps `LLMClient`
  with `max_tokens=1`, `logprobs=True`, `top_logprobs=10`, thinking off through
  `chat_template_kwargs`, and returns `p(yes) = softmax(lp_yes, lp_no)` for a
  noul and the probability-weighted level for a score over the option tokens.
  Each question is one request against the same state prefix so vLLM's prefix
  cache does the sharing the write-up describes.
- `typesafe_rerank.py` takes its judge from a factory keyed on `RERANK_METHOD`:
  `typesafe` (unchanged), `local` (unchanged), new `local_judge`. The
  fingerprint already includes the model name, so switching invalidates stored
  judgements correctly and reuse stays safe. The entitlement gate stays
  `Feature.TYPESAFE_RERANK` until the product decision in Phase 6.
- Settings: `JUDGE_BASE_URL`, `JUDGE_MODEL`, `JUDGE_API_KEY`, `JUDGE_TIMEOUT`,
  `JUDGE_CONCURRENCY`. Management command `judge_check` mirroring
  `typesafe_check` (one fixed sentence, prints p(yes) and latency).
- The logger from Phase 1 records `local_judge` calls too, under
  `judge.provider: "local"`, so disagreements are in the same files.
- Management command `judge_replay --corpus DIR --judge local|typesafe --out
  FILE`: answers every record's state offline with the named judge and writes
  the answers next to the originals. This is the instrument for every
  experiment below and it never touches the database.

**Validation.** `pytest apps/core -k judge` with a fake completions object that
returns logprobs; `judge_check` against a running vLLM. `uv run --project
web/backend pytest apps/content -k typesafe_rerank` unchanged.

### Phase 4 — Grow the corpus synthetically

- `scripts/judgements/synthesize.py`: builds states from **real** candidates
  (a sample of the content pool per type, the same `candidate_block`) paired
  with **synthetic** strands drawn from the topic list in
  `web/backend/sandbox/ambient/world.py` and the eval profile generator
  (`eval/harness/profiles.py`), plus researcher texts rendered by the same
  `_profile_text` the pipeline uses. Labels them through `TypeSafeJudge` with
  `source: "synthetic"`, bounded by `--max-pairs` and `--max-usd` at list price.
- Target scale for the first round: 50,000 pairs, about 55 M input tokens,
  about $2.30 at the price recorded in `EXP-2026-09-004`. Under the relay
  budget rules this runs against TypeSafe, not the relay.
- Recorded as an experiment folder because it spends money and produces a
  dataset card (`make new-experiment SLUG=judgement-corpus-synthetic`).

**Validation.** The synthetic file passes the same schema; the dataset card
lists the sampling and the cost from the API's usage block.

### Phase 5 — The experiments that decide

Each is scaffolded with `make new-experiment`, has its `PROTOCOL.md` written
before a call is made, and stays under an hour and 32 concurrent requests.

- **EXP-A, zero-shot agreement.** `judge_replay` with `LogprobJudge` on
  Qwen3-1.7B and Qwen3-4B over every nightly record to date. Per theme window:
  Kendall tau against TypeSafe `worth`, top-10 Jaccard of the resulting order,
  mean absolute error of the probability, a reliability table, repeat spread on
  20 pairs × 3, latency. Pre-registered bar: mean top-10 Jaccard ≥ 0.80 (the
  bar the two TypeSafe framings met against each other) and tau ≥ 0.6;
  falsifier: Jaccard < 0.6. Answers "how far is a stock model" before any GPU
  hour is spent.
- **EXP-B, the fine-tuned student.** Train on the Phase 2 `train.jsonl` plus
  the synthetic file; evaluate on `test.jsonl` (held-out readers) and on a
  held-out date range. Loss: temperature-scaled KL against the `{yes, no}` soft
  target, cross-entropy on the hard label as the ablation. Two students:
  Qwen3-1.7B with LoRA, and a ModernBERT-base regression head. Same metrics
  and bars as EXP-A, plus the LongEval arm `local_noul` over BM25's top 20 on
  the 2,000 pairs `EXP-2026-09-004` used, paired against the stored
  `typesafe_noul` answers. Training code lives in `eval/train/` under an
  optional `train` dependency group of the eval project so no new top-level
  area is added.
- **EXP-C, shadow week.** With `RERANK_METHOD=typesafe` still deciding, the
  local judge answers the same pairs nightly through the logger. One week of
  disagreement rates per reader and content type, read from the files alone.

**Validation.** `make validate-research` before any number is quoted.

### Phase 6 — Cut over

Only after EXP-B meets its bar on held-out readers and EXP-C shows the
disagreement rate holding: flip `RERANK_METHOD=local_judge`, keep TypeSafe
configured for a fortnight as the fallback on a failed call, then remove the
key. Two product decisions land here and go in the canonical docs, not the
code: whether the judge stays paid-tier now that nothing leaves the host and
the marginal call is free, and whether the window widens past 20. The plan is
deleted and the outcome written to `changelog.md`, `architecture.md`,
`repo-map.md`, and `CLAIMS.md`.

## Interfaces and docs that change

| Surface | Change |
|---|---|
| `apps/content/judgement_log.py`, `apps/content/judge_prompts.py`, `apps/core/judge.py` | New modules (Phases 1–3) |
| `apps/content/typesafe_rerank.py` | Logs each fresh judgement; takes its judge from the `RERANK_METHOD` factory |
| `apps/core/systemone.py` | `question_to_dict` |
| Management commands | `export_judgements`, `judge_check`, `judge_replay` |
| Settings / `.env.example` | `JUDGEMENT_LOG_*`, `JUDGE_*`, `RERANK_METHOD=local_judge` |
| `eval/harness/` | `local_noul` arm; `eval/train/` with the `train` dependency group |
| `docs/architecture.md`, `docs/repo-map.md`, `docs/evaluation.md` | Config rows, module rows, the new arm |
| API contract | Unchanged. The feed serializers read `signals["typesafe"]` as before; the key name stays until Phase 6 |

## Acceptance criteria

- After one nightly run the day's file exists, validates line by line, and its
  line count equals the run log's `asked` count; the reorder output is
  identical to a run with logging off.
- `export_judgements` produces a folder a person can open and read as
  "prompt → expected answer", with no reader in two splits.
- `judge_check` answers from a local model in under a second per question on
  the dev host's card.
- EXP-A and EXP-B are recorded with pre-registered bars; whichever way they
  land, `CLAIMS.md` says what the local judge can and cannot claim.
- Nothing shipped to readers changes before Phase 6.

## Explicit exclusions

- No change to what is ranked, to the pool, to the 20-item window, or to the
  prose write-ups. This is the judge only.
- No human relevance labels; W5 remains the separate, still-blocking effort.
  Agreement with TypeSafe is the bar here, and it is a parity bar, not a
  quality claim.
- No new infrastructure: no object store for the files, no Neo4j, no second
  model on the shared relay.
- No Free-tier change, no widening of the window, until Phase 6's recorded
  decision.
