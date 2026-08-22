# EXP-2026-08-009 — Issues

## 1. The protocol was genuinely pre-registered

Unlike `EXP-2026-08-008`, `PROTOCOL.md` here was written before any arm on
`sci-2025-01` ran, and before the `xenc over bm25` arm existed on any snapshot.
Both hypotheses — the primary (the cross-encoder's advantage survives a paired
interval) and the secondary (the *fusion-based* variant will not replicate,
because the dense channel is much weaker on this snapshot) — were recorded in
advance, along with the falsifier and a decision rule.

The primary hypothesis was **falsified**. Recording that it was pre-registered is
the point: this is the first result in this record where a claim the project
wanted to be true was tested at adequate power and did not survive.

## 2. Two confounds separate the snapshots, and neither can be removed here

`sci-2026-train` and `sci-2025-01` differ in **two** ways at once, so a difference
between them cannot be attributed to either alone:

- **Judgment provenance.** 2026 uses `dctr` — click-model–derived pseudo-relevance.
  2025-01 uses the released CLEF-2025 `test` qrels. A cross-encoder trained on
  MS MARCO (itself click-derived) may plausibly agree more with click-derived
  judgments than with assessed ones, which would produce exactly the pattern
  observed without any property of the snapshot being involved.
- **Query style.** The 2025-01 topics are markedly shorter — many are one or two
  words (`operation`, `merleau-ponty`, `european crania`) — where 2026 topics run
  longer (`utilizing llm to identify entities in natural language text`). A
  cross-encoder is trained on natural-language questions and has little to read in
  a one-word query, while BM25's rare-term exact match is at its strongest there.

The query-length stratification in `tables/paired.md` was added to test the second
mechanism. On 2026 it is **not** conclusive — the buckets are small (5 queries at
one word) and the pattern is not monotonic. It should be read as a diagnostic that
did not resolve, not as support for the explanation.

## 3. Scope of what was actually run on `sci-2025-01`

Only the arms needing no corpus embedding were run: `bm25_only` and
`xenc_rerank` over the BM25 base. The **fusion-based** arms on this snapshot were
not run, because they require a one-time encode of the 261,294-document pooled
subset (~2 h on this host, no GPU).

That matters for how C-013 can be rescoped. C-013 as written is about the
cross-encoder *over the fusion ranking* beating BM25. That exact contrast is
measured on 2026 (not significant) but **not** on 2025-01. What 2025-01 establishes
is the more basic fact that the cross-encoder degrades the strongest first stage
available there.

## 4. A run was interrupted and re-launched

The `xenc over bm25 d100` arm on `sci-2025-01` was cut off mid-run by a session
boundary and restarted from scratch. No partial result was recorded and nothing
was salvaged from the interrupted attempt, so no result here is built on a partial
run. The `d50` arm on the same snapshot had already completed and its result file
is the one used.

## 5. Working tree dirty

`code.dirty: true`. The harness changes this experiment needed — run files carrying
the config hash, `needs_vectors()` letting a rerank arm over a lexical base skip
the corpus encode, and the two `xenc_rerank_bm25base_*` configs — were uncommitted
while the first arms ran. `apps.content` is unchanged; this experiment adds no
production behaviour.

The config-hash change to run filenames has a knock-on worth stating: run files
written *before* that change do not carry a hash, so `code/paired.py` could not
find them. The affected 2026 arms (`bm25_only`, `fusion_union_pool`,
`xenc_rerank_d50`, `xenc_rerank_d100`) were re-run rather than matched by an older
pattern, and all four reproduced their recorded values exactly (0.3212, 0.3056,
0.3299, 0.3304).

## 6. What the intervals do and do not license

The bootstrap resamples **queries**, so an interval here answers "would this
difference survive a different sample of topics from this collection". It does not
address a different corpus, a different judgment set, or Mycelium's actual task.
`docs/evaluation.md`'s claims boundary applies unchanged, and `Q-001` is untouched.

The 2026 intervals are wide because n = 100 — every single contrast on that
snapshot spans zero, including ones with point estimates the previous experiment
reported as findings. That is itself the most useful output of this experiment and
should be read as a statement about the **design**, not only about the arms.
