# Research Decisions

ADR-style, dated, append-only. Reviewers ask "why did you use X?" — this is where
the honest answer already lives. Template: [`templates/DECISION.md`](templates/DECISION.md).

A superseded decision gets a new entry naming the one it replaces. Nothing here
is edited after the fact.

---

## D-001 — Evaluate on LongEval-Sci rather than a static scholarly collection

**Date:** 2026-08-04
**Context:** The ranking stack had no external measurement of any kind. The
production corpus grows daily and nobody had checked whether relevance degrades
as it does — the question most specific to this system.
**Options:**
- A static scholarly IR collection (TREC-COVID, SciFact, SciDocs via BEIR).
  Well-understood, widely comparable, but says nothing about persistence.
- LongEval-Sci (CLEF). Temporal snapshots of CORE open-access publications with
  per-snapshot judgments, openly downloadable, ships published BM25 and
  Qwen3-Embedding-4B baselines.
- Build an internal collection from the production corpus. Directly on-task, but
  requires annotators and produces nothing anyone else can check.

**Decision:** LongEval-Sci, with the internal collection deferred until
judgments exist (see `OPEN_QUESTIONS.md` W5).
**Consequences:** Persistence becomes measurable and the baselines come free.
The cost is that LongEval evaluates *query → documents* while Mycelium does
*declared-interest profile → feed*; the granularity mismatch between a
three-word interest and a 200-word abstract is not tested. This limitation must
be stated in any paper, not buried.
**Revisit when:** internal graded judgments exist, or LongEval's task shape
changes.

---

## D-002 — Report the qrels variant next to every number

**Date:** 2026-08-04
**Context:** LongEval-Sci ships click-model-derived pseudo-relevance judgments
(`dctr`, 8,772 for the training snapshot) and a smaller `raw` click set. Neither
is TREC-grade human assessment.
**Options:** report a single headline number; report the qrels variant only in
the methods section; carry the variant on every row.
**Decision:** carry it on every row, in the result JSON, in the generated
leaderboard, and in the manifest.
**Consequences:** Tables are wider. In exchange, no number can be quoted out of
its evidentiary context, and confidence is always sized to the judgments. This
is the mechanism that stops a pseudo-relevance number being cited later as if it
were human-assessed.
**Revisit when:** human-assessed judgments become available for any snapshot.

---

## D-003 — `pooled` and `full` corpus scopes are never compared

**Date:** 2026-08-05
**Context:** Scoring five arms against the full 869,902-document snapshot costs
hours of CPU embedding. A pooled evaluation — the union of judged documents with
a deep corpus-wide BM25 pool — is the standard reduction.
**Options:** full-corpus only (correct, slow); pooled only (fast, a re-ranking
evaluation); both, clearly labeled.
**Decision:** both, with `corpus_scope` recorded on every run and an explicit
prohibition on cross-scope comparison printed inside the generated leaderboard.
**Consequences:** Reordering metrics (nDCG@10) stay broadly comparable across
scopes; recall metrics do not and must never be read across the boundary. The
risk is that a reader lifts a pooled R@100 into a full-corpus claim, which is
why the warning lives inside the generated table rather than beside it.
**Revisit when:** full-corpus runs become cheap enough that pooled runs add
nothing.

---

## D-004 — nDCG@10 is the primary metric; R@100 is the primary *recall* metric

**Date:** 2026-08-05
**Context:** The product surfaces a short daily feed, so top-of-ranking quality
is what a user experiences. But the sharpest structural criticism of the stack
(C-008) is a *recall* failure, invisible to any top-10 measure.
**Options:** nDCG@10 alone; MAP alone; nDCG@10 primary with R@100 reported
alongside on every row.
**Decision:** nDCG@10 primary, R@100 always reported, and both plotted.
**Consequences:** A single headline metric would have hidden the dense-pool
recall gap entirely — the fusion arms look merely mediocre on nDCG@10 and are
severely handicapped on R@100. Reporting both is what turned an architectural
criticism into a measured number.
**Revisit when:** the feed length becomes variable in production, at which point
the @10 cutoff stops matching what users see.

---

## D-005 — The evaluation harness calls production code, never a copy of it

**Date:** 2026-08-04
**Context:** An evaluation harness that reimplements ranking measures the
harness, not the system.
**Options:** reimplement the ranking stack inside `eval/` against a spec; import
the production modules directly; run the deployed service over HTTP.
**Decision:** import directly. `eval/harness/arms.py` contains no ranking logic;
it imports `apps.content.{lexical,fusion,ranking}` and `pipeline._build_pool`.
The seam is `apps.content.protocols.VectorIndex` — production passes
`PgVectorIndex`, the harness passes `NumpyIndex`.
**Consequences:** Every ranking change is measured by the next run with no edit
to `eval/`. This is only sound because production has no ANN index — every
pgvector query is an exact sequential scan — so the in-memory index computes an
identical ranking, not an approximation. **If an ANN index is ever added to
production, this decision breaks and must be revisited.**
**Revisit when:** an approximate index (HNSW/IVFFlat) is enabled in production.

---

## D-006 — The research record is `docs/research/`, and it is enforced

**Date:** 2026-08-06
**Context:** The first real evaluation produced 27 runs and a genuine negative
result. Those numbers lived in one narrative markdown file, and the claims they
bear on lived in a different 128 KB audit document. Neither was machine-checkable
and neither would survive six months of drift.
**Options:** keep the narrative docs and add discipline; adopt an
experiment-tracking SaaS (MLflow, W&B); a git-tracked structured record with a
validator in CI.
**Decision:** the git-tracked record, with a schema-validated manifest per
experiment and CI enforcement. A tracker may be added later for capture, but it
must export a static snapshot into the experiment folder — external dashboards
die, repositories persist.
**Consequences:** Recording an experiment costs one command and a filled
template. Numbers now have exactly one home, and a claim with no experiment ID is
visibly unsupported rather than quietly assumed. The cost is a CI job that will
block pull requests when the record goes stale, which is the point.
**Revisit when:** the record exceeds what a validator can meaningfully check, or
a tracker becomes the capture layer.
