# Paper Outline

The paper this record is building toward. Sections map to files here, so that
writing is assembly rather than reconstruction.

**Working title:** Eligibility-Constrained Recommendation of Fellowships and
Grants with Graded Ineligibility

**Chosen contribution:** Path A. Rationale and alternatives in
[`venue-targets.md`](venue-targets.md).

**Status:** the contribution is chosen; the evidence for it does not exist yet.
Every C-005 row in [`../CLAIMS.md`](../CLAIMS.md) is `unsupported`, and the
corpus it rests on is not redistributable
([`../datasets/cards/mycelium-opportunities.md`](../datasets/cards/mycelium-opportunities.md)).
W5, W7, and W10 are the gates.

## Sections

| § | Section | Assembled from | State |
|---|---|---|---|
| 1 | Introduction — the problem: relevance is not the same as winnability | `../../purpose.md`, audit §1.2 | not written |
| 2 | Related work | [`../RELATED_WORK.md`](../RELATED_WORK.md) | seeded, prose not written (W4) |
| 3 | Task formulation — graded eligibility, adapting the TREC-CDS scheme [B21] to scholarly funding | audit §4 G2, [`../DECISIONS.md`](../DECISIONS.md) | not written |
| 4 | System — the deterministic rule engine, the 0.65·cosine + 0.35·rule-fit blend, the retrieval substrate beneath it | `../../architecture.md`, `../../repo-map.md` | describable today |
| 5 | Retrieval substrate, measured | `EXP-2026-08-001`, `EXP-2026-08-002` | **done** |
| 6 | Eligibility evaluation | W5 judgments — do not exist | **blocked** |
| 7 | Results | experiment `RESULTS.md` files, `tables/`, `figures/` | partial |
| 8 | Limitations | [`../OPEN_QUESTIONS.md`](../OPEN_QUESTIONS.md) "known weaknesses" | written, and unusually long |
| 9 | Reproducibility statement | manifests + [`ARTIFACT_APPENDIX.md`](ARTIFACT_APPENDIX.md) | assembles automatically |

## What §5 must say, whatever else the paper argues

The retrieval measurement produced a negative result and it is not optional to
report it:

- **BM25 alone beats every fusion arm** on nDCG@10 across all three LongEval-Sci
  snapshots, and the organizers' 4B-parameter dense baseline also loses to BM25.
  This is evidence about the shape of the task — short keyword queries over
  titles and abstracts — not only about the 384-dimension embedder in use.
- **The dense-pool restriction costs recall.** BM25 currently indexes only what
  dense retrieval already found, so the lexical channel can reorder a document
  but can never add one. A union pool raises R@100 by 8.7% on the 2026 snapshot
  and 75–80% on the 2025 pair.
- Every number rests on click-model pseudo-relevance judgments, not human
  assessment.

Writing §5 as anything other than "the substrate is weaker than assumed, here is
by how much" would be the overstatement failure this record exists to prevent.

## What the paper may not claim

Carried verbatim in spirit from [`../../evaluation.md`](../../evaluation.md), and
binding:

- Nothing measured on LongEval licenses a claim about the *personalized feed*
  task. LongEval is query → documents; Mycelium is declared-interest profile →
  feed.
- Nothing about cluster max-pooling, LLM percent-match, fellowship eligibility,
  or member routing has been exercised (C-003 to C-006).
- Confidence is capped by the judgments: click-derived, not human.

## Anti-scoop check before submission

Re-sweep [`../RELATED_WORK.md`](../RELATED_WORK.md) — Scholar Inbox [B1] scoops
the paper-feed framing outright, and ResearchArena [B26] and the multi-agent
critique line point against LLM-heavy framings. The two unscooped gaps (G2 graded
eligibility, G3 lab-level routing) are the whole contribution, so confirming they
are still unscooped is a submission gate, not a formality.
