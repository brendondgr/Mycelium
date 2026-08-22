# EXP-2026-08-011 — Issues

## 1. Pre-registration

`PROTOCOL.md` was written before any interval here was computed. The hypothesis,
the falsifier, and the decision rule (interval excludes zero **and** the per-query
record favours the treatment) were all fixed in advance — deliberately the same
rule that disqualified the LLM arm in `EXP-2026-08-008` and the cross-encoder in
`EXP-2026-08-009`, so the surviving claims are not being graded on a curve.

## 2. One snapshot, and pseudo-relevance judgments

`sci-2026-train` only: 100 queries, click-model–derived `dctr` qrels. The
`sci-2025-01` fusion arms would need a ~2 h corpus encode of its 261,294-document
subset and were not run here or in `EXP-2026-08-009`.

So C-008 and C-014 are supported **on one snapshot with click-derived
judgments**. That is a real step up from a point estimate with no interval, and it
is short of settled — particularly given that `EXP-2026-08-009` found the
cross-encoder's sign *flipping* between these two snapshots. `Q-024` exists to
close this.

## 3. Pooled scope — the caveat that is easiest to lose

R@100 here is recall **within the 84,489-document pooled subset**, which is the
union of the judged set with a corpus-wide BM25 pool. It supports a claim about
the *relative ordering of pool constructions* and says nothing about recall on a
production corpus. `Q-001` is untouched by this experiment.

## 4. The unplanned finding was not pre-registered

C-018 — two-channel fusion is significantly worse than BM25 on recall (−0.0392,
14 wins to 32 losses) — came out of a contrast included for context, not out of a
stated hypothesis. It is recorded as a finding because the interval excludes zero
and the per-query record agrees, but it is exploratory and should be replicated
alongside `Q-024` rather than treated as confirmed.

## 5. Interval widths

The recall effects resolve because they are 3–6× the ±0.04 band that defeated
every nDCG@10 contrast — not because n = 100 is adequate. C-008's interval is
[+0.0235, +0.0858]: the claim's direction is settled on this snapshot, its
magnitude is not.

## 6. Working tree dirty

`code.dirty: true`. Uncommitted while running: this experiment's folder and
`eval/harness/stats.py`. `apps.content` is unchanged — no production behaviour was
touched, and the three re-run arms reproduced their committed values exactly,
which is the evidence for that.
