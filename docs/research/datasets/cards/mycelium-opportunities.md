# Dataset card — Mycelium opportunity corpus

## Identity

| Field | Value |
|---|---|
| Name | Mycelium opportunity corpus — grants, fellowships, conference CFPs |
| Sources | Pivot-RP (Clarivate); Illinois Fellowship Finder |
| Licence | Proprietary / site terms |
| Redistributable | **No** |
| Version | Rolling |

## Composition

Grants and fellowships with eligibility prose, deadlines, and sponsor metadata;
~2,989 conference CFP records. Deadlines are normalized into `ContentDeadline`
rows; fellowship eligibility is evaluated by a deterministic rule engine, not an
LLM.

## Why this blocks publication

Pivot-RP is a commercial Clarivate product behind institutional SSO. The Illinois
Fellowship Finder is one university's website, accessed by a Playwright scrape.
Neither can be redistributed, which means:

- no independent reproduction of any grant, fellowship, or conference result;
- no *Available* artifact badge for a paper resting on this corpus;
- no shared benchmark contribution, which is the gap (G1) most worth filling.

## The route out

W10 in [`../../OPEN_QUESTIONS.md`](../../OPEN_QUESTIONS.md): rebuild from CORDIS,
NIH RePORTER, NSF Awards, and public university listings. Estimated 3 weeks. It
costs the Pivot conference CFPs, which have no open equivalent — so the
conference half of the product would lose its corpus, and any conference claim
would have to be dropped or re-sourced.

Award-linkage ground truth (W7) can be built from the same open sources: profile
each PI from publications strictly *before* the award date, positives = programs
won, negatives = contemporaneous unwon calls. ⚠️ Two hazards, both fatal if
unhandled: temporal leakage (publication-to-grant year gap is the single most
predictive feature in prior work), and *won ≠ applied*, so the positives carry
selection bias.

## Status: no experiment uses this yet

Claims C-005 (eligibility gating) and the fellowship half of the work have no
evidence. Nothing here has been measured.
