# EXP-2026-08-012 — Issues

## 1. Pre-registration

`PROTOCOL.md` was written before any arm on `sci-2025-01` was scored — only the
frozen subset and the already-published `bm25_only` baseline existed. The
hypothesis, the secondary prediction (C-008's effect should be *larger* here
because the dense channel is weaker on this snapshot), the falsifier, and the
decision rule were all fixed in advance.

The secondary prediction is not a free hit: `EXP-2026-08-002` had already reported
the un-intervalled recall gap as 8.7% on 2026 against 75–80% on the 2025 pair, so
the *direction* was known. What was not known is whether it survives an interval.

## 2. Two things differ between the snapshots, not one

This is a replication across **snapshot and judgment provenance simultaneously**:

- `sci-2026-train` — 100 queries, `dctr` click-model–derived pseudo-relevance.
- `sci-2025-01` — 492 queries, released CLEF-2025 human assessments.

If the claims hold under both, that is *stronger* than either alone — agreement
across two judgment regimes is harder to get by accident than agreement within
one. But a **failure** to replicate is ambiguous between the two causes and must
be reported that way rather than attributed to the snapshot.

The precedent for taking this seriously is in the record: `EXP-2026-08-009` found
the cross-encoder null on 2026 and significantly harmful on 2025-01 — an effect
that flipped across exactly this pair.

## 3. Run offline and unattended, by design

The network was expected to drop for roughly twenty minutes mid-run. Rather than
supervise it, phases 2 and 3 were chained in `scripts/exp012_chain.sh` and made
network-independent:

- the corpus was already downloaded under `data/eval-cache/ir_datasets`;
- the fastembed model cache was **copied out of `/tmp`** (where it can be cleared
  by system tmpfiles cleanup) into `data/eval-cache/fastembed`, and pointed at via
  `FASTEMBED_CACHE_PATH`;
- `HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1` stop fastembed from contacting the
  hub to check for model updates;
- no LLM is called anywhere in this experiment.

Offline loading of the SPLADE model from the durable cache was **verified before**
the chain was launched, not assumed.

This changes no result — encoding is deterministic and the same model weights are
used either way — but it is why the run is trustworthy despite being unsupervised.

## 4. Encodes run one at a time

`EXP-2026-08-008` ISSUES §5 measured that two concurrent ONNX sessions on this
host are catastrophically slower than serial (a 4,096-document shard took 20
minutes against a 3-minute projection). The chain therefore waits for the dense
encode to finish before starting SPLADE, at the cost of wall-clock rather than
throughput.

## 5. Scope

`pooled` scope at depth 1000 on both snapshots — a **re-ranking** evaluation.
`R@100` is recall *within each snapshot's pooled subset* and supports a claim
about the relative ordering of pool constructions, never about a production
corpus.

And the boundary that governs everything in this programme: LongEval is
`query → documents`; Mycelium is `declared-interest profile → feed`. Two snapshots
of the wrong task are still the wrong task. `Q-001` remains the gate on any
production change, and this experiment does not move it.

## 6. C-018 is exploratory on both snapshots

C-018 was not pre-registered in `EXP-2026-08-011` — it came out of a contrast
included for context. It **is** pre-registered here, so a replication gives it a
proper footing that the original observation lacked. If it fails here, it should
be cut rather than carried.

## 7. Working tree dirty

`code.dirty: true`. Uncommitted while running: this experiment's folder and
`scripts/exp012_chain.sh`. `apps.content` is unchanged; no arm in this experiment
adds or alters production behaviour, and every arm is one already measured in
`EXP-2026-08-008`/`011` on the other snapshot.
