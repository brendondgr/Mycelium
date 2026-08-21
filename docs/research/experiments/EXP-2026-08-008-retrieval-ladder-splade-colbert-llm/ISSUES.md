# EXP-2026-08-008 — Issues

Everything that a reader should know before trusting a number here, including the
things that make it weaker. Recorded as they happened, not reconstructed.

## 1. The protocol was written part-way through the run

`PROTOCOL.md` was not written before the first arm ran. At the moment it was
written, the baseline reproduction, the three LLM arms, and the cross-encoder
arms at depths 50 and 100 had already been scored. The SPLADE arms, every ColBERT
arm, the cascade, the deep-pool arms, and the cross-encoder at depth 250 had not.

Predictions in `PROTOCOL.md` are individually labelled `[PRE]` or `[POST]`
accordingly. Only the `[PRE]` ones are pre-registrations; the `[POST]` ones are
descriptions of results already seen and carry no evidential weight as
predictions.

**Why it matters most for SPLADE:** the SPLADE hypothesis and its falsifier were
written down before `splade_only` was scored, and the falsifier fired. That one is
a genuine pre-registration. The cross-encoder's "expected to be strongest" is not.

## 2. The working tree was dirty for every run

`code.dirty: true`. The ladder itself — `eval/harness/{ladder,neural,llm_rerank,
subset}.py`, `eval/{freeze_subset,encode_ladder}.py`, the new configs, and the
`run.py` changes that pass `params`/`collection` through and honour a frozen
subset — was uncommitted while it ran. The production code under test
(`apps.content`) was **not** modified: this experiment changes no ranking
behaviour that ships, and the baseline arms it re-scored reproduced the committed
leaderboard exactly, which is the evidence for that claim (see §3).

## 3. Baseline reproduction, and what it does and does not prove

All five baseline arms reproduced their recorded values on the frozen subset to
four decimal places:

| Arm | nDCG@10 recorded | nDCG@10 here | R@100 recorded | R@100 here |
|---|---:|---:|---:|---:|
| `bm25_only` | 0.3212 | 0.3212 | 0.6903 | 0.6903 |
| `dense_only` | 0.2401 | 0.2401 | 0.6120 | 0.6120 |
| `fusion_dense_pool` | 0.2937 | 0.2937 | 0.5988 | 0.5988 |
| `fusion_union_pool` | 0.3056 | 0.3056 | 0.6511 | 0.6511 |
| `fusion_full` | 0.2963 | 0.2963 | 0.5988 | 0.5988 |

This proves the frozen subset is the same 84,489 documents the leaderboard was
built on, and that the row-sliced embedding matrix is aligned to them. It does
**not** prove anything about the ladder arms, which had no prior value to
reproduce.

## 4. The rerank-depth sweep on the shallow base is vacuous

`xenc_rerank` at depths 100 and 250 returned byte-identical metrics. The cause is
not a bug in the arm: the `fusion_union_pool` base at `pool_per_interest = 100`
emits only **59–97 candidates per query** (median 74, max 97, measured from the
run file). At depth 100 the arm already reranks everything there is, so depth 250
is the same operation.

Two consequences:

1. Only the depth 50 → 100 contrast is real on that base. The `[PRE]` depth
   hypothesis cannot be tested against it, and the deep-pool arms
   (`pool_per_interest = 500`) were added mid-run for that reason. Those arms were
   **not** in the original plan and are exploratory.
2. The candidate count is itself a finding about production, not about the
   harness. `fuse_interest`'s `DEFAULT_INTEREST_FLOOR = 0.15`, applied after
   min-max normalization, discards more than half of a 200-document pool. It also
   places a hard ceiling on this base's recall — no `R@100` above roughly 0.75 is
   reachable when only ~74 documents are ever emitted.

## 5. Two ONNX sessions oversubscribed the host

The first attempt ran the SPLADE and ColBERT encodes concurrently. A 4,096-document
shard took ~20 minutes against a benchmarked projection of ~3. Both were killed
and re-run one at a time with `fastembed`'s process sharding (`parallel=8`), after
which SPLADE sustained ~30 docs/s and finished 84,489 documents in 3,451 s.

No result is affected — encoding is deterministic and the shards written under
contention were reused — but the reconnaissance throughput figures in
`harness/neural.py`'s docstring are single-model figures and should be read that
way.

## 6. The LLM arms measure a counterfactual, not production

`apps.content.suggest` does **not** reorder; it annotates a fused ordering. Every
number from `llm_rerank`, `llm_rerank_reversed`, and `llm_rubric` describes what
would happen if the model were allowed to rank, which it is not. They are
evidence about a design option, not about shipped behaviour.

Related: `LLM_TEMPERATURE` is pinned to 0 for these arms, whereas production
defaults to 0.2 (audit item W1, still open). So even the counterfactual is
measured under a setting production does not use.

Five of 100 listwise verdicts (`llm_rerank`) and three of 100
(`llm_rerank_reversed`) were unparseable; those queries kept their base ordering,
which biases both arms *toward* the base. The rubric arm parsed 2,000 of 2,000.

## 7. Statistical power

n = 100 queries, single run, no paired confidence intervals computed in this
experiment. `Q-011` and `Q-013` both exist because this record has twice failed to
separate "no effect" from "an effect too small to resolve". Differences below
roughly 0.01 nDCG@10 here should be treated as unresolved. The differences this
experiment actually leans on — SPLADE's deficit, the cross-encoder's gain, and
the listwise/reversed gap — are all several times that, but the marginal ones
(for example `fusion_bm25_dense_splade` against `bm25_only`) are not.

## 8. Judgments

`dctr`: click-model–derived pseudo-relevance, not human assessment. This is a
property of the collection and applies to every number in the record.

## 9. Scope

`pooled`, 84,489 documents — a **re-ranking** evaluation. `R@100` is reported as a
within-scope diagnostic only and cannot be quoted as a recall claim about the
production corpus. And the collection evaluates `query → documents` while Mycelium
does `declared-interest profile → feed`; `docs/evaluation.md`'s claims boundary
applies to everything here without modification.
